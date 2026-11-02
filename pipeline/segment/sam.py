"""SAM 3.1 on the local GPU, the one module that talks to it: the checkpoint, the processor and its confidence
threshold, mixed precision, the text-encoder cache, SAM's private grounding calls, and the lock that keeps the one
GPU single-threaded while the reviews run in parallel threads.

    seg = Segmenter()
    seg.find(img, [("person", 0.45), ...])         per prompt: [(box-size mask, score)] over the box's tiles, holes filled
    seg.instances(tile, [("person", 0.45), ...])   the same on one image SAM takes whole
    seg.zoom(img, box, prompts)                    [(probability on the box's crop, score, prompt)]: crop-size, as a
                                                   box-size array per instance would cost ~3.6 MB on a tall webtoon box
    seg.encode(images); seg.ground(state, prompt, boxes)   text (+ exemplar boxes) grounding on encoded images

SAM 3 resizes every input to a 1008 x 1008 square, so a tall box is cut into square tiles (tiles) and a small
region is enlarged to fill the square (zoom).
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / ".models/sam3/official/sam3.1_multiplex.pt"
SIDE = 1008      # SAM's square input
THRESHOLD = 0.3  # the processor's confidence threshold: instances under it are never returned
BATCH = 4        # images per image-encoder call (encode)


def tiles(h: int, w: int, overlap: float = 0.25) -> list[int]:
    """Top rows of square tiles (side = the box's width) covering a box of height h, overlapping by `overlap`."""
    if h <= w:
        return [0]
    step = max(1, int(w * (1 - overlap)))
    return sorted(set(list(range(0, h - w, step)) + [h - w]))


class Segmenter:
    """One SAM 3.1 processor for a run. Every call holds the lock and runs under inference mode with bfloat16
    autocast (as in Meta's examples)."""

    def __init__(self, threshold: float = THRESHOLD):
        from sam3.model.sam3_image_processor import Sam3Processor
        self.proc = Sam3Processor(_model(), confidence_threshold=threshold)
        self._lock = threading.Lock()
        self._text: dict[str, dict] = {}

    @contextmanager
    def _gpu(self):
        import torch
        with self._lock, torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            yield

    @staticmethod
    def _out(state) -> tuple[np.ndarray, np.ndarray]:
        return state["masks_logits"][:, 0].float().cpu().numpy(), state["scores"].float().cpu().numpy()

    def instances(self, image: Image.Image, prompts: list[tuple[str, float]]) -> list[list[tuple[np.ndarray, float]]]:
        """Per (prompt, min score): every instance at or above the score, as an image-size mask (probability > 0.5,
        holes filled). The image is encoded once for all prompts."""
        from scipy.ndimage import binary_fill_holes
        out = []
        with self._gpu():
            base = self.proc.set_image(image)
            for prompt, thr in prompts:
                probs, scores = self._out(self.proc.set_text_prompt(prompt, base))
                out.append([(binary_fill_holes(p > 0.5), float(s)) for p, s in zip(probs, scores) if s >= thr])
        return out

    def find(self, img: Image.Image, prompts: list[tuple[str, float]],
             rows: list[int | None] | None = None) -> list[tuple[int, np.ndarray, float]]:
        """instances over a whole box, tile by tile (tiles), each mask placed back on the box: [(prompt index,
        box-size mask, score)], tile by tile, then prompt by prompt (the order callers merge in). rows: per prompt the
        row it is asked around (only on the tiles holding it), or None for every tile."""
        w, h = img.size
        out: list[tuple[int, np.ndarray, float]] = []
        for top in tiles(h, w):
            tile = img.crop((0, top, w, min(h, top + w)))
            ask = [k for k in range(len(prompts)) if rows is None or rows[k] is None or top <= rows[k] < top + tile.height]
            if not ask:
                continue
            for k, hits in zip(ask, self.instances(tile, [prompts[k] for k in ask])):
                for m, s in hits:
                    full = np.zeros((h, w), bool)
                    full[top:top + m.shape[0]] = m
                    out.append((k, full, s))
        return out

    def zoom(self, img: Image.Image, box, prompts) -> list[tuple[np.ndarray, float, str]]:
        """SAM on the crop of `box` enlarged to fill its input (pasted top-left on white): per instance its
        probability resized back onto the crop (float, crop size), its score and its prompt, prompts in order."""
        crop = img.crop(box)
        s = SIDE / max(crop.size)
        big = crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS)
        canvas = Image.new("RGB", (SIDE, SIDE), (255, 255, 255))
        canvas.paste(big, (0, 0))
        out = []
        with self._gpu():
            base = self.proc.set_image(canvas)
            for prompt in prompts:
                probs, scores = self._out(self.proc.set_text_prompt(prompt, base))
                for p, sc in zip(probs, scores):
                    prob = np.asarray(Image.fromarray(p[: big.height, : big.width].astype(np.float32)).resize(crop.size, Image.BILINEAR))
                    out.append((prob, float(sc), prompt))
        return out

    def encode(self, images: list[Image.Image]) -> list[dict]:
        """One grounding state per image; the image encoder runs on batches of BATCH images instead of one call
        each."""
        states = []
        with self._gpu():
            for s in range(0, len(images), BATCH):
                chunk = images[s: s + BATCH]
                out = self.proc.set_image_batch(chunk)["backbone_out"]
                for i, im in enumerate(chunk):
                    states.append({"original_height": im.height, "original_width": im.width,
                                   "backbone_out": _slice(out, i, len(chunk))})
        return states

    def ground(self, state: dict, prompt: str, boxes: list[list[float]] | None = None) -> tuple[np.ndarray, np.ndarray]:
        """(probabilities, scores) of the instances of `prompt` on an encoded image; boxes (normalised cx, cy, w, h):
        positive exemplar boxes on it, all in one call (add_geometric_prompt reruns the detection head per box)."""
        import torch
        with self._gpu():
            if prompt not in self._text:  # the text encoder once per prompt and run
                self._text[prompt] = self.proc.model.backbone.forward_text([prompt], device=self.proc.device)
            state["backbone_out"].update(self._text[prompt])
            state["geometric_prompt"] = self.proc.model._get_dummy_prompt()
            if boxes:
                b = torch.tensor(boxes, device=self.proc.device, dtype=torch.float32).view(-1, 1, 4)
                state["geometric_prompt"].append_boxes(b, torch.ones((len(boxes), 1), device=self.proc.device, dtype=torch.bool))
            return self._out(self.proc._forward_grounding(state))


def _model():
    """SAM 3.1's image model on the GPU, its weights read from the memory-mapped checkpoint straight into it. sam3's
    own loader (checkpoint_path=) builds the model on the CPU and reads the 3.5 GB checkpoint into RAM before moving
    it, and Windows keeps that memory committed for the run: 11.0 GB of commit after loading, against 5.4 here."""
    import torch
    from sam3 import build_sam3_image_model
    model = build_sam3_image_model(checkpoint_path=None, load_from_HF=False)
    ckpt = torch.load(CKPT, map_location="cpu", weights_only=True, mmap=True)
    ckpt = ckpt.get("model", ckpt)
    missing, _ = model.load_state_dict({k.replace("detector.", ""): v for k, v in ckpt.items() if "detector" in k},
                                       strict=False)
    if missing:
        print(f"SAM 3.1: weights missing from {CKPT.name}: {missing}")
    return model


def _slice(x, i: int, n: int):
    """Image i of a batched backbone output (tensors with the batch on dim 0)."""
    import torch
    if torch.is_tensor(x):
        return x[i: i + 1] if x.dim() and x.shape[0] == n else x
    if isinstance(x, dict):
        return {k: _slice(v, i, n) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(_slice(v, i, n) for v in x)
    return x
