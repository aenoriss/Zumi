"""Qwen-Image-Edit-2511 + fal Multiple-Angles LoRA on Modal: one image in, the same scene from new camera angles out.

Research test (docs/research/novel-view-generation-2026-10.md): new views of a whole scene, room and characters,
as extra evidence for 3D reconstruction. Prompt format from the LoRA card: "<sks> [azimuth] [elevation] [distance]",
azimuth in 45 deg bins (front view, front-left quarter view, ...), elevation low-angle / eye-level / elevated /
high-angle, distance close-up / medium shot / wide shot. LoRA strength 0.9 (card: 0.8-1.0).

    modal deploy pipeline/modal/qwen_angles.py
    modal run pipeline/modal/qwen_angles.py::download                 # once: weights into the volume
    modal run pipeline/modal/qwen_angles.py --path in.png --out dir    # the three test views
"""

import io
import time

import modal

BASE = "Qwen/Qwen-Image-Edit-2511"
LORA = "fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA"
# the model the user remembered: Qwen-Image-Edit-2509 + dx8152's camera LoRA (Chinese commands such as
# 将镜头向左旋转45度, "rotate the camera 45 deg left"); its card says to use it with the Lightning LoRA (8 steps, cfg 1)
BASE_2509 = "Qwen/Qwen-Image-Edit-2509"
LORA_2509 = "dx8152/Qwen-Edit-2509-Multiple-angles"
LIGHTNING = ("lightx2v/Qwen-Image-Lightning", "Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.safetensors")
VIEWS = ["<sks> front-left quarter view eye-level shot medium shot",
         "<sks> front-right quarter view eye-level shot medium shot",
         "<sks> front view elevated shot medium shot"]
app = modal.App("zumi-qwen-angles")
weights = modal.Volume.from_name("qwen-angles-weights", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("torch==2.6.0", "torchvision==0.21.0", "transformers>=4.51.3", "accelerate", "safetensors", "pillow",
                 "peft", "huggingface_hub", "git+https://github.com/huggingface/diffusers")
    .env({"HF_HOME": "/weights"})
)


@app.function(image=image, volumes={"/weights": weights}, timeout=3600)
def download():
    from huggingface_hub import snapshot_download

    snapshot_download(BASE)
    snapshot_download(LORA)
    weights.commit()


@app.function(image=image, volumes={"/weights": weights}, timeout=3600)
def download_2509():
    from huggingface_hub import hf_hub_download, snapshot_download

    snapshot_download(BASE_2509)
    snapshot_download(LORA_2509)
    hf_hub_download(LIGHTNING[0], LIGHTNING[1])
    weights.commit()


@app.cls(image=image, gpu="A100-80GB", volumes={"/weights": weights}, timeout=1800, scaledown_window=120)
class Angles2509:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import DiffusionPipeline
        from huggingface_hub import list_repo_files

        t = time.perf_counter()
        self.pipe = DiffusionPipeline.from_pretrained(BASE_2509, torch_dtype=torch.bfloat16).to("cuda")
        self.pipe.load_lora_weights(LIGHTNING[0], weight_name=LIGHTNING[1], adapter_name="lightning")
        # the camera LoRA's file name is Chinese: take the repo's .safetensors file rather than spelling it out
        name = next(f for f in list_repo_files(LORA_2509) if f.endswith(".safetensors"))
        self.pipe.load_lora_weights(LORA_2509, weight_name=name, adapter_name="angles")
        self.pipe.set_adapters(["lightning", "angles"], adapter_weights=[1.0, 1.0])
        self.pipe.set_progress_bar_config(disable=True)
        # the inpainting pipeline shares the SAME module objects (no copy, no dtype conversion): from_pipe() inside a
        # request ran out of memory on the 80 GB card (a second copy while converting)
        import inspect
        from diffusers import QwenImageEditInpaintPipeline
        names = set(inspect.signature(QwenImageEditInpaintPipeline.__init__).parameters) - {"self"}
        self.inpaint_pipe = QwenImageEditInpaintPipeline(**{k: v for k, v in self.pipe.components.items() if k in names})
        self.inpaint_pipe.set_progress_bar_config(disable=True)
        self.default_sched_config = dict(self.pipe.scheduler.config)  # the 2509 default, for runs without Lightning
        self.load_s = time.perf_counter() - t

    def _lightning_scheduler(self):
        """The 8-step Lightning LoRA was distilled with shift 3 (base_shift = max_shift = log 3, no terminal stretch);
        the 2509 default works out to about 2.0 for our token count (docs/research/qwen-image-edit-parameters-2026-10.md)."""
        import math
        from diffusers import FlowMatchEulerDiscreteScheduler
        return FlowMatchEulerDiscreteScheduler.from_config({
            "base_image_seq_len": 256, "base_shift": math.log(3), "invert_sigmas": False, "max_image_seq_len": 8192,
            "max_shift": math.log(3), "num_train_timesteps": 1000, "shift": 1.0, "shift_terminal": None,
            "stochastic_sampling": False, "time_shift_type": "exponential", "use_beta_sigmas": False,
            "use_dynamic_shifting": True, "use_exponential_sigmas": False, "use_karras_sigmas": False})

    @modal.method()
    def inpaint(self, png: bytes, mask_png: bytes, prompt: str, strength: float = 1.0, steps: int = 8, seed: int = 0,
                lightning: bool = True, cfg: float = 4.0) -> dict:
        """QwenImageEditInpaintPipeline (one image + mask, white = repaint), camera LoRA off. lightning=True: 8-step
        LoRA with its shift-3 scheduler, cfg 1; lightning=False: the full model, default scheduler, true cfg `cfg`."""
        import torch
        from PIL import Image

        ip = self.inpaint_pipe
        if lightning:
            self.pipe.set_adapters(["lightning"], adapter_weights=[1.0])  # the shared transformer carries the LoRAs
            ip.scheduler, true_cfg = self._lightning_scheduler(), 1.0
        else:
            self.pipe.set_adapters(["lightning", "angles"], adapter_weights=[0.0, 0.0])
            ip.scheduler, true_cfg = self.pipe.scheduler.__class__.from_config(self.default_sched_config), cfg
        img = Image.open(io.BytesIO(png)).convert("RGB")
        mask = Image.open(io.BytesIO(mask_png)).convert("L")
        t = time.perf_counter()
        with torch.inference_mode():
            r = ip(image=img, mask_image=mask, prompt=prompt, negative_prompt=" ", true_cfg_scale=true_cfg, strength=strength,
                   num_inference_steps=steps, generator=torch.Generator(device="cuda").manual_seed(seed))
        buf = io.BytesIO()
        r.images[0].save(buf, format="PNG")
        return {"image": buf.getvalue(), "secs": round(time.perf_counter() - t, 1), "load_s": round(self.load_s, 1)}

    @modal.method()
    def edit_blend(self, pngs: list[bytes], mask_png: bytes, prompt: str, steps: int = 8, seed: int = 0) -> dict:
        """Route B: the multi-image pipeline with the original as reference, but at every step everything outside the
        mask is reset to the render, noised to the current level (latent blending), so the model can only paint inside
        the holes. pngs[0] is the render (same size as the output), pngs[1] the reference."""
        import torch
        import torch.nn.functional as F
        from PIL import Image

        self.pipe.set_adapters(["lightning"], adapter_weights=[1.0])
        default_sched = self.pipe.scheduler
        self.pipe.scheduler = self._lightning_scheduler()
        pipe = self.pipe
        imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in pngs]
        render = imgs[0]
        W, H = render.size
        mask = Image.open(io.BytesIO(mask_png)).convert("L").resize((W, H))
        dev, dt = "cuda", pipe.transformer.dtype
        # the render's clean latents, packed like the output latents
        x = pipe.image_processor.preprocess(render, H, W).unsqueeze(2).to(dev, pipe.vae.dtype)
        with torch.inference_mode():
            z0 = pipe._encode_vae_image(x, generator=None)
        c, lh, lw = z0.shape[1], z0.shape[3], z0.shape[4]
        z0 = pipe._pack_latents(z0, 1, c, lh, lw).to(dt)
        # mask on the latent grid (any hole pixel marks its cell), then packed 2x2 like the latents
        m = torch.from_numpy((__import__("numpy").asarray(mask) > 127).astype("float32"))[None, None].to(dev)
        m = F.max_pool2d(m, kernel_size=pipe.vae_scale_factor * 2, stride=pipe.vae_scale_factor * 2)
        m = m[:, :, : lh // 2, : lw // 2].reshape(1, -1, 1).to(dt)
        noise = torch.randn(z0.shape, generator=torch.Generator(device=dev).manual_seed(seed), device=dev, dtype=dt)

        def blend(p, i, t, kw):
            sig = p.scheduler.sigmas[i + 1].to(dev, dt) if i + 1 < len(p.scheduler.sigmas) else torch.tensor(0.0, device=dev, dtype=dt)
            known = (1 - sig) * z0 + sig * noise
            lat = kw["latents"]
            if lat.shape == known.shape:
                kw["latents"] = m * lat + (1 - m) * known
            return kw

        t0 = time.perf_counter()
        with torch.inference_mode():
            r = pipe(image=imgs, prompt=prompt, negative_prompt=" ", true_cfg_scale=1.0, num_inference_steps=steps,
                     generator=torch.Generator(device=dev).manual_seed(seed), callback_on_step_end=blend,
                     callback_on_step_end_tensor_inputs=["latents"])
        pipe.scheduler = default_sched
        buf = io.BytesIO()
        r.images[0].save(buf, format="PNG")
        return {"image": buf.getvalue(), "secs": round(time.perf_counter() - t0, 1), "load_s": round(self.load_s, 1),
                "latent_tokens": int(z0.shape[1]), "masked_share": round(float(m.mean()), 3)}

    @modal.method()
    def edit(self, pngs: list[bytes], prompt: str, steps: int = 8, seed: int = 0) -> dict:
        """Several input images (2509 takes up to 3) and one instruction, camera LoRA off: e.g. a point-cloud render
        from a new angle (image 1) cleaned up in the style of the original panel (image 2)."""
        import torch
        from PIL import Image

        self.pipe.set_adapters(["lightning"], adapter_weights=[1.0])
        default_sched = self.pipe.scheduler
        self.pipe.scheduler = self._lightning_scheduler()
        imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b in pngs]
        torch.cuda.reset_peak_memory_stats()
        t = time.perf_counter()
        with torch.inference_mode():
            r = self.pipe(image=imgs, prompt=prompt, negative_prompt=" ", true_cfg_scale=1.0, num_inference_steps=steps,
                          generator=torch.Generator(device="cuda").manual_seed(seed))
        buf = io.BytesIO()
        r.images[0].save(buf, format="PNG")
        self.pipe.scheduler = default_sched
        self.pipe.set_adapters(["lightning", "angles"], adapter_weights=[1.0, 1.0])
        return {"image": buf.getvalue(), "secs": round(time.perf_counter() - t, 1), "load_s": round(self.load_s, 1),
                "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}

    @modal.method()
    def views(self, png: bytes, prompts: list[str], steps: int = 8, seed: int = 0) -> dict:
        import torch
        from PIL import Image

        self.pipe.set_adapters(["lightning", "angles"], adapter_weights=[1.0, 1.0])
        default_sched = self.pipe.scheduler
        self.pipe.scheduler = self._lightning_scheduler()  # shift 3, as the Lightning LoRA was distilled
        img = Image.open(io.BytesIO(png)).convert("RGB")
        torch.cuda.reset_peak_memory_stats()
        out, secs = [], []
        for p in prompts:
            t = time.perf_counter()
            with torch.inference_mode():
                r = self.pipe(image=[img], prompt=p, negative_prompt=" ", true_cfg_scale=1.0, num_inference_steps=steps,
                              generator=torch.Generator(device="cuda").manual_seed(seed))
            buf = io.BytesIO()
            r.images[0].save(buf, format="PNG")
            out.append(buf.getvalue())
            secs.append(round(time.perf_counter() - t, 1))
        return {"images": out, "secs": secs, "load_s": round(self.load_s, 1),
                "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}


@app.cls(image=image, gpu="A100-80GB", volumes={"/weights": weights}, timeout=1800, scaledown_window=120)
class Angles:
    @modal.enter()
    def load(self):
        import torch
        from diffusers import DiffusionPipeline

        t = time.perf_counter()
        self.pipe = DiffusionPipeline.from_pretrained(BASE, torch_dtype=torch.bfloat16).to("cuda")
        self.pipe.load_lora_weights(LORA, adapter_name="angles")
        self.pipe.set_adapters(["angles"], adapter_weights=[0.9])
        self.pipe.set_progress_bar_config(disable=True)
        self.load_s = time.perf_counter() - t

    @modal.method()
    def views(self, png: bytes, prompts: list[str], steps: int = 40, seed: int = 0, strength: float = 0.9) -> dict:
        import torch
        from PIL import Image

        self.pipe.set_adapters(["angles"], adapter_weights=[strength])
        img = Image.open(io.BytesIO(png)).convert("RGB")
        torch.cuda.reset_peak_memory_stats()
        out, secs = [], []
        for p in prompts:
            t = time.perf_counter()
            with torch.inference_mode():
                r = self.pipe(image=[img], prompt=p, negative_prompt=" ", true_cfg_scale=4.0, num_inference_steps=steps,
                              generator=torch.Generator(device="cuda").manual_seed(seed))
            buf = io.BytesIO()
            r.images[0].save(buf, format="PNG")
            out.append(buf.getvalue())
            secs.append(round(time.perf_counter() - t, 1))
        return {"images": out, "secs": secs, "load_s": round(self.load_s, 1),
                "peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}


@app.local_entrypoint()
def main(path: str, out: str = "qwen_angles", steps: int = 40):
    from pathlib import Path

    res = Angles().views.remote(Path(path).read_bytes(), VIEWS, steps=steps)
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    for k, b in enumerate(res["images"]):
        (d / f"view{k}.png").write_bytes(b)
    print(f"{len(res['images'])} views, per view {res['secs']} s, model load {res['load_s']} s, peak {res['peak_gb']} GB -> {d}")
