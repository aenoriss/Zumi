"""Masked inpainting with 2025+ open models on Modal, to fill what characters and lettering cover (the hidden
background layer behind a panel's point cloud / mesh):

  Klein   FLUX.2 [klein] 4B (Apache 2.0, Jan 2026), diffusers Flux2KleinInpaintPipeline, 4 distilled steps
  ZImage  Z-Image-Turbo (Apache 2.0, Nov 2025) + alibaba-pai Fun ControlNet Union 2.1-2601 8 steps (Apache 2.0),
          diffusers ZImageControlNetInpaintPipeline; no structural control: a black control image

Both take image + mask (white = repaint) + prompt and return one PNG at the requested size.

    modal deploy pipeline/modal/inpaint2025.py
"""

import io
import time

import modal

KLEIN = "black-forest-labs/FLUX.2-klein-4B"
ZIMAGE = "Tongyi-MAI/Z-Image-Turbo"
ZCONTROL = ("alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1", "Z-Image-Turbo-Fun-Controlnet-Union-2.1-2601-8steps.safetensors")
app = modal.App("zumi-inpaint2025")
weights = modal.Volume.from_name("inpaint2025-weights", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("torch==2.6.0", "torchvision==0.21.0", "transformers>=4.56", "accelerate", "safetensors", "pillow",
                 "huggingface_hub", "sentencepiece", "git+https://github.com/huggingface/diffusers")
    .env({"HF_HOME": "/weights"})
)


def _out(img, t, load_s):
    import torch

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"image": buf.getvalue(), "secs": round(time.perf_counter() - t, 1), "load_s": round(load_s, 1),
            "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}


@app.cls(image=image, gpu="L40S", volumes={"/weights": weights}, timeout=1800, scaledown_window=120)
class Klein:
    """model: the distilled 4B (4 steps, no guidance) or FLUX.2-klein-base-4B (50 steps, true CFG). The inpaint pipeline
    blends: at every step the latents outside the mask are reset to the (noised) original, the model does not see the
    rest of the image as context. edit() is the plain Klein editing pipeline: the image goes in as reference tokens,
    the model sees all of it and redraws the whole frame."""
    model: str = modal.parameter(default=KLEIN)

    @modal.enter()
    def load(self):
        import torch
        from diffusers import Flux2KleinInpaintPipeline, Flux2KleinPipeline

        t = time.perf_counter()
        self.pipe = Flux2KleinInpaintPipeline.from_pretrained(self.model, torch_dtype=torch.bfloat16).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        self.edit_pipe = Flux2KleinPipeline(**self.pipe.components)  # same modules, no copy
        self.edit_pipe.set_progress_bar_config(disable=True)
        weights.commit()  # keep the download for the next cold start
        self.load_s = time.perf_counter() - t

    @modal.method()
    def inpaint(self, png: bytes, mask_png: bytes, prompt: str, width: int = 0, height: int = 0, steps: int = 4,
                strength: float = 1.0, guidance: float = 4.0, seed: int = 0) -> dict:
        """Runs at the input image's size (the pipeline takes its resolution from the image)."""
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_png)).convert("L")
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        with torch.inference_mode():
            r = self.pipe(prompt=prompt, image=img, mask_image=mask, strength=strength, guidance_scale=guidance,
                          num_inference_steps=steps, generator=torch.Generator("cuda").manual_seed(seed))
        return _out(r.images[0], t, self.load_s)

    @modal.method()
    def edit(self, png: bytes, prompt: str, steps: int = 4, guidance: float = 4.0, seed: int = 0) -> dict:
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGB")
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        with torch.inference_mode():
            r = self.edit_pipe(image=[img], prompt=prompt, width=img.width, height=img.height, guidance_scale=guidance,
                               num_inference_steps=steps, generator=torch.Generator("cuda").manual_seed(seed))
        return _out(r.images[0], t, self.load_s)


@app.cls(image=image, gpu="L40S", volumes={"/weights": weights}, timeout=1800, scaledown_window=120)
class ZImage:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import ZImageControlNetInpaintPipeline, ZImageControlNetModel
        from huggingface_hub import hf_hub_download

        t = time.perf_counter()
        cn = ZImageControlNetModel.from_single_file(hf_hub_download(*ZCONTROL), torch_dtype=torch.bfloat16)
        self.pipe = ZImageControlNetInpaintPipeline.from_pretrained(ZIMAGE, controlnet=cn, torch_dtype=torch.bfloat16).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        weights.commit()
        self.load_s = time.perf_counter() - t

    @modal.method()
    def inpaint(self, png: bytes, mask_png: bytes, prompt: str, width: int, height: int, steps: int = 8,
                scale: float = 0.9, seed: int = 0) -> dict:
        """scale: controlnet_conditioning_scale; the card recommends 0.65-1.0, larger for inpainting continuity."""
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(png)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_png)).convert("L")
        control = Image.new("RGB", img.size, (0, 0, 0))
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        with torch.inference_mode():
            r = self.pipe(prompt, image=img, mask_image=mask, control_image=control, controlnet_conditioning_scale=scale,
                          width=width, height=height, num_inference_steps=steps, guidance_scale=0.0,
                          generator=torch.Generator("cuda").manual_seed(seed))
        return _out(r.images[0], t, self.load_s)
