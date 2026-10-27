"""Flat prefill + band mask, one FLUX Erase call per box, and FLUX's RAW output taken for everything under the cards
(one source: no patch seams). Card interiors are prefilled with the plain background-only membrane fill (no texture:
textured strokes were continued by FLUX as crackle and stamped shapes, P&C 39 p7); the mask is a band per card (its
30 cm lean shift + 6 px) plus a RING px ring outside. FLUX repaints the unmasked interior coherently too, so its whole
output is used under the cards and in the ring, colour cast removed by a per-channel fit outside the cards, the seam
tone matched (ghost_iter.seam_match). The raw output is saved (<name>-raw-pNNN.npz) so later rounds cost nothing.

    uv run python experiments/prefill_raw.py <name> --panels 9,10,19,21,26,14,18,23,7
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt as edt

import flux_erase as FE
import ghost_iter as GI
import prefill_tex as PT
import shadow_fill as SF

RING = 0          # was 3: the API already grows the mask by dilate_pixels=8, the ring only removed context
GRAIN_GAIN = 1.0
NO_PAGE = True
PREFILL = "mirror"  # "mirror" (real background mirrored in) or "flat" (membrane + grain)
MIRROR_BLUR = 2.0   # px, so a mirrored line is a soft echo, not a hard doubled edge
INSET_PX = 14  # the windows are cut 1% inside their frame (cards.INSET): grown back to the frame's edge
ROW_H = 300


def grain(img, src, hole, rng):
    """Fine grain over `hole` (band-pass sigma 0.8-2 of random background patches, no strokes): a perfectly flat
    prefill left a large flat unmasked area, and FLUX Erase answered with flat placeholder colour (green, khaki, teal)
    over the whole mask (P&C 39 p23: flat prefill failed 3 of 3, textured prefill with the same mask worked)."""
    import junction_fix as JF
    return JF.band_texture(img.astype(np.float32), src, hole, rng, gain=GRAIN_GAIN)


def main():
    name = sys.argv[1]
    rng = np.random.default_rng(0)
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    SF.LEAN = 0.3 / 1.5
    z = zipfile.ZipFile(GI.ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rows = []
    for i in picks:
        pid = f"pepper-carrot-39-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cards, _ = SF.cards_of(json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text()), GI.OUT / "parallax/mesh")
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        # the page is what lies outside every frame (cards.json windows), not "white": a near-white test took the
        # bubbles' interiors for page, so no ring was masked around them and the prefill skipped them
        cj = json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text())
        frames = []
        for L in cj["layers"]:
            if L["kind"] == "backdrop":
                fa = np.zeros(foot.shape, bool)
                wa = np.asarray(Image.open(GI.OUT / "parallax/mesh" / L["window"]))[..., 3] > 0
                wx0, wy0 = L["window_bbox"][:2]
                fa[wy0:wy0 + wa.shape[0], wx0:wx0 + wa.shape[1]] = wa
                frames.append(binary_dilation(fa, iterations=INSET_PX))
        page = ~np.logical_or.reduce(frames)
        d = edt(foot)
        band = np.zeros_like(foot)
        for c in cards:
            # a bubble is masked whole: it is small, and its white interior must not reach the model as content
            band |= c["mask"] if c["kind"] == "lettering" else c["mask"] & (d <= abs(c["shift"]) + 6)
        # (scipy's iterations=0 means "until nothing changes": the ring must be built only when RING > 0)
        ring = (binary_dilation(foot, iterations=RING) & ~foot & ~page) if RING > 0 else np.zeros_like(foot)
        mask = (band | ring) & ~page
        ys, xs = np.nonzero(~page)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        raw = GI.R / f"{name}-raw-p{i:03d}.npz"
        if raw.exists():
            g = np.load(raw)["g"]
            line = "reused saved FLUX output"
        else:
            pre = img.copy()
            if PREFILL == "mirror":
                # the interiors as the real background mirrored across each card's outline, per frame, softened a
                # little: the model's unmasked view is 20-30% our prefill against ~10% real background, and a flat
                # or finely grained prefill read as a featureless scene, answered with a flat placeholder (p23: flat
                # failed 3 of 4, grain failed, painted strokes worked with the very same mask)
                import cards as CD
                import cv2
                for fa in frames:
                    hole = foot & ~band & fa
                    if not hole.any():
                        continue
                    mir, _ = CD.mirror_fill(img, fa & ~foot)
                    mir = cv2.GaussianBlur(mir.astype(np.float32), (0, 0), MIRROR_BLUR)
                    pre[hole] = mir.clip(0, 255).astype(np.uint8)[hole]
            else:
                # the prefill per frame, from that frame's background only: one membrane over the whole box pulled
                # the right frame's blue through the gutter into the left frame's orange (P&C 39 p23)
                for fa in frames:
                    hole = foot & ~band & fa
                    if not hole.any():
                        continue
                    fill = SF.membrane(img, fa & ~foot & ~ring) + grain(img, fa & ~foot & ~ring, hole, rng)
                    pre[hole] = fill.clip(0, 255).astype(np.uint8)[hole]
            send, smask = pre, mask
            if NO_PAGE:  # the page (gutters, margins) as the frames' content mirrored outward, unmasked: the
                # placeholder colour gathered at the frames' edges against the white page (p23: 85% within 40 px of
                # a frame edge, 32% further in). The mirror source is the prefilled image minus the masked band, so
                # neither a hole nor a character is mirrored out
                import cards as CD
                filled, _ = CD.mirror_fill(pre, ~page & ~mask)
                send = np.where(page[..., None], filled, pre).astype(np.uint8)
                smask = mask & ~page
            _, got, line = FE.erase_panel(send[y0:y1, x0:x1].copy(), smask[y0:y1, x0:x1])
            g = np.zeros_like(img, dtype=np.float32)
            g[y0:y1, x0:x1] = got
            np.savez_compressed(raw, g=g, mask=mask)
        g = PT.cast_fit(g.astype(np.float32), img, ~binary_dilation(foot, iterations=12) & ~page)
        under = foot | ring
        res = np.where(under[..., None], g, img.astype(np.float32))
        reach = max(abs(c["shift"]) + 6 for c in cards)
        res, _ = GI.seam_match(img.astype(np.float32), res, foot, page, d, reach, 30, 200)
        halo, _, _, _ = GI.score(img.astype(np.float32), res, res, foot, band, foot & ~band, page, d)
        print(f"p{i:03d}: {line}; halo {halo:.1f}")
        out = res.astype(np.uint8)
        Image.fromarray(out).save(GI.R / f"{name}-p{i:03d}.png")
        rr = Image.fromarray(np.concatenate([img, np.full((img.shape[0], 8, 3), 20, np.uint8), out], 1))
        rr = rr.resize((round(rr.width * ROW_H / rr.height), ROW_H))
        dr = ImageDraw.Draw(rr)
        dr.rectangle([0, 0, 120, 13], fill=(0, 0, 0))
        dr.text((3, 1), f"p{i:03d} source", fill=(255, 255, 255))
        x = rr.width // 2 + 4
        dr.rectangle([x, 0, x + 240, 13], fill=(0, 0, 0))
        dr.text((x + 3, 1), "flat prefill, FLUX raw under cards", fill=(255, 255, 255))
        rows.append(rr)
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(GI.R / f"{name}.png")
    print(GI.R / f"{name}.png", f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    sys.path.insert(0, str(GI.Path(__file__).resolve().parent.parent))
    main()
