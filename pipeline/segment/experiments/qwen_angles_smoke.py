"""Smoke test of the deployed Qwen multi-angle app: model load + 2 steps on a synthetic gradient (no panel)."""
import io
import time

import modal
import numpy as np
from PIL import Image

g = np.linspace(0, 255, 512, dtype=np.uint8)
img = Image.fromarray(np.stack([np.tile(g, (512, 1)), np.tile(g[:, None], (1, 512)), np.full((512, 512), 128, np.uint8)], 2))
buf = io.BytesIO()
img.save(buf, format="PNG")
Angles = modal.Cls.from_name("zumi-qwen-angles", "Angles")
t = time.perf_counter()
try:
    r = Angles().views.remote(buf.getvalue(), ["<sks> front-left quarter view eye-level shot medium shot"], steps=2)
    print("OK", len(r["images"]), "image, run", r["secs"], "s, load", r["load_s"], "s, peak", r["peak_gb"], "GB,",
          f"wall {time.perf_counter() - t:.0f} s")
except Exception as e:
    print("FAILED", repr(e)[:800])
