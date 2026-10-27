"""LEGACY: steps 4-6 as a depth-based surface, replaced by flat layers (cards.py, user 2026-10-25). Kept runnable with
`episode.py --legacy-mesh`.

Per box: precise depth (parallax.build: DA3MONO tiled, shift from DA3METRIC) on the lettering-free base as a point
cloud and mesh grid; hidden layers with their depth fitted to it (hidden_layer_export.py); scene and layers joined
into one layered depth mesh (ldi_mesh.py); mesh tears judged by Haiku 5.5 and closed (tears.py, scene_judge.py);
the lettering placed against that surface. Why it went: on close-ups DA3MONO gives a ramp with no figure in it
(ToG 228 p10, TB4 p35) and the fit to DA3METRIC breaks (correlation -0.07-0.63), and where it worked the surface
was 1-3 M points and a GLB of up to 33 MB for what reads as a few planes.

Modules only this path uses: parallax.build (and its depth cleanup), hidden_layer_export, occlusion_mask, ldi_mesh,
tears, scene_judge.judge_tears, hidden_layers.finish / build_plain, export_zumi.box_scene_legacy.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import torch

from openrouter import BudgetExceeded


def scene_finish(a, stem, i, img, letters_i, und_i, root) -> None:
    """After a box's mesh exists: tears judged and closed (Haiku 5.5 on the tear sheet), then the lettering redrawn
    from data (bubbles.json, placed clear of the 3D scene)."""
    import lettering_layer as LL
    import tears as TR
    from occlusion_mask import read_cloud2
    from scene_judge import judge_tears
    pid = f"{stem}-p{i:03d}"
    tdir = root / "tears" / pid
    try:
        # only boxes with hidden layers: the tears close the scene surface over a layer behind it (fgclean.f32)
        T = TR.list_tears(pid, root, tdir) if (root / "mesh" / f"{pid}.fgclean.f32").exists() else []
        if T:
            dec = judge_tears(tdir / "tears_sheet.png", tdir / "tears.json", tag=f"{stem} p{i} tears")
            (tdir / "decisions.json").write_text(json.dumps(dec, indent=1))
            if dec.get("close"):
                TR.close_tears(pid, root, tdir, dec["close"])
    except BudgetExceeded as e:
        print(f"p{i} tears skipped: {e}")
    if letters_i:
        _, _, _, _, L, D = read_cloud2(pid, root)
        LL.build(pid, img, [e.mask for e in letters_i], und_i, D, root / "mesh" / f"{pid}.bubbles.json",
                 kinds=[e.kind for e in letters_i], valid=L != 2)


def depth_and_layers(a, stem, picks, img_of, letters, chars, und=None, proc=None) -> dict:
    """Steps 4-6 for every box: objects chosen and masked, ONE erase call per box (all masks: lettering, characters,
    objects) while the depth models load, depth on the lettering-free base, hidden layers and the layered mesh, tears
    judged and closed, lettering redrawn as floating panels. Stops cleanly at the BFL and OpenRouter daily caps."""
    import depth as DP
    from episode import choose_box_objects
    from hidden_layers import build_plain, erase_boxes, finish, prepare

    root = a.out / "parallax"
    und = und or {}
    union = lambda els, shape: np.logical_or.reduce([e.mask for e in els]) if els else np.zeros(shape, bool)
    t = time.perf_counter()
    figs, imgs = {}, {}
    for i in picks:
        imgs[i] = img_of(i)
        shape = (imgs[i].height, imgs[i].width)
        figs[i] = (union(chars[i], shape), union(letters[i], shape))
    objs = {} if a.no_layers else choose_box_objects(a, stem, picks, imgs, {i: figs[i][0] for i in picks}, proc)
    proc = None
    torch.cuda.empty_cache()
    # lettering first: one erase call per box (in parallel, while the depth models load), then depth on each box's
    # lettering-free base image, so bubbles and captions never get depth
    boxes = {} if a.no_layers else {
        i: b for i in picks if (b := prepare(f"{stem}-p{i:03d}", imgs[i], *figs[i], root / "plates" / f"{stem}-p{i:03d}",
                                             objects=objs.get(i)))}
    with ThreadPoolExecutor(1) as pool:
        job = pool.submit(erase_boxes, list(boxes.values()))
        mono, metric = DP.load(), DP.load(DP.METRIC_ID)
        crops = job.result()
    for i in picks:
        pid = f"{stem}-p{i:03d}"
        if i in boxes and pid in crops:
            finish(boxes[i], crops[pid], mono, metric, root, objects=objs.get(i))
        else:
            build_plain(pid, imgs[i], *figs[i], mono, metric, root, objects=objs.get(i))
        scene_finish(a, stem, i, imgs[i], letters[i], und.get(i), root)
    return {"depth_and_layers": time.perf_counter() - t}
