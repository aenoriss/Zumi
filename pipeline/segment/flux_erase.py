"""Fill a panel's holes (characters + lettering) with FLUX Erase (Black Forest Labs API, May 2026): image + binary
mask in, no prompt; trained for removal, also takes the shadows the mask misses.

The model was trained at ~1 MP with aspects between 1:2 and 2:1, and webtoon panels are taller (700x2000 = 1:2.86),
so each hole gets its own crop with generous context (no prompt, so context cannot mislead it), expanded to a
trained aspect and scaled to ~1 MP. Crops run in order on the current result, so a later crop sees earlier fills.

    python flux_erase.py <panel.png> <characters npz> <lettering npz> <out png> [--dry]
BFL_API_KEY in pipeline/.env. Every call's credits are logged to .data/spend/bfl.jsonl (1 credit = 0.01 USD).
"""
import base64
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import requests
from PIL import Image
from scipy.ndimage import binary_dilation, label

from masks import load_masks

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
API = "https://api.bfl.ai/v1"
SPEND = ROOT / ".data" / "spend" / "bfl.jsonl"
DAILY_USD = float(os.environ.get("BFL_DAILY_USD", 2.0))  # the user's 2 USD/day; a run may raise it only with their
                                                         # explicit permission for that day (BFL_DAILY_USD=4)


def key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("BFL_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["BFL_API_KEY"]


def spent_today():
    if not SPEND.exists():
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(json.loads(l)["usd"] for l in SPEND.read_text().splitlines() if l.startswith('{"day": "' + today))


def b64(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def erase(img, mask, dilate=8):
    if spent_today() >= DAILY_USD:
        raise SystemExit(f"BFL daily budget reached ({spent_today():.2f} USD)")
    h = {"x-key": key(), "accept": "application/json"}
    r = requests.post(f"{API}/flux-tools/erase-v1", headers=h, timeout=60,
                      json={"image": b64(img), "mask": b64(mask), "dilate_pixels": dilate, "output_format": "png"})
    r.raise_for_status()
    job = r.json()
    t = time.perf_counter()
    while True:
        time.sleep(1.0)
        p = requests.get(job.get("polling_url") or f"{API}/get_result", headers=h, params={"id": job["id"]}, timeout=60).json()
        if p["status"] == "Ready":
            break
        if p["status"] not in ("Pending", "Processing", "Queued"):
            raise RuntimeError(f"FLUX Erase: {p['status']} {p}")
        if time.perf_counter() - t > 300:
            raise TimeoutError("FLUX Erase took over 5 min")
    cost = job.get("cost", p.get("cost"))
    usd = (cost or 0) / 100
    SPEND.parent.mkdir(parents=True, exist_ok=True)
    with SPEND.open("a") as f:
        f.write(json.dumps({"day": datetime.now(timezone.utc).date().isoformat(), "credits": cost, "usd": usd,
                            "size": img.size}) + "\n")
    out = Image.open(io.BytesIO(requests.get(p["result"]["sample"], timeout=120).content)).convert("RGB")
    return out, round(time.perf_counter() - t, 1), cost


def crops(mask, ctx=160, lo=0.5, hi=2.0):
    """One crop per connected hole, skipping holes already inside an earlier crop: the hole's box plus `ctx` px of
    context, widened or heightened (within the panel) until its aspect is between 1:2 and 2:1."""
    lab, n = label(mask)
    H, W = mask.shape
    boxes = []
    comps = sorted(range(1, n + 1), key=lambda i: -(lab == i).sum())
    for i in comps:
        ys, xs = np.nonzero(lab == i)
        if any(x0 <= xs.min() and xs.max() < x1 and y0 <= ys.min() and ys.max() < y1 for x0, y0, x1, y1 in boxes):
            continue
        x0, y0 = max(0, xs.min() - ctx), max(0, ys.min() - ctx)
        x1, y1 = min(W, xs.max() + 1 + ctx), min(H, ys.max() + 1 + ctx)
        while (x1 - x0) / (y1 - y0) < lo and (x0 > 0 or x1 < W):
            x0, x1 = max(0, x0 - 8), min(W, x1 + 8)
        while (x1 - x0) / (y1 - y0) < lo:  # panel narrower than 1:2 at this height: shrink the context vertically
            cy = (y0 + y1) // 2
            half = int((x1 - x0) / lo / 2)
            y0, y1 = max(0, min(cy - half, ys.min())), min(H, max(cy + half, ys.max() + 1))
            break
        while (x1 - x0) / (y1 - y0) > hi and (y0 > 0 or y1 < H):
            y0, y1 = max(0, y0 - 8), min(H, y1 + 8)
        boxes.append((x0, y0, x1, y1))
    return boxes


def shadow_take(orig, got, mask, reach=150, thresh=14):
    """Where to use the model's pixels: the holes, plus whatever it changed noticeably (mean RGB difference over
    `thresh`, after a small blur against resampling noise) within `reach` px of a hole and touching it: the shadows
    and glow it removed. A fixed margin cut those shadows in half."""
    import cv2
    d = np.abs(cv2.GaussianBlur(got.astype(np.float32), (0, 0), 2) - cv2.GaussianBlur(orig.astype(np.float32), (0, 0), 2)).mean(-1)
    near = binary_dilation(mask, iterations=reach)
    changed = binary_dilation((d > thresh) & near, iterations=2) | mask
    lab, _ = label(changed)
    keep = np.unique(lab[mask])
    return np.isin(lab, keep[keep > 0])


def erase_panel(cur, mask, dry=False):
    """All holes in one call: the panel padded to the nearest trained aspect (1:2 for a tall webtoon panel) with its
    own mirrored edges (and mirrored mask), scaled to ~1 MP; the padding is cut off again afterwards. Returns the
    plate (the model's pixels in the holes and in the shadows it removed, the original elsewhere), the raw output and
    a log line; (None, None, line) when dry."""
    h, w = mask.shape
    pw = max(0, int(np.ceil(h * 0.5)) - w)  # extra width for 1:2
    ph = max(0, int(np.ceil(w * 0.5)) - h)  # extra height for 2:1 (wide panels)
    l, t = pw // 2, ph // 2
    padded = np.pad(cur, ((t, ph - t), (l, pw - l), (0, 0)), mode="reflect")
    # the mask is mirrored too: a mirrored box or character left unmasked in the padding would read as scene to keep
    pm = np.pad(mask, ((t, ph - t), (l, pw - l)), mode="reflect")
    PH, PW = pm.shape
    s = (1024 * 1024 / (PW * PH)) ** 0.5
    W, H = round(PW * s / 16) * 16, round(PH * s / 16) * 16
    line = f"one call: {w}x{h} padded to {PW}x{PH} (aspect {PW / PH:.2f}) -> {W}x{H}, holes {mask.mean() * 100:.0f}%"
    if dry:
        return None, None, line
    out, secs, cost = erase(Image.fromarray(padded).resize((W, H), Image.LANCZOS),
                            Image.fromarray(pm.astype(np.uint8) * 255).resize((W, H), Image.NEAREST))
    got = np.asarray(out.resize((PW, PH), Image.LANCZOS))[t:t + h, l:l + w]
    take = shadow_take(cur, got, mask)
    plate = cur.copy()
    plate[take] = got[take]
    return plate, got, line + f"; erase {secs} s, {cost} credits; pasted {take.mean() * 100:.1f}% (holes + shadows removed)"


def erase_packed(items, gap=48, max_mp=4.0):
    """Several (image, mask) pairs in ONE call, at native resolution, scaled down only past max_mp. Measured prices:
    0.52 MP 3.0 credits, 1.0 MP 3.4, 1.71 MP 4.2, 2.75 MP 5.8, 3.98 MP 5.8, so four ~1 MP pieces in one call cost
    about 1.5 credits each against 3.4 for a call each (ToG 228 p7-p11).

    No flat colour anywhere: the model fills holes with flat colour it sees nearby (a grey filler strip and wide white
    gutters came back as grey and white blocks in p7 and p9). Each piece is padded by gap/2 with its own mirrored
    edges (mask mirrored too, so a mirrored character is erased as well), pieces sit edge to edge, and a short row is
    filled the same way. Rows (shelf packing) keep the canvas near square, inside the 1:2-2:1 range the model was
    trained on. Returns ([plate per item], log line)."""
    pad = gap // 2
    pieces = [(np.pad(im, ((pad, pad), (pad, pad), (0, 0)), mode="reflect"), np.pad(m, pad, mode="reflect"))
              for im, m in items]

    def shelf(target):
        rows, cur, x = [], [], 0
        for k, (pi, _) in enumerate(pieces):
            w = pi.shape[1]
            if cur and x + w > target:
                rows.append(cur)
                cur, x = [], 0
            cur.append(k)
            x += w
        rows.append(cur)
        W = max(sum(pieces[k][0].shape[1] for k in r) for r in rows)
        H = sum(max(pieces[k][0].shape[0] for k in r) for r in rows)
        return rows, W, H

    # row width chosen for the squarest canvas: webtoon boxes are tall (0.35-0.8), so a fixed sqrt(area) target
    # stacked them (aspects 0.43 and 0.28 on ToG 228 p7-p11) where side by side is near square
    widths = sorted({sum(p[0].shape[1] for p in pieces[:k]) for k in range(1, len(pieces) + 1)})
    rows, W, H = min((shelf(t) for t in widths), key=lambda r: abs(np.log(r[1] / r[2])))
    band_img, band_mask, pos, y = [], [], [None] * len(items), 0
    for r in rows:
        rh = max(pieces[k][0].shape[0] for k in r)
        ims, ms, x = [], [], 0
        for k in r:
            pi, pm = pieces[k]
            extra = rh - pi.shape[0]  # a shorter piece continues downward in mirror
            ims.append(np.pad(pi, ((0, extra), (0, 0), (0, 0)), mode="symmetric"))
            ms.append(np.pad(pm, ((0, extra), (0, 0)), mode="symmetric"))
            pos[k] = (x + pad, y + pad)
            x += pi.shape[1]
        ri, rm = np.concatenate(ims, 1), np.concatenate(ms, 1)
        if W > x:  # a shorter row continues sideways in mirror
            ri = np.pad(ri, ((0, 0), (0, W - x), (0, 0)), mode="symmetric")
            rm = np.pad(rm, ((0, 0), (0, W - x)), mode="symmetric")
        band_img.append(ri)
        band_mask.append(rm)
        y += rh
    canvas, cmask = np.concatenate(band_img, 0), np.concatenate(band_mask, 0)
    s = min(1.0, (max_mp * 1024 * 1024 / (W * H)) ** 0.5)
    SW, SH = round(W * s / 16) * 16, round(H * s / 16) * 16
    out, secs, cost = erase(Image.fromarray(canvas).resize((SW, SH), Image.LANCZOS),
                            Image.fromarray(cmask.astype(np.uint8) * 255).resize((SW, SH), Image.NEAREST))
    got = np.asarray(out.resize((W, H), Image.LANCZOS))
    plates = []
    raws = []  # the model's whole output per piece, not only its pixels in the holes (whole-background test)
    for (im, m), (x, y) in zip(items, pos):
        h, w = m.shape
        g = got[y:y + h, x:x + w]
        raws.append(g.copy())
        take = shadow_take(im, g, m)
        p = im.copy()
        p[take] = g[take]
        plates.append(p)
    erase_packed.last_raw = raws
    return plates, (f"packed {len(items)} into {W}x{H} -> {SW}x{SH} ({SW * SH / 1048576:.2f} MP, aspect {W / H:.2f}); "
                    f"erase {secs} s, {cost} credits")


def single(img, cur, mask, dst):
    plate, got, line = erase_panel(cur, mask, dry="--dry" in sys.argv)
    print(line)
    if plate is None:
        return
    Image.fromarray(got).save(dst.with_name(dst.stem + "_raw.png"))
    cur[:] = plate
    Image.fromarray(cur).save(dst)
    h, w = mask.shape
    side = Image.new("RGB", (w * 2 + 16, h), "white")
    side.paste(img, (0, 0)); side.paste(Image.fromarray(cur), (w + 16, 0))
    side.save(dst.with_name(dst.stem + "_side.png"))
    print(f"BFL spend today: {spent_today():.2f} USD")


def main():
    src, cpath, lpath, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    img = Image.open(src).convert("RGB")
    cur = np.asarray(img).copy()
    mask = binary_dilation(np.logical_or.reduce([f.mask for f in load_masks(cpath) + load_masks(lpath)]), iterations=10)
    if "--mask" in sys.argv:  # a ready erase mask (occlusion_mask.py: characters, lettering and depth bands)
        mask = np.asarray(Image.open(sys.argv[sys.argv.index("--mask") + 1]).convert("L")) > 127
    if "--crops" not in sys.argv:
        single(img, cur, mask, dst)
        return
    boxes = crops(mask)
    for x0, y0, x1, y1 in boxes:
        cw, ch = x1 - x0, y1 - y0
        s = (1024 * 1024 / (cw * ch)) ** 0.5
        W, H = round(cw * s / 16) * 16, round(ch * s / 16) * 16
        print(f"crop {(x0, y0, x1, y1)} {cw}x{ch} (aspect {cw / ch:.2f}) -> {W}x{H}, holes {mask[y0:y1, x0:x1].mean() * 100:.0f}%")
        if "--dry" in sys.argv:
            continue
        c = Image.fromarray(cur[y0:y1, x0:x1]).resize((W, H), Image.LANCZOS)
        m = Image.fromarray(mask[y0:y1, x0:x1].astype(np.uint8) * 255).resize((W, H), Image.NEAREST)
        out, secs, cost = erase(c, m)
        print(f"  erase {secs} s, {cost} credits")
        got = np.asarray(out.resize((cw, ch), Image.LANCZOS))
        # FLUX Erase may also clean shadows just outside the mask: take its pixels in the dilated mask, not further
        take = binary_dilation(mask[y0:y1, x0:x1], iterations=12)
        cur[y0:y1, x0:x1][take] = got[take]
    if "--dry" in sys.argv:
        return
    Image.fromarray(cur).save(dst)
    w, h = img.size
    side = Image.new("RGB", (w * 2 + 16, h), "white")
    side.paste(img, (0, 0)); side.paste(Image.fromarray(cur), (w + 16, 0))
    side.save(dst.with_name(dst.stem + "_side.png"))
    print(f"BFL spend today: {spent_today():.2f} USD")


if __name__ == "__main__":
    main()
