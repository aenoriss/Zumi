"""Qwen-Image-Layered on Modal: one image in, N transparent RGBA layers out (bottom to top).

Alibaba Qwen, Apache-2.0, 20B parameters (arXiv 2512.15603). Too large for the local RTX 3060 (about 45 GB peak at
1024 px), so it runs on a Modal A100-80GB. Used only as an upper-bound test for scene layering
(docs/research/scene-layers-synthesis-2026-10.md); our own depth orders the layers, its stack order is not depth.

    modal deploy pipeline/modal/qwen_layered.py              # deploy the app
    modal run pipeline/modal/qwen_layered.py::download       # once: weights into the volume
    modal run pipeline/modal/qwen_layered.py --path in.png --layers 4 --out out_dir
"""

import io
import time

import modal

MODEL = "Qwen/Qwen-Image-Layered"
app = modal.App("zumi-qwen-image-layered")
weights = modal.Volume.from_name("qwen-image-layered-weights", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.6.0",
        "torchvision==0.21.0",  # Qwen2.5-VL's video processor imports it at load time; startup failed without it
        "transformers>=4.51.3",
        "accelerate",
        "safetensors",
        "pillow",
        "python-pptx",
        "huggingface_hub[hf_transfer]",
        "git+https://github.com/huggingface/diffusers",  # the model card requires diffusers from main
    )
    .env({"HF_HOME": "/weights", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
)


@app.function(image=image, volumes={"/weights": weights}, timeout=3600)
def download():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL)
    weights.commit()


@app.cls(image=image, gpu="A100-80GB", volumes={"/weights": weights}, timeout=1800, scaledown_window=120)
class Layered:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import QwenImageLayeredPipeline

        t = time.perf_counter()
        self.pipe = QwenImageLayeredPipeline.from_pretrained(MODEL).to("cuda", torch.bfloat16)
        self.pipe.set_progress_bar_config(disable=True)
        self.load_s = time.perf_counter() - t

    @modal.method()
    def decompose(self, png: bytes, layers: int = 4, resolution: int = 640, steps: int = 50, seed: int = 777) -> dict:
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGBA")
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        with torch.inference_mode():
            out = self.pipe(image=img, generator=torch.Generator(device="cuda").manual_seed(seed), true_cfg_scale=4.0,
                            negative_prompt=" ", num_inference_steps=steps, num_images_per_prompt=1, layers=layers,
                            resolution=resolution, cfg_normalize=True, use_en_prompt=True)
        pngs = []
        for layer in out.images[0]:
            buf = io.BytesIO()
            layer.save(buf, format="PNG")
            pngs.append(buf.getvalue())
        return {"layers": pngs, "secs": round(time.perf_counter() - t, 1), "load_s": round(self.load_s, 1),
                "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}


@app.local_entrypoint()
def main(path: str, layers: int = 4, out: str = "qwen_layers", resolution: int = 640):
    from pathlib import Path

    res = Layered().decompose.remote(Path(path).read_bytes(), layers=layers, resolution=resolution)
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    for k, b in enumerate(res["layers"]):
        (d / f"{k:02d}.png").write_bytes(b)
    print(f"{len(res['layers'])} layers in {res['secs']} s (model load {res['load_s']} s), peak {res['peak_gb']} GB -> {d}")
