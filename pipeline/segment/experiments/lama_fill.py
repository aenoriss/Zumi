"""LaMa (big-lama, Apache 2.0, TorchScript from the IOPaint release) on the same holes as room_plate.py: real masked
inpainting, local, no prompt. Writes lama.png and compare_lama.png (original | LaMa | Qwen edit, if present).

    python experiments/lama_fill.py <panel.png> <characters npz> <lettering npz> <out dir> [dilate px]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation

from bubbles import load_masks

WEIGHTS = Path(__file__).resolve().parents[2] / ".data" / "models" / "lama" / "big-lama.pt"


def lama(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    model = torch.jit.load(str(WEIGHTS), map_location="cuda").eval()
    h, w = mask.shape
    ph, pw = -h % 8, -w % 8  # the network wants sides divisible by 8
    im = np.pad(img, ((0, ph), (0, pw), (0, 0)), mode="symmetric")
    mk = np.pad(mask, ((0, ph), (0, pw)), mode="symmetric")
    x = torch.from_numpy(im).permute(2, 0, 1)[None].float().cuda() / 255
    m = torch.from_numpy(mk.astype(np.float32))[None, None].cuda()
    with torch.inference_mode():
        y = model(x, m)[0].permute(1, 2, 0).cpu().numpy()
    return np.clip(y[:h, :w] * 255, 0, 255).astype(np.uint8)


def main():
    import time
    src, chars, letters, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    dil = int(sys.argv[5]) if len(sys.argv) > 5 else 8
    img = np.asarray(Image.open(src).convert("RGB"))
    mask = binary_dilation(np.logical_or.reduce([f.mask for f in load_masks(chars) + load_masks(letters)]), iterations=dil)
    t = time.perf_counter()
    filled = lama(img, mask)
    print(f"lama {time.perf_counter() - t:.1f} s (incl. load), {img.shape[1]}x{img.shape[0]}, holes {mask.mean() * 100:.1f}%")
    plate = np.where(mask[..., None], filled, img)  # LaMa keeps known pixels anyway; exact original outside
    Image.fromarray(plate).save(out / "lama.png")
    panes = [(img, "original"), (plate, "LaMa (local, free)")]
    if (out / "plate.png").exists():
        panes.append((np.asarray(Image.open(out / "plate.png").convert("RGB")), "Qwen edit (Modal)"))
    h, w = mask.shape
    sheet = Image.new("RGB", (len(panes) * (w + 16), h + 24), "white")
    for i, (p, label) in enumerate(panes):
        sheet.paste(Image.fromarray(p), (i * (w + 16), 24))
        ImageDraw.Draw(sheet).text((i * (w + 16) + 4, 6), label, fill=(0, 0, 0))
    sheet.save(out / "compare_lama.png")


if __name__ == "__main__":
    main()
