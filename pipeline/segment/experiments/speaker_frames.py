"""The speaker rules on new frames without rebuilding the layers (2026-10-30): frames.split on every box of the speaker
dataset, each saved character card cut by the new frames the way cards.layers cuts a mask spanning frames (a piece of
at least cards.PART_MIN px per frame), the bubbles homed as speakers.load_box homes them (home_frame: a stack read
in one frame, a straddler in the frame of its tail tip), speakers.assign re-run. An answer
naming a piece counts as naming the card it was cut from, since the labels name the saved cards. Scored as
speaker_eval.py scores, on all four episodes: the saved layers' frames against the new ones, with the bubbles whose
verdict changed.

    uv run python experiments/speaker_frames.py <out root> [--cached v1|v2] [--review]

--cached: the answers cached for that prompt version, read only: any model call raises (no paid call). Without it the
current prompt's answers are used, asked for when not cached.
--review: the labelling page shows the bubbles whose verdict changed: speakers/review.json lists them (the old one
kept as review.backup-<n>.json) and the new frames go into bakeoff.json as the method "split" (open with ?fm=split).
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import frames as FR  # noqa: E402
from boxstore import Box, index_of  # noqa: E402
from chapter import Chapter  # noqa: E402
import openrouter as OR  # noqa: E402
import page as PG  # noqa: E402
import speakers as SP  # noqa: E402
from cards import PART_MIN  # noqa: E402

def box_image(root: Path, ep: str, i: int) -> Image.Image:
    return Chapter(root / "chapters" / f"{ep}.zumi").image(i)


def letters_of(root: Path, box: dict) -> np.ndarray | None:
    ms = Box(root / "dataset" / box["episode"], box["pid"]).letters()
    return np.logical_or.reduce([m.mask for m in ms]) if ms else None


def gutter_of(root: Path, box: dict, img: Image.Image) -> np.ndarray:
    return PG.gutter(img, letters_of(root, box))


def new_split(root: Path, box: dict, cached: str | None = None) -> FR.Split:
    """frames.split of the box, on the answer cached for prompt `cached` ("v1", "v2"), or the current prompt's."""
    img = box_image(root, box["episode"], index_of(box["pid"]))
    if cached:
        f = FR.cache_file(img, {"v1": FR.PROMPT_V1, "v2": FR.PROMPT_V2}[cached])
        lay = FR.to_layout(json.loads(f.read_text()), *img.size) if f.exists() else None
    else:
        try:
            lay = FR.layout(img, f"panels:{box['pid']}")
        except (OR.BudgetExceeded, FR.PanelError):
            lay = None
    return FR.split(img, gutter_of(root, box, img), lay, letters_of(root, box))


def recut(cards, bubbles, s: FR.Split):
    """(cards cut by the frames of s, the parent card of each piece, the bubbles homed in them, the frames)."""
    fr = s.frames
    new, parent = [], []
    for p, c in enumerate(cards):
        pieces = [(k, c.mask & f) for k, f in enumerate(fr) if (c.mask & f).sum() >= PART_MIN]
        if not pieces:
            share = [int((c.mask & f).sum()) for f in fr]  # on the page between frames: whole, the frame it touches most
            pieces = [(int(np.argmax(share)) if share and max(share) else None, c.mask)]
        for k, m in pieces:
            new.append(SP.Card(c.key, c.kind, k, m, SP._centroid(m), int(m.sum())))
            parent.append(p)
    SP.order_bubbles(bubbles, fr)  # homes each bubble's stack in the new frames
    return new, parent, bubbles, fr


def verdict(a, lab, cards, parent):
    if lab["kind"] != "card":
        return a["speaker_kind"] == lab["kind"]
    gs = [{parent[i] for i in g} for g in SP.groups(cards)]
    allowed = {i for g in gs if any(s in g for s in lab["speakers"]) for i in g} | set(lab["speakers"])
    got = {parent[i] for i in a["speakers"]}
    return a["speaker_kind"] == "card" and set(lab["speakers"]) <= got <= allowed


def main() -> None:
    root = Path(sys.argv[1])
    cached = sys.argv[sys.argv.index("--cached") + 1] if "--cached" in sys.argv else None
    if cached:  # read only: a model call would be a bug
        def _no_call(*_, **__):
            raise RuntimeError("speaker_frames --cached: a model call was attempted")
        OR.chat = _no_call
    s0 = OR.spent_today()
    labels = json.loads((root / "speakers" / "labels.json").read_text())
    boxes = json.loads((root / "speakers" / "dataset.json").read_text())["boxes"]
    with ThreadPoolExecutor(8) as ex:
        splits = dict(zip([b["pid"] for b in boxes], ex.map(lambda b: new_split(root, b, cached), boxes)))
    tot = {"old": 0, "new": 0}; n = 0; flips = []; counts = []; notes = {}
    for box in boxes:
        got = SP.load_box(Box(root / "dataset" / box["episode"], box["pid"]))
        if got is None:
            continue
        cards, bubbles, old_fr, _ = got
        s = splits[box["pid"]]
        counts.append((box["pid"], len(old_fr), len(s.frames), sum(s.flat)))
        old = {b.id: SP.assign(b, cards, old_fr) for b in bubbles}
        ncards, parent, bubbles, grown = recut(cards, bubbles, s)
        for b in bubbles:
            lab = labels.get(f"{box['pid']}#{b.id}")
            if not lab or lab.get("skip") or lab["kind"] in ("missing", "off_panel"):
                continue
            a_old, a_new = old[b.id], SP.assign(b, ncards, grown)
            r_old = verdict(a_old, lab, cards, list(range(len(cards))))
            r_new = verdict(a_new, lab, ncards, parent)
            n += 1; tot["old"] += r_old; tot["new"] += r_new
            if r_old != r_new:
                why = (f"{'fixed' if r_new else 'broken'} by the new frames: label {lab['kind']} {lab['speakers']}, "
                       f"old {a_old['speakers']} ({a_old['rule']}), new {[parent[i] for i in a_new['speakers']]} ({a_new['rule']})")
                flips.append(f"  {box['pid']} #{b.id}: {why}")
                notes[f"{box['pid']}#{b.id}"] = why + ". Frames menu: 'split' = new frames."
    changed = [c for c in counts if c[1] != c[2] or c[3]]
    print(f"frames changed on {len(changed)} of {len(counts)} boxes: " +
          ", ".join(f"{p.split('carrot-')[1]} {o}->{w}" + (f" ({fl} flat)" if fl else "") for p, o, w, fl in changed))
    print(f"speakers, all four episodes: saved frames {tot['old']}/{n}, new frames {tot['new']}/{n}")
    print("\n".join(flips) or "  no bubble changed verdict")
    print(f"paid calls: {OR.spent_today() - s0:.4f} USD")
    if "--review" in sys.argv:
        write_review(root, splits, notes)


def write_review(root: Path, splits: dict[str, FR.Split], notes: dict[str, str]) -> None:
    from speaker_dataset import outline
    sp = root / "speakers"
    old = sp / "review.json"
    if old.exists():
        n = 1
        while (sp / f"review.backup-{n}.json").exists():
            n += 1
        old.rename(sp / f"review.backup-{n}.json")
    old.write_text(json.dumps(notes, indent=1))
    bk = json.loads((sp / "bakeoff.json").read_text())
    bk["methods"]["split"] = {pid: [{"rings": outline(f), "score": "flat" if fl else None}
                                    for f, fl in zip(s.frames, s.flat)] for pid, s in splits.items()}
    (sp / "bakeoff.json").write_text(json.dumps(bk))
    print(f"review: {len(notes)} bubbles in {old}; frames as 'split' in bakeoff.json")


if __name__ == "__main__":
    main()
