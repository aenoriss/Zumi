"""Camera-angle round 2 on one panel: the model the user remembered (Qwen-Image-Edit-2509 + dx8152 LoRA, Chinese
camera commands, Lightning 8 steps with the shift-3 scheduler) and a stronger push on 2511 + fal LoRA.

    python experiments/angles_round2.py <panel.png> <out dir>
"""
import sys
import time
from pathlib import Path

import modal

RUNS = [
    ("Angles2509", "将镜头向左旋转45度", {}, "2509_rotate45left"),      # rotate the camera 45 deg left
    ("Angles2509", "将镜头向左移动", {}, "2509_moveleft"),              # move the camera left
    ("Angles", "<sks> left side view eye-level shot wide shot", {"strength": 1.0}, "2511_side90_full"),
]
# round 3: the newer model with round 1's errors fixed (bubbles removed, LoRA strength 1.0 not 0.9, wide shot)
RUNS3 = [
    ("Angles", "<sks> front-left quarter view eye-level shot wide shot", {"strength": 1.0}, "2511_left45_full"),
    ("Angles", "<sks> front-right quarter view eye-level shot wide shot", {"strength": 1.0}, "2511_right45_full"),
    ("Angles", "<sks> front view elevated shot wide shot", {"strength": 1.0}, "2511_up30_full"),
]
if "--round3" in sys.argv:
    RUNS = RUNS3


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    for cls, prompt, kw, name in RUNS:
        t = time.perf_counter()
        r = modal.Cls.from_name("zumi-qwen-angles", cls)().views.remote(data, [prompt], **kw)
        (out / f"{name}.png").write_bytes(r["images"][0])
        print(name, r["secs"], "s, load", r["load_s"], "s, peak", r["peak_gb"], "GB, wall", round(time.perf_counter() - t), "s")


if __name__ == "__main__":
    main()
