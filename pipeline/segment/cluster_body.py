"""Body-only character clustering across episodes, with a 3D view (research use).

    uv run --group magi python cluster_body.py true-beauty-4 true-beauty-5 true-beauty-7

1. Detect: Magiv3 character boxes on every panel of each episode (cached in OUT/detections.json).
2. Embed: each character box cropped from the panel, padded to a square on white, DINOv2-large CLS token,
   L2-normalised. Body only: no head crop, no text, no position.
3. Cluster: average-linkage agglomerative clustering on cosine distance, all episodes together, with one
   constraint: two characters in the same panel are never merged. Merges are recorded, so the clusters can be
   cut at several distance thresholds.
4. Show: t-SNE to 3D, written as a local HTML page (Plotly) with a threshold slider, a crop preview on
   hover and a gallery per cluster. The page embeds webtoon crops, so it stays under .data (gitignored).
"""

from __future__ import annotations

import base64
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / ".data/out/chapters"
OUT = ROOT / ".data/out/cluster"
ENCODER = "facebook/dinov2-large"
MIN_SIDE = 40  # px; smaller boxes carry too little to embed
THRESHOLDS = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


def panels_of(ep: str):
    z = zipfile.ZipFile(CHAPTERS / f"{ep}.zumi")
    panels = json.loads(z.read("manifest.json"))["panels"]
    for i, p in enumerate(panels):
        yield i, Image.open(io.BytesIO(z.read(p["layers"][0]["image"]))).convert("RGB")


def detect_all(eps: list[str]) -> list[dict]:
    cache = OUT / "detections.json"
    done = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [e for e in eps if e not in done]
    if todo:
        from transformers import AutoModelForCausalLM, AutoProcessor
        from magi_run import MODEL
        from magi_superframe import detect
        model = AutoModelForCausalLM.from_pretrained(str(MODEL), torch_dtype=torch.float16, trust_remote_code=True).cuda().eval()
        proc = AutoProcessor.from_pretrained(str(MODEL), trust_remote_code=True)
        for ep in todo:
            t = time.perf_counter()
            boxes = {}
            for i, img in panels_of(ep):
                with torch.no_grad():
                    det = detect(model, proc, img)
                boxes[str(i)] = [[round(v, 1) for v in b] for b in det["characters"]]
            done[ep] = boxes
            cache.write_text(json.dumps(done))
            print(f"{ep}: {sum(len(v) for v in boxes.values())} characters in {len(boxes)} panels, {time.perf_counter() - t:.0f}s")
        del model
        torch.cuda.empty_cache()
    crops = []
    for ep in eps:
        for i, img in panels_of(ep):
            for k, b in enumerate(done[ep].get(str(i), [])):
                x0, y0, x1, y1 = max(0, b[0]), max(0, b[1]), min(img.width, b[2]), min(img.height, b[3])
                if min(x1 - x0, y1 - y0) < MIN_SIDE:
                    continue
                crops.append({"ep": ep, "panel": i, "k": k, "box": [x0, y0, x1, y1], "img": img.crop((x0, y0, x1, y1))})
    return crops


def square(im: Image.Image, size: int) -> Image.Image:
    s = max(im.size)
    out = Image.new("RGB", (s, s), (255, 255, 255))
    out.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
    return out.resize((size, size), Image.BICUBIC)


def embed(crops: list[dict]) -> np.ndarray:
    from transformers import AutoImageProcessor, AutoModel
    proc = AutoImageProcessor.from_pretrained(ENCODER)
    model = AutoModel.from_pretrained(ENCODER, torch_dtype=torch.float16).cuda().eval()
    feats = []
    for s in range(0, len(crops), 32):
        batch = [square(c["img"], 224) for c in crops[s : s + 32]]
        x = proc(images=batch, return_tensors="pt", do_resize=False, do_center_crop=False)["pixel_values"].cuda().half()
        with torch.no_grad():
            f = model(pixel_values=x).last_hidden_state[:, 0].float()
        feats.append(torch.nn.functional.normalize(f, dim=1).cpu().numpy())
    del model
    torch.cuda.empty_cache()
    return np.concatenate(feats)


def cluster(x: np.ndarray, groups: list[tuple]) -> list[tuple[int, int, float]]:
    """Average linkage on cosine distance; clusters holding two crops of the same panel never merge.
    Returns the merges (a, b, distance) in order; cluster ids follow scipy's convention (n, n+1, ...)."""
    n = len(x)
    d = 1.0 - x @ x.T
    sums = d.copy()  # sum of pairwise distances between clusters
    size = np.ones(n)
    alive = np.ones(n, bool)
    ids = list(range(n))
    banned = np.zeros((n, n), bool)
    for i in range(n):
        for j in range(i + 1, n):
            banned[i, j] = banned[j, i] = groups[i] == groups[j]
    np.fill_diagonal(banned, True)
    merges = []
    nxt = n
    while True:
        avg = sums / np.outer(size, size)
        avg[banned | ~alive[:, None] | ~alive[None, :]] = np.inf
        a, b = np.unravel_index(np.argmin(avg), avg.shape)
        if not np.isfinite(avg[a, b]):
            break
        merges.append((ids[a], ids[b], float(avg[a, b])))
        sums[a, :] += sums[b, :]
        sums[:, a] += sums[:, b]
        size[a] += size[b]
        banned[a, :] |= banned[b, :]
        banned[:, a] |= banned[:, b]
        banned[a, a] = True
        alive[b] = False
        ids[a] = nxt
        nxt += 1
    return merges


def cut(merges, n: int, t: float) -> list[int]:
    parent = list(range(n))
    owner = {i: i for i in range(n)}  # cluster id -> representative crop

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    nxt = n
    for a, b, dist in merges:
        ra, rb = owner[a], owner[b]
        if dist <= t:
            parent[find(rb)] = find(ra)
        owner[nxt] = ra
        nxt += 1
    roots = [find(i) for i in range(n)]
    order = {r: k for k, (r, _) in enumerate(sorted(((r, roots.count(r)) for r in set(roots)), key=lambda p: -p[1]))}
    return [order[r] for r in roots]


def thumb(im: Image.Image, h: int = 120) -> str:
    im = im.copy()
    im.thumbnail((h, h))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    eps = sys.argv[1:] or ["true-beauty-4", "true-beauty-5", "true-beauty-7"]
    OUT.mkdir(parents=True, exist_ok=True)
    crops = detect_all(eps)
    print(f"{len(crops)} crops of at least {MIN_SIDE}px")
    x = embed(crops)
    t = time.perf_counter()
    merges = cluster(x, [(c["ep"], c["panel"]) for c in crops])
    labels = {str(th): cut(merges, len(crops), th) for th in THRESHOLDS}
    print(f"clustered in {time.perf_counter() - t:.1f}s")
    for th in THRESHOLDS:
        lab = labels[str(th)]
        sizes = np.bincount(lab)
        multi = [k for k in range(len(sizes)) if sizes[k] > 1]
        cross = [k for k in multi if len({crops[i]["ep"] for i in range(len(crops)) if lab[i] == k}) > 1]
        print(f"t={th:.2f}: {len(sizes)} clusters, {len(multi)} with 2+ crops, {sum(sizes == 1)} singletons, "
              f"{len(cross)} span 2+ episodes, largest {sizes.max()}")
    from sklearn.manifold import TSNE
    xyz = TSNE(n_components=3, metric="cosine", perplexity=min(30, len(crops) - 1), init="pca", random_state=0).fit_transform(x)
    data = {
        "eps": eps, "thresholds": THRESHOLDS, "labels": labels, "encoder": ENCODER,
        "points": [{"ep": c["ep"], "panel": c["panel"], "xyz": [round(float(v), 3) for v in p], "img": thumb(c["img"])}
                   for c, p in zip(crops, xyz)],
    }
    page = (Path(__file__).parent / "cluster_view.html").read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data))
    out = OUT / f"{eps[0].rsplit('-', 1)[0]}-body.html"
    out.write_text(page, encoding="utf-8")
    np.save(OUT / "embeddings.npy", x)
    print("wrote", out)


if __name__ == "__main__":
    main()
