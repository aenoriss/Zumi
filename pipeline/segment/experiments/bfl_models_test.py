"""Quick test of two other Black Forest Labs models on boxes where FLUX Erase failed (masks over 75% of the box), against
the plate the pipeline has: FLUX.1 Kontext [pro] (instruction editing, no mask input: the mask is painted magenta and
the prompt asks to repaint it as background) and FLUX.1 Fill [pro] (image + mask + prompt). Each output is pasted
back only inside the mask; Kontext's drift outside the mask (it redraws the whole image) is measured. Spend goes to the
same log and daily cap as flux_erase.

    uv run python experiments/bfl_models_test.py <episode.zumi> <out dir> <sheet path> --panels 9,20,23
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import flux_erase as FE  # noqa: E402

KONTEXT_PROMPT = ("Repaint every solid magenta area as the empty background of this scene (walls, floor, furniture, "
                  "sky), continuing what is around it, in the same painted comic style and colours. No people, no "
                  "animals, no text, no speech bubbles. Leave everything that is not magenta exactly as it is.")
FILL_PROMPT = ("the empty background of this comic panel, continuing the surrounding walls, floor and sky, same painted "
               "style and colours, no people, no animals, no text")
ROW_H = 300
LIST_CREDITS = {"flux-kontext-pro": 4, "flux-pro-1.0-fill": 5}  # BFL list prices per image (1 credit = 0.01 USD)


def call(endpoint: str, payload: dict) -> Image.Image:
    if FE.spent_today() >= FE.DAILY_USD:
        raise SystemExit(f"BFL daily budget reached ({FE.spent_today():.2f} USD)")
    h = {"x-key": FE.key(), "accept": "application/json"}
    r = requests.post(f"{FE.API}/{endpoint}", headers=h, json=payload, timeout=60)
    r.raise_for_status()
    job = r.json()
    t = time.perf_counter()
    while True:
        time.sleep(1.0)
        p = requests.get(job.get("polling_url") or f"{FE.API}/get_result", headers=h, params={"id": job["id"]},
                         timeout=60).json()
        if p["status"] == "Ready":
            break
        if p["status"] not in ("Pending", "Processing", "Queued"):
            raise RuntimeError(f"{endpoint}: {p['status']}")
        if time.perf_counter() - t > 300:
            raise TimeoutError(endpoint)
    cost = job.get("cost", p.get("cost"))
    if cost is None:  # these endpoints return no cost: the list price, so the daily cap still sees the call
        cost = LIST_CREDITS[endpoint]
    usd = cost / 100
    with FE.SPEND.open("a") as f:
        f.write(json.dumps({"day": datetime.now(timezone.utc).date().isoformat(), "credits": cost, "usd": usd,
                            "model": endpoint}) + "\n")
    print(f"  {endpoint}: {round(time.perf_counter() - t, 1)} s, {cost} credits")
    return Image.open(io.BytesIO(requests.get(p["result"]["sample"], timeout=120).content)).convert("RGB")


def pad_to(img: Image.Image, lo: float, hi: float, fill) -> tuple[Image.Image, tuple]:
    """img padded (centred) so its aspect is within lo..hi, and the box to crop it back."""
    w, h = img.size
    a = w / h
    W, H = (w, round(w / hi)) if a > hi else (round(h * lo), h) if a < lo else (w, h)
    W, H = max(W, w), max(H, h)
    out = Image.new(img.mode, (W, H), fill)
    x, y = (W - w) // 2, (H - h) // 2
    out.paste(img, (x, y))
    return out, (x, y, x + w, y + h)


def main():
    zumi, out, sheet = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rows = []
    for i in picks:
        pid = f"{zumi.stem}-p{i:03d}"
        d = out / "parallax" / "plates" / pid
        src = Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
        kind = "all" if (d / "plate-all.png").exists() else "full"
        m = np.asarray(Image.open(d / f"mask-{kind}.png").convert("L").resize(src.size)) > 127
        erase = np.asarray(Image.open(d / f"plate-{kind}.png").convert("RGB").resize(src.size))
        s = np.asarray(src)
        print(f"p{i:03d}: mask {m.mean():.0%} of the box")
        # Kontext: magenta in the holes, aspect kept within 3:7..7:3 by white padding
        mag = s.copy()
        mag[m] = (255, 0, 255)
        pk, cb = pad_to(Image.fromarray(mag), 3 / 7, 7 / 3, (255, 255, 255))
        ar = f"{pk.width}:{pk.height}"
        g = np.gcd(pk.width, pk.height)
        k = call("flux-kontext-pro", {"prompt": KONTEXT_PROMPT, "input_image": FE.b64(pk),
                                      "aspect_ratio": f"{pk.width // g}:{pk.height // g}", "output_format": "png",
                                      "safety_tolerance": 2})
        k = np.asarray(k.resize(pk.size, Image.LANCZOS).crop(cb))
        drift = float(np.abs(k[~m].astype(int) - s[~m]).mean())
        kont = np.where(m[..., None], k, s)
        # Fill: image + mask (white = fill), size a multiple of 32
        W, H = (src.width // 32) * 32, (src.height // 32) * 32
        f = call("flux-pro-1.0-fill", {"image": FE.b64(src.resize((W, H))),
                                       "mask": FE.b64(Image.fromarray((m * 255).astype(np.uint8)).resize((W, H))),
                                       "prompt": FILL_PROMPT, "output_format": "png", "safety_tolerance": 2})
        f = np.asarray(f.resize(src.size, Image.LANCZOS))
        fill = np.where(m[..., None], f, s)
        cols = [(s, f"p{i:03d} source"), (mag, f"mask ({m.mean():.0%})"), (erase, "FLUX Erase (now)"),
                (kont, f"Kontext pro, pasted (drift outside {drift:.1f})"), (fill, "Fill pro, pasted")]
        r = Image.fromarray(np.concatenate([c for c, _ in cols], 1))
        sc = ROW_H / r.height
        r = r.resize((round(r.width * sc), ROW_H))
        dr = ImageDraw.Draw(r)
        for j, (c, t) in enumerate(cols):
            x = round(j * c.shape[1] * sc)
            dr.rectangle([x, 0, x + 270, 13], fill=(0, 0, 0))
            dr.text((x + 3, 1), t, fill=(255, 255, 255))
        rows.append(r)
        Image.fromarray(k).save(sheet.parent / f"kontext-raw-p{i:03d}.png")
    Wd = max(r.width for r in rows)
    sh = Image.new("RGB", (Wd, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(sheet)
    print(sheet, f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
