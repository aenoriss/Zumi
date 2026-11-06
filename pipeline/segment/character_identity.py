"""Character identity (decisions.md section 12, as built 2026-11-05): which character cards of an episode are one
character, across its boxes and across the episodes of a series, and a voice description for each speaking character.
Steps 7 and 8 of episode.py; both read only what earlier steps saved (cards.json, speakers.json) and the .zumi.

7. Identity (identity_step).
   a. Every character card (a cards.json layer of kind "character") embedded on its colour cut-out by three frozen
      encoders, CCIP caformer_b36, DINOv3 ViT-L/16 and Magiv2's crop embedder, each unit length; cached per card PNG
      in <episode>/identity/feats.npz. Similarity: the mean of the three cosines.
   b. Appearance groups (witness_link): average linkage, two cards of one frame never one group, and a merge needs
      strong card-to-card matches. On the 12 labelled episodes (498 speaking cards, each series held out once) 11.2%
      of speaking cards land in the wrong group, against 15.3% for plain average linkage.
   c. Pass 1, when the series has no cast yet: one Claude Sonnet 5.5 call reads the episode (every box with each card
      outlined and tagged by its group, the script with the speaker links, each group's sheet), edits the groups by
      story evidence (merge, split, move) and names them. 4.6% and 5.4% wrong in two runs over the 12 episodes. The
      final groups become the series cast.
   d. Pass 2, when the series has a cast from earlier episodes: each group is matched by appearance to a cast character
      (CCIP + Magiv2, the mean of each card's 3 best matches, at least 0.80, never two groups sharing a frame on one
      character), then one Sonnet call corrects the assignment with the cast sheet beside the episode. 81.1% of 212
      speaking cards right by appearance, 94.3% after the reader (5 episode pairs). Groups it calls NEW join the cast;
      matched cards add no exemplars (section 12: matches never self-add, or the cast drifts).
   A look the story treats as separate (heavy makeup against none, a disguise) is a separate character (user,
   2026-11-04); its voice is shared (8).
   e. The same call reviews the speaker links (speaker_edits, user 2026-11-05): the script marks `check` every
      balloon linked without a clear tail (the only or the nearest figure in the frame, a tail shared by a stack or
      tied between two cards, no card, several cards at once; CHECK_CONF) and the reader decides each one, tail
      first, then the turns of the conversation; it may also correct any other link it is sure of. The speaker can
      be any card of the episode (a voice from the box before or after) or off-panel. The corrections go into the
      boxes' speaker records (apply_speakers; the earlier link kept under "was"), and speakers.assign_box keeps them
      when the rules run again. On 302 labelled balloons of 3 held-out episodes, fresh: rules 85.8%, after the
      reader 90-92% (2026-11-06).
   Writes <episode>/identity/identity.json, stamped with the cards and speakers it read: a rerun on the same layers
   pays nothing. The series cast lives in <run>/cast/<series>/ (cast.json, exemplars.npz, card thumbnails, voices/),
   beside the run's dataset/. A rerun founds the episode's characters again under new ids and gives them back the
   voices they had, by the cards they share (inherit_voices).
8. Voices (voices_step): every character of the episode with at least MIN_LINES lines and no voice in the cast gets the
   description Gemini 3.8 Flash TTS voice design takes (display name, gender, language code, one or two sentences of
   permanent traits, no age for a minor: the model refuses it; emotion goes per line), from one Sonnet call that
   reads the episode. Another look of a person links to that person's voice (same_voice_as, user 2026-11-04). Then
   design_voices creates each described voice once on Inworld TTS-2 (inworld.design_voice: designed from the
   description with the character's own lines as the preview script, published as a voice id; its sample in
   <cast>/voices/K<n>.wav), and record_lines speaks every balloon with a speaker in its character's voice, the
   delivery note from the balloon's kind and Transcribe's reading of the drawing (style_of) and the scene's
   previous balloons as context, to <episode>/audio/<pid>.b<bubble>.wav with audio/lines.json as the index: a line
   recorded with the same words, voice and note is kept, one whose balloon lost its speaker is dropped; a balloon
   of marks alone ("...") is not voiced. episode_audio joins the lines into audio/episode.mp3 for listening.
   Gemini 3.8 Flash TTS was the first backend (2026-11-05): its 100 requests a day on the paid tier and the
   flatter delivery sent it away (user, 2026-11-06); its voice ids stay in the cast as id_gemini.

Paid calls go through openrouter.ask_json and inworld under the shared daily cap. Measured (P&C 39, 2026-11-05/06):
identity 0.15-0.22 USD, voices reader 0.11, a voice design about 0.015, a line about 0.0025 (list price, the
delivery note's characters billed too).

    uv run python character_identity.py <episode.zumi> <episode out dir> [--series NAME] [--no-voices]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path

os.environ.setdefault("HF_HOME", "D:/hf-cache")  # C: is full; the encoders live on D:

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import inworld as IW  # noqa: E402
from boxstore import Box, Episode  # noqa: E402
from openrouter import BudgetExceeded, Truncated, ask_json, image_part  # noqa: E402
from spend import paid_map  # noqa: E402

MODEL = "anthropic/claude-sonnet-5.5"
REASONING = "high"       # at high the reader stops thinking on its own (2-8k of its 14k tokens used, 2026-11-05); at
                         # xhigh it thought through the whole 24k budget and gave no answer (0.35 USD lost): a higher
                         # effort needs a budget of 40k+ tokens, 3x the cost a call
ANSWER_TOKENS = 8000
# witness link, the settings the held-out search picked for 5 of the 6 series (the sixth, unOrdinary, rho 0.1)
CUT, WITNESS, FRAC, RHO = 0.525, 0.675, 0.34, 0.25
MATCH_ENC, TOP_K, MATCH_MIN = ("ccipb36", "magiv2"), 3, 0.80
EXEMPLARS = 32            # cards kept per cast character (section 12), spread over its appearances
LOOSE = 0.6               # a card whose mean similarity to the rest of its group is below this is tagged "?"
PAGE_H = 2200             # boxes stacked into page images up to this height
MIN_LINES = 3             # lines a character speaks in the episode to get a voice
CHECK_CONF = 0.75         # a speaker link at or under this confidence (the rules without a tail to a card: the only
                          # figure in the frame, the nearest figure, a shared tail, no card in the box) is marked
                          # `check` in the script: the reader decides each one. The single-figure rule is 98% right
                          # against drawn-card labels but is where a speaker drawn in the box before or after gets the
                          # wrong card (5 of 33 misses, 2026-11-06), so it is checked too; the tail rules are not.
                          # So is a link to several cards at once (a tail at two touching figures: 34 of 776 balloons,
                          # 3 of them a real chorus by the labels): the reader names the one who speaks
PAL = [(78, 121, 167), (242, 142, 43), (225, 87, 89), (118, 183, 178), (89, 161, 79), (237, 201, 72),
       (176, 122, 161), (255, 157, 167), (156, 117, 95), (186, 176, 172), (31, 119, 180), (255, 127, 14),
       (44, 160, 44), (214, 39, 40), (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
       (188, 189, 34), (23, 190, 207)]


# ---------------------------------------------------------------- the episode's cards

@dataclass
class Card:
    id: str                 # "<pid>/<png>", as speakers.json names it with its box
    box: int                # box index
    frame: str              # "<pid>#<frame>"
    rank: int               # the frame's place in the episode's reading order
    bbox: tuple             # in its box's pixels
    png: Path
    lines: list             # what the speaker links give it


@dataclass
class Cards:
    cards: list[Card]
    script: list[tuple]     # every balloon with text in reading order: (box, kind, [card index], speaker_kind, text,
                            # check: the link was made without a tail to a card, for the reader to decide)
    stamp: str              # the cards.json and speakers.json files it was read from

    def __len__(self):
        return len(self.cards)


def read_cards(ep: Episode, n_boxes: int) -> Cards:
    """Every character card of the boxes that have layers, in reading order (box, then frame by speakers.reading_order),
    with what the speaker step links to it."""
    from speakers import reading_order
    cards, script, h, rank, by_id, later = [], [], hashlib.sha1(), 0, {}, []
    for i in range(n_boxes):
        box = ep.box(i)
        sc = box.scene()
        if sc is None:
            continue
        h.update((box.cards_stamp() or "").encode())
        f = box.frames()
        order = reading_order(f.masks) if f and f.masks else [0]
        place = {k: rank + n for n, k in enumerate(order)}
        rank += len(order)
        for l in sc.layers:
            if l.kind != "character":
                continue
            by_id[f"{box.pid}/{l.key}"] = len(cards)
            fr = l.frame if isinstance(l.frame, int) else 0
            cards.append(Card(f"{box.pid}/{l.key}", i, f"{box.pid}#{fr}", place.get(fr, rank), l.bbox, l.path, []))
        recs = box.speakers() or []
        h.update(json.dumps(recs, sort_keys=True).encode())
        for r in sorted(recs, key=lambda r: r["order"]):
            text = (r.get("text") or "").strip()
            if not text:
                continue
            # a speaker is a card key of this box, or "<pid>/<key>" for a card of another box (the reader's
            # corrections: a voice carrying over from the box before); the latter may not be read yet
            who = []
            for s in r.get("speakers") or []:
                full = s if "/" in s else f"{box.pid}/{s}"
                if full in by_id:
                    who.append(by_id[full])
                elif "/" in s:
                    later.append((full, text, len(script)))
            for n in who:
                cards[n].lines.append(text)
            script.append((i, r.get("kind"), who, r.get("speaker_kind"), text, r.get("rule") != "reader" and
                           (float(r.get("confidence") or 0) <= CHECK_CONF or len(r.get("speakers") or []) > 1)))
    for full, text, k in later:
        if full in by_id:
            cards[by_id[full]].lines.append(text)
            script[k][2].append(by_id[full])
    order = sorted(range(len(cards)), key=lambda n: (cards[n].rank, n))  # reading order across boxes
    remap = {old: new for new, old in enumerate(order)}
    script = [(b, k, [remap[n] for n in who], sk, t, chk) for b, k, who, sk, t, chk in script]
    return Cards([cards[n] for n in order], script, h.hexdigest()[:16])


# ---------------------------------------------------------------- 7a. the encoders

def _rgba(path) -> np.ndarray:
    return cv2.imread(str(path), cv2.IMREAD_UNCHANGED)  # BGRA


def _square(im: np.ndarray, side: int) -> np.ndarray:
    """The card on mid grey (its transparent part), padded square and resized, BGR float."""
    a = im[..., 3:4].astype(np.float32) / 255
    bgr = im[..., :3].astype(np.float32) * a + 128 * (1 - a)
    h, w = bgr.shape[:2]
    s = max(h, w)
    pad = np.full((s, s, 3), 128, np.float32)
    pad[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = bgr
    return cv2.resize(pad, (side, side), interpolation=cv2.INTER_AREA)


def _encoders() -> dict:
    """name -> (constructor, input side, normalisation mean/std). Weights in the HF cache on D:."""
    import torch
    import torch.nn.functional as F

    class AttnPool(torch.nn.Module):
        """CLIP's AttentionPool2d: the mean token, plus positions, attends over the grid; projected to out_dim."""

        def __init__(self, grid, dim, heads, out_dim):
            super().__init__()
            self.positional_embedding = torch.nn.Parameter(torch.zeros(grid * grid + 1, dim))
            self.k_proj, self.q_proj, self.v_proj = (torch.nn.Linear(dim, dim) for _ in range(3))
            self.c_proj = torch.nn.Linear(dim, out_dim)
            self.heads = heads

        def forward(self, x):
            x = x.flatten(2).permute(2, 0, 1)
            x = torch.cat([x.mean(0, keepdim=True), x]) + self.positional_embedding[:, None].to(x.dtype)
            out, _ = F.multi_head_attention_forward(
                x[:1], x, x, x.shape[-1], self.heads, q_proj_weight=self.q_proj.weight,
                k_proj_weight=self.k_proj.weight, v_proj_weight=self.v_proj.weight, in_proj_weight=None,
                in_proj_bias=torch.cat([self.q_proj.bias, self.k_proj.bias, self.v_proj.bias]), bias_k=None,
                bias_v=None, add_zero_attn=False, dropout_p=0, out_proj_weight=self.c_proj.weight,
                out_proj_bias=self.c_proj.bias, use_separate_proj_weight=True, training=False, need_weights=False)
            return out[0]

    class Ccip(torch.nn.Module):
        """CCIP caformer_b36-24 (deepghs/ccip_onnx; character similarity on anime art, F1 0.941 on its own test)."""

        def __init__(self):
            super().__init__()
            import timm
            from huggingface_hub import hf_hub_download
            from timm.models.metaformer import checkpoint_filter_fn
            sd = torch.load(hf_hub_download("deepghs/ccip_onnx", "ccip-caformer_b36-24/model.ckpt"),
                            map_location="cpu", weights_only=True)
            pre = "module._orig_mod.feature.backbone."
            self.caformer = timm.create_model("caformer_b36", pretrained=False, num_classes=2)  # head unused
            cf = {k[len(pre + "caformer."):]: v for k, v in sd.items() if k.startswith(pre + "caformer.")}
            self.caformer.load_state_dict(checkpoint_filter_fn(cf, self.caformer), strict=True)
            pool = {k[len(pre + "attnpool."):]: v for k, v in sd.items() if k.startswith(pre + "attnpool.")}
            n, dim = pool["positional_embedding"].shape
            self.attnpool = AttnPool(int(round((n - 1) ** 0.5)), dim, dim // 64, pool["c_proj.weight"].shape[0])
            self.attnpool.load_state_dict(pool)

        def forward(self, x):
            return self.attnpool(self.caformer.forward_features(x))

    class Dinov3(torch.nn.Module):
        def __init__(self):
            super().__init__()
            import timm
            self.m = timm.create_model("vit_large_patch16_dinov3.lvd1689m", pretrained=True, num_classes=0)

        def forward(self, x):
            return self.m.forward_features(x)[:, 0]  # the CLS token after the norm

    class Magiv2(torch.nn.Module):
        """Magiv2's crop embedder (ragavsachdeva/magiv2, ViTMAE-B/16 trained for manga character identity) in timm's
        ViT: the CLS token after the final norm, no masking."""

        def __init__(self):
            super().__init__()
            import timm
            from huggingface_hub import hf_hub_download
            sd = torch.load(hf_hub_download("ragavsachdeva/magiv2", "pytorch_model.bin"), map_location="cpu",
                            weights_only=True)
            sd = {k[len("crop_embedding_model."):]: v for k, v in sd.items() if k.startswith("crop_embedding_model.")}
            self.m = timm.create_model("vit_base_patch16_224", pretrained=False, num_classes=0,
                                       norm_layer=partial(torch.nn.LayerNorm, eps=1e-12))
            new = {"cls_token": sd["embeddings.cls_token"], "pos_embed": sd["embeddings.position_embeddings"],
                   "patch_embed.proj.weight": sd["embeddings.patch_embeddings.projection.weight"],
                   "patch_embed.proj.bias": sd["embeddings.patch_embeddings.projection.bias"],
                   "norm.weight": sd["layernorm.weight"], "norm.bias": sd["layernorm.bias"]}
            for i in range(12):
                p, b = f"encoder.layer.{i}.", f"blocks.{i}."
                for part in ("weight", "bias"):
                    new[b + f"attn.qkv.{part}"] = torch.cat(
                        [sd[p + f"attention.attention.{q}.{part}"] for q in ("query", "key", "value")])
                    new[b + f"attn.proj.{part}"] = sd[p + f"attention.output.dense.{part}"]
                    new[b + f"norm1.{part}"] = sd[p + f"layernorm_before.{part}"]
                    new[b + f"norm2.{part}"] = sd[p + f"layernorm_after.{part}"]
                    new[b + f"mlp.fc1.{part}"] = sd[p + f"intermediate.dense.{part}"]
                    new[b + f"mlp.fc2.{part}"] = sd[p + f"output.dense.{part}"]
            self.m.load_state_dict(new, strict=True)

        def forward(self, x):
            return self.m.forward_features(x)[:, 0]

    imagenet = ([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    # DINOv3 in float16 overflows to NaN on every card (2026-11-04); bfloat16 has float32's range
    return {"ccipb36": (lambda: Ccip().eval().cuda().half(), 384, ([0.5] * 3, [0.5] * 3)),
            "dinov3": (lambda: Dinov3().eval().cuda().to(torch.bfloat16), 224, imagenet),
            "magiv2": (lambda: Magiv2().eval().cuda().half(), 224, imagenet)}


ENCODERS = ("ccipb36", "dinov3", "magiv2")


def embed(cards: Cards, cache: Path) -> dict[str, np.ndarray]:
    """Each encoder's unit embeddings of the cards (n x d), cached by card PNG content: only new cards load a model."""
    import torch
    import torch.nn.functional as F
    keys = [hashlib.sha1(c.png.read_bytes()).hexdigest()[:16] for c in cards.cards]
    old = dict(np.load(cache)) if cache.exists() else {}
    out = {}
    for name in ENCODERS:
        todo = [n for n, k in enumerate(keys) if f"{name}/{k}" not in old]
        if todo:
            make, side, (mean, std) = _encoders()[name]
            model = make()
            dtype = next(model.parameters()).dtype
            m, s = np.array(mean, np.float32) * 255, np.array(std, np.float32) * 255
            with torch.no_grad():
                for a in range(0, len(todo), 16):
                    batch = todo[a:a + 16]
                    x = np.stack([(_square(_rgba(cards.cards[n].png), side)[..., ::-1] - m) / s for n in batch])
                    f = F.normalize(model(torch.from_numpy(x).permute(0, 3, 1, 2).cuda().to(dtype)).float(), dim=1)
                    for n, v in zip(batch, f.cpu().numpy()):
                        old[f"{name}/{keys[n]}"] = v
                    print(f"  {name}: {min(a + 16, len(todo))}/{len(todo)} cards", flush=True)
            del model
            torch.cuda.empty_cache()
        out[name] = np.stack([old[f"{name}/{k}"] for k in keys]) if keys else np.zeros((0, 1), np.float32)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, **old)
    return out


def similarity(feats: dict) -> np.ndarray:
    return sum(v @ v.T for v in feats.values()) / len(feats)


def match_features(feats: dict, rows=slice(None)) -> np.ndarray:
    """The pass 2 match space: CCIP and Magiv2 joined, unit length."""
    x = np.concatenate([feats[k][rows] for k in MATCH_ENC], 1)
    return x / np.linalg.norm(x, axis=1, keepdims=True)


# ---------------------------------------------------------------- 7b. appearance groups

def witness_link(s: np.ndarray, frame: list[str], cut: float = CUT, witness: float = WITNESS, frac: float = FRAC,
                 rho: float = RHO) -> np.ndarray:
    """Average linkage on similarity s, merging the closest pair of groups while their mean similarity is above
    1 - cut, where a merge is allowed only if (1) the two groups share few frames (a shared frame means two people;
    a share above rho of their frames, or more than one, vetoes it) and (2) at least max(1, frac * smaller size) cards
    of the smaller group have a strong match (>= witness) in the other. Two look-alike people drawn in one style score
    uniformly mediocre across all their pairs; two pieces of one person hold some pairs at a similar pose and scale
    that score high. Returns a group id per card."""
    n = len(frame)
    if n == 0:
        return np.zeros(0, int)
    _, fidx = np.unique(np.array(frame), return_inverse=True)
    sim = s.astype(float).copy()
    np.fill_diagonal(sim, 0.0)
    ssum = sim.copy()
    near = s.astype(float).copy()                       # card x group: the card's best match in the group
    np.fill_diagonal(near, -np.inf)
    size = np.ones(n)
    cnt = np.zeros((n, fidx.max() + 1))
    cnt[np.arange(n), fidx] = 1
    alive = np.ones(n, bool)
    label = np.arange(n)
    while alive.sum() > 1:
        idx = np.where(alive)[0]
        p = (cnt[idx] > 0).astype(float)
        shared = p @ p.T
        nf = p.sum(1)
        ok = (shared == 0) | ((shared / np.sqrt(nf[:, None] * nf[None, :]) <= rho + 1e-9) & (shared <= 1))
        member = (label[:, None] == idx[None, :]).astype(float)
        strong = member.T @ (near[:, idx] >= witness)   # strong[A, B]: cards of A with a strong match in B
        sz = size[idx]
        got = np.where(sz[:, None] < sz[None, :], strong,
                       np.where(sz[:, None] > sz[None, :], strong.T, np.maximum(strong, strong.T)))
        ok &= got >= np.maximum(1.0, frac * np.minimum(sz[:, None], sz[None, :])) - 1e-9
        d = 1 - ssum[np.ix_(idx, idx)] / (sz[:, None] * sz[None, :])
        d[~ok] = np.inf
        np.fill_diagonal(d, np.inf)
        a, b = divmod(int(np.argmin(d)), len(idx))
        if not d[a, b] <= cut:
            break
        a, b = idx[a], idx[b]
        ssum[a] += ssum[b]; ssum[:, a] += ssum[:, b]; ssum[a, a] = 0
        near[:, a] = np.maximum(near[:, a], near[:, b])
        size[a] += size[b]; cnt[a] += cnt[b]
        alive[b] = False
        label[label == b] = a
        near[label == a, a] = -np.inf
    return label


def number_groups(g: np.ndarray) -> np.ndarray:
    """Groups renumbered 1.. by first appearance (the cards are in reading order)."""
    order = {}
    for k in g:
        order.setdefault(int(k), len(order) + 1)
    return np.array([order[int(k)] for k in g], int)


# ---------------------------------------------------------------- the reader's material

def _font(size: int):
    for f in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def pages(chapter, cards: Cards, tag, colour) -> list[Image.Image]:
    """The episode's original boxes (from the .zumi, nothing inpainted) stacked into images up to PAGE_H tall, each
    card outlined in colour(n) and tagged tag(n), each box headed with its number."""
    f_tag, f_box = _font(22), _font(18)
    by_box = {}
    for n, c in enumerate(cards.cards):
        by_box.setdefault(c.box, []).append(n)
    tiles = []
    for b in range(len(chapter)):
        im = chapter.image(b).convert("RGB")
        d = ImageDraw.Draw(im)
        for n in by_box.get(b, []):
            x0, y0, x1, y1 = [int(v) for v in cards.cards[n].bbox]
            col = colour(n)
            d.rectangle([x0, y0, x1, y1], outline=col, width=4)
            t = tag(n)
            d.rectangle([x0, y0, x0 + d.textlength(t, font=f_tag) + 10, y0 + 28], fill=col)
            d.text((x0 + 5, y0 + 2), t, fill=(255, 255, 255), font=f_tag)
        tile = Image.new("RGB", (im.width, im.height + 26), (30, 30, 30))
        ImageDraw.Draw(tile).text((6, 3), f"box {b}", fill=(230, 230, 230), font=f_box)
        tile.paste(im, (0, 26))
        tiles.append(tile)
    out, cur, h = [], [], 0
    for t in tiles + [None]:
        if cur and (t is None or h + t.height > PAGE_H):
            page = Image.new("RGB", (max(x.width for x in cur), h), (255, 255, 255))
            y = 0
            for x in cur:
                page.paste(x, (0, y)); y += x.height
            out.append(page)
            cur, h = [], 0
        if t is not None:
            cur.append(t); h += t.height
    return out


def sheet(pngs: list, captions: list[str], cols: int = 8) -> Image.Image:
    """Card thumbnails on grey, captioned, cols to a row."""
    thumbs = []
    for p, cap in zip(pngs, captions):
        c = Image.open(p).convert("RGBA")
        bg = Image.new("RGBA", c.size, (128, 128, 128, 255))
        bg.alpha_composite(c)
        bg = bg.convert("RGB")
        bg.thumbnail((180, 180))
        t = Image.new("RGB", (190, 214), (30, 30, 30))
        t.paste(bg, ((190 - bg.width) // 2, 4))
        ImageDraw.Draw(t).text((6, 190), cap, fill=(230, 230, 230), font=_font(15))
        thumbs.append(t)
    out = Image.new("RGB", (cols * 190, max(1, (len(thumbs) + cols - 1) // cols) * 214), (20, 20, 20))
    for j, t in enumerate(thumbs):
        out.paste(t, ((j % cols) * 190, (j // cols) * 214))
    return out


def script_md(cards: Cards, label) -> str:
    """Every balloon in reading order: box, kind, the speaker card(s) with label(n), `check` on a link made without
    a tail to a card, the text."""
    rows = []
    for b, kind, who, sk, text, chk in cards.script:
        sp = ", ".join(f"c{n} ({label(n)})" for n in who) if who else \
            {"off_panel": "off-panel", "nobody": "nobody"}.get(sk, "?")
        rows.append(f"- box {b} · {kind} · {sp}{' · check' if chk else ''}: \"{text}\"")
    return "\n".join(rows)


def _ask(task: str, parts: list[tuple[str, Image.Image | str]], tag: str, save: Path) -> tuple[dict, float]:
    """One reader call: the task, then each named part (an image or a text), the reply a JSON object. The material is
    saved under `save` as the model saw it, with the reply."""
    save.mkdir(parents=True, exist_ok=True)
    content = [{"type": "text", "text": task}]
    for name, p in parts:
        if isinstance(p, Image.Image):
            p.save(save / name)
            content += [{"type": "text", "text": f"{name}:"}, image_part(p)]
        else:
            (save / name).write_text(p, encoding="utf-8")
            content.append({"type": "text", "text": f"{name}:\n{p}"})
    (save / "task.md").write_text(task, encoding="utf-8")
    reply, cost = ask_json(MODEL, content, tag, ANSWER_TOKENS, REASONING, brief=False)
    (save / "reply.json").write_text(json.dumps({"cost": cost, **reply}, indent=1, ensure_ascii=False),
                                     encoding="utf-8")
    print(f"  reader: {cost:.3f} USD", flush=True)
    return reply, cost


# ---------------------------------------------------------------- 7c. pass 1

PASS1_TASK = """# Task: polish a character grouping by reading the story

You get one comic episode and a proposed grouping of its character cards. A card is one figure in one panel. The grouping comes from an appearance-only algorithm: it puts cards that look alike together. It makes mistakes:

- it merges different people who look alike, such as the same uniform or the same drawing style;
- it splits one person across groups when their look changes, such as different clothes or a different scene, an odd pose, a close-up or a tiny figure.

Your job is to fix the grouping **the way an attentive reader would**: by following the story.

## Material (below, in this order)
- `page-NN.png` (read every one of them, in order): the episode in reading order, top to bottom, several boxes per image. Every character card is outlined and tagged `G<group> c<card>`. A `?` marks a card that is only loosely attached to its group.
- `script.md`: every balloon in reading order, with the card the pipeline thinks speaks it. A link made by a tail pointing at a card is right about 95% of the time. A balloon marked `check` was linked without one (the only figure in the frame, the nearest figure, a tail shared by a stack of balloons, no card in the box), or to several cards at once (a tail at two figures that touch): the usual mistake there is a speaker drawn in another frame or box, or off-panel.
- `cast.md` and `G<k>.png`: each proposed group's cards as thumbnails, and the lines they speak.

## How to work
1. Read ALL the pages in order, with the script beside them. Follow the story: who is where, who talks to whom, who is called by what name (a name called out names the person addressed, not the speaker), who reacts to whom, scene changes, outfits.
2. Look at the cast sheets, and check each group against the story. Does every card in it belong to the same character? Is the same character spread over several groups?
3. One convention for this task: a character shown in a deliberately different look that the story treats as a separate appearance (a transformation, heavy makeup against none, a disguise) counts as a separate character. Keep each such look in its own group, and do not merge the looks, even when the story makes clear it is the same person underneath.
4. Propose only edits you can support with story evidence: names, dialogue, scene continuity, who is present. Appearance can support story evidence, but appearance alone is not enough. The algorithm already used appearance.
5. The script's speaker links are part of what you check. While reading, when the story makes clear that a balloon is said by a different character than the card linked (the linked card is the one addressed, the balloon continues another character's speech, the reply makes no sense from the linked card...), report it under `speakers`. The pipeline only links within a frame; a speaker is often drawn elsewhere: in another frame of the box, or in the box before or after (a voice carrying over, a reply across a cut). Name the character's card there, any `c<n>` of the episode. `off-panel` only when the speaker is drawn nowhere in the episode. Decide EVERY balloon marked `check`: list each one under `speakers`, with `said_by` the linked card itself when the link is right. A balloon linked to several cards is said by ONE of them. Decide which in two steps: first look at the balloon's tail in the page image, the pointed end of the balloon, which aims at the speaker's mouth or figure; then check that reading against the turns of the conversation (who spoke before, who is answered, who is addressed) and the story. When the two agree, that is the speaker; when the tail is ambiguous (figures touching where it points, no tail), the turns decide. Name that one card; give several cards only for a real chorus, several characters saying the same words together. The same two steps settle any balloon whose linked card looks wrong. For the other balloons, report only what you are sure of.

## Output
Reply with ONE JSON object, exactly this shape:

```json
{
  "edits": [
    {"op": "merge", "groups": ["G2", "G9"], "evidence": "box 12 and box 40: ..."},
    {"op": "split", "group": "G3", "cards": ["c14", "c20"], "evidence": "..."},
    {"op": "move", "card": "c34", "to": "G5", "evidence": "..."},
    {"op": "move", "card": "c51", "to": "new", "evidence": "..."}
  ],
  "names": {"G1": "the name the story gives this character, or a short description", "G2": "..."},
  "speakers": [
    {"box": 14, "line": "the balloon's first words", "card": "c94", "said_by": "c92", "evidence": "..."},
    {"box": 20, "line": "...", "card": "c130", "said_by": "off-panel", "evidence": "..."}
  ],
  "notes": "anything uncertain"
}
```

- **merge** joins whole groups (one character).
- **split** takes the listed cards out of a group into one new group of their own.
- **move** puts one card into another group, or into a new group of its own (`"to": "new"`).
- **speakers**: every `check` balloon, and any other balloon whose speaker link is wrong (`card`: the linked card, `said_by`: the card that says it; the same card confirms the link).

Edits are applied in order: merges, then splits, then moves. When unsure, leave the grouping and the links as they are: a wrong edit costs as much as a missed one.
"""


def apply_edits(groups: np.ndarray, edits: list[dict]) -> np.ndarray:
    """The reader's edits on the groups: merges, then splits, then moves; a malformed edit is skipped and printed."""
    g = np.array(groups)
    num = lambda s: int(str(s).lstrip("Gg"))  # noqa: E731
    card = lambda s: int(str(s).lstrip("Cc"))  # noqa: E731
    rank = {"merge": 0, "split": 1, "move": 2}
    for e in sorted(edits, key=lambda e: rank.get(e.get("op"), 9)):
        try:
            if e["op"] == "merge":
                gs = [num(x) for x in e["groups"]]
                for x in gs[1:]:
                    g[g == x] = gs[0]
            elif e["op"] == "split":
                new = g.max() + 1
                for c in e["cards"]:
                    g[card(c)] = new
            elif e["op"] == "move":
                g[card(e["card"])] = g.max() + 1 if str(e["to"]).lower() == "new" else num(e["to"])
        except (KeyError, ValueError, IndexError, TypeError) as err:
            print(f"  skipped a malformed edit {e}: {err}")
    return g


def _loose(s: np.ndarray, G: np.ndarray) -> np.ndarray:
    out = np.zeros(len(G), bool)
    for i in range(len(G)):
        mates = [j for j in range(len(G)) if G[j] == G[i] and j != i]
        out[i] = bool(mates) and s[i, mates].mean() < LOOSE
    return out


def pass1(chapter, cards: Cards, s: np.ndarray, save: Path, tag: str) -> tuple[np.ndarray, dict, dict]:
    """Groups by appearance, then the reader's edits. Returns (final group per card, {group: name}, reply)."""
    G = number_groups(witness_link(s, [c.frame for c in cards.cards]))
    loose = _loose(s, G)
    parts = [(f"page-{k:02d}.png", p) for k, p in enumerate(
        pages(chapter, cards, lambda n: f"G{G[n]} c{n}" + (" ?" if loose[n] else ""),
              lambda n: PAL[(G[n] - 1) % len(PAL)]), 1)]
    parts.append(("script.md", script_md(cards, lambda n: f"G{G[n]}")))
    md = [f"# Proposed groups ({G.max()} groups, {len(cards)} character cards)\n"]
    sheets = []
    for k in range(1, G.max() + 1):
        mem = [n for n in range(len(cards)) if G[n] == k]
        lines = [t for n in mem for t in cards.cards[n].lines][:8]
        md.append(f"## G{k}: {len(mem)} cards" + (" (16 shown)" if len(mem) > 16 else "") + "\ncards: "
                  + ", ".join(f"c{n}{'?' if loose[n] else ''} (box {cards.cards[n].box})" for n in mem)
                  + ("\nlines: " + " / ".join(f'"{t}"' for t in lines) if lines else "") + "\n")
        sheets.append((f"G{k}.png", sheet([cards.cards[n].png for n in mem[:16]],
                                          [f"c{n} box {cards.cards[n].box}" + (" ?" if loose[n] else "")
                                           for n in mem[:16]])))
    parts += [("cast.md", "\n".join(md))] + sheets
    reply, _ = _ask(PASS1_TASK, parts, tag, save)
    final = apply_edits(G, reply.get("edits", []))
    names = {}
    for k, v in (reply.get("names") or {}).items():
        if str(k).lstrip("Gg").isdigit() and int(str(k).lstrip("Gg")) in set(final.tolist()):
            names.setdefault(int(str(k).lstrip("Gg")), str(v))
    print(f"  pass 1: {G.max()} appearance groups, {len(reply.get('edits', []))} edits, {len(set(final))} characters")
    return final, names, reply


# ---------------------------------------------------------------- the series cast

class Cast:
    """A series' characters, kept in <run>/cast/<series>/: cast.json ({"series", "episodes": {episode: pass},
    "characters": [{"id": "K<n>", "name", "first", "exemplars": [{"episode", "card", "thumb"}], "lines", "voice"}]}),
    exemplars.npz (the match features of each exemplar, "<episode>/<card id>") and thumbs/ (the exemplars' card PNGs,
    so a rerun of an earlier episode cannot change them)."""

    def __init__(self, root: Path, series: str):
        self.dir = root / series
        self.file = self.dir / "cast.json"
        self.d = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else \
            {"series": series, "episodes": {}, "characters": []}
        f = self.dir / "exemplars.npz"
        self.x = dict(np.load(f)) if f.exists() else {}

    @property
    def chars(self) -> list[dict]:
        return self.d["characters"]

    def char(self, cid: str) -> dict | None:
        return next((c for c in self.chars if c["id"] == cid), None)

    def without(self, episode: str) -> None:
        """The episode's own contribution removed (a rerun of it): the characters it founded and its exemplars."""
        keep = [c for c in self.chars if c["first"] != episode]
        for c in keep:
            c["exemplars"] = [e for e in c["exemplars"] if e["episode"] != episode]
        if len(keep) < len(self.chars):
            print(f"  {len(self.chars) - len(keep)} characters founded by {episode} replaced: episodes run after it "
                  f"should run again")
        self.d["characters"] = keep
        self.d["episodes"].pop(episode, None)
        self.x = {k: v for k, v in self.x.items() if not k.startswith(episode + "/")}

    def add(self, episode: str, name: str, cards: list[Card], x: np.ndarray, lines: list[str]) -> str:
        """A new character from these cards (their match features x): up to EXEMPLARS of them, spread over its
        appearances. Returns its id."""
        cid = f"K{max([int(c['id'][1:]) for c in self.chars] + [0]) + 1}"
        pick = sorted({int(i) for i in np.linspace(0, len(cards) - 1, min(EXEMPLARS, len(cards)))})
        (self.dir / "thumbs").mkdir(parents=True, exist_ok=True)
        ex = []
        for i in pick:
            thumb = f"{episode}__{cards[i].id.replace('/', '__')}"
            shutil.copyfile(cards[i].png, self.dir / "thumbs" / thumb)
            ex.append({"episode": episode, "card": cards[i].id, "thumb": thumb})
            self.x[f"{episode}/{cards[i].id}"] = x[i]
        self.chars.append({"id": cid, "name": name, "first": episode, "exemplars": ex, "lines": lines[:20],
                           "voice": None})
        return cid

    def features(self, c: dict) -> np.ndarray:
        return np.stack([self.x[f"{e['episode']}/{e['card']}"] for e in c["exemplars"]])

    def thumbs(self, c: dict) -> list[Path]:
        return [self.dir / "thumbs" / e["thumb"] for e in c["exemplars"]]

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.d, indent=1, ensure_ascii=False), encoding="utf-8")
        np.savez(self.dir / "exemplars.npz", **self.x)


# ---------------------------------------------------------------- 7d. pass 2

PASS2_TASK = """# Task: identify the characters of a new episode against the known cast

You get a NEW comic episode, and the cast already confirmed in the EARLIER episodes of the same series. An appearance algorithm grouped the new episode's character cards (a card is one figure in one panel) and proposed, for each group, which known character it is (`K<n>`) or `NEW` (someone not in the known cast). It makes mistakes: it confuses look-alikes, misses a known character who looks different here (other clothes, a close-up, an odd pose), and lumps different people together.

Your job: decide, **the way an attentive reader of the series would**, which known character each group and card really is, or whether it is someone new.

## Material (below, in this order)
- `cast.md` and `K<n>.png`: the known cast, each character with cards from the earlier episodes and some of their lines. One convention: a person shown in a deliberately different look (heavy makeup against none, a disguise, a transformation) is a SEPARATE character here, with its own K. Keep such looks apart.
- `page-NN.png`: the new episode in reading order. Read every one of them, in order. Each card is tagged `G<group> c<card> > K<n>` (or `> NEW`), showing the proposal.
- `groups.md` and `G<k>.png`: each group of the new episode, its proposal, its three closest known characters by appearance, and its lines.
- `script.md`: every line of the new episode with its speaker card, group and proposal. A link made by a tail pointing at a card is right about 95% of the time. A balloon marked `check` was linked without one (the only figure in the frame, the nearest figure, a tail shared by a stack of balloons, no card in the box), or to several cards at once (a tail at two figures that touch): the usual mistake there is a speaker drawn in another frame or box, or off-panel.

## How to work
1. Look at the cast sheets first, so you know the characters.
2. Read ALL the new episode's pages with the script. Follow the story: names used (a name called out names the person addressed), who is with whom, roles, relationships, outfits, what is happening.
3. For each group, check the proposal. Is it the right known character, a different one, or someone new? Does the group mix several people?
4. Use the story as your evidence. The algorithm already used appearance.
5. The script's speaker links are part of what you check. While reading, when the story makes clear that a balloon is said by a different character than the card linked (the linked card is the one addressed, the balloon continues another character's speech, the reply makes no sense from the linked card...), report it under `speakers`. The pipeline only links within a frame; a speaker is often drawn elsewhere: in another frame of the box, or in the box before or after (a voice carrying over, a reply across a cut). Name the character's card there, any `c<n>` of the episode. `off-panel` only when the speaker is drawn nowhere in the episode. Decide EVERY balloon marked `check`: list each one under `speakers`, with `said_by` the linked card itself when the link is right. A balloon linked to several cards is said by ONE of them. Decide which in two steps: first look at the balloon's tail in the page image, the pointed end of the balloon, which aims at the speaker's mouth or figure; then check that reading against the turns of the conversation (who spoke before, who is answered, who is addressed) and the story. When the two agree, that is the speaker; when the tail is ambiguous (figures touching where it points, no tail), the turns decide. Name that one card; give several cards only for a real chorus, several characters saying the same words together. The same two steps settle any balloon whose linked card looks wrong. For the other balloons, report only what you are sure of.

## Output
Reply with ONE JSON object:

```json
{
  "groups": {"G1": "K3", "G4": "NEW", "G7": "K1"},
  "moves": [{"card": "c34", "to": "K5", "evidence": "..."}, {"card": "c51", "to": "NEW", "evidence": "..."}],
  "evidence": {"G1": "box 3: called by name ...", "G4": "..."},
  "names": {"G4": "the name the story gives each NEW group's character, or a short description"},
  "speakers": [{"box": 14, "line": "the balloon's first words", "card": "c94", "said_by": "c92", "evidence": "..."}],
  "notes": "anything uncertain"
}
```

- `groups`: list only the groups whose proposal you CHANGE. Any group not listed keeps its proposal.
- `moves`: single cards that belong to a different character than their group, given as `K<n>`, `NEW`, or a group `G<k>` (that group's final character).
- `names`: one for every group that ends as NEW.
- `speakers`: every `check` balloon, and any other balloon whose speaker link is wrong (`card`: the linked card, `said_by`: the card that says it, the same card to confirm, or `off-panel`).
- When unsure, keep the proposal and the links: a wrong change costs as much as a missed one.
"""


def match(G: np.ndarray, x: np.ndarray, frames: list[str], cast: Cast) -> tuple[dict, dict]:
    """Each group's proposed cast character by appearance: score(G, K) = mean over G's cards of the mean of their
    TOP_K best similarities to K's exemplars. Groups in order of their best score take their best character that
    clears MATCH_MIN and that no group sharing a frame with them already took; else None (NEW)."""
    ids = [c["id"] for c in cast.chars]
    feats = {c["id"]: cast.features(c) for c in cast.chars}
    score = {}
    for k in np.unique(G):
        idx = np.where(G == k)[0]
        for c in ids:
            sim = x[idx] @ feats[c].T
            score[(int(k), c)] = float(np.sort(sim, 1)[:, -min(TOP_K, sim.shape[1]):].mean(1).mean())
    fr = np.array(frames)
    taken, out = {}, {}
    for k in sorted(map(int, np.unique(G)), key=lambda k: -max(score[(k, c)] for c in ids)):
        mine = set(fr[G == k])
        out[k] = None
        for c in sorted(ids, key=lambda c: -score[(k, c)]):
            if score[(k, c)] < MATCH_MIN:
                break
            if any(mine & set(fr[G == k2]) for k2 in taken.get(c, [])):
                continue
            out[k] = c
            taken.setdefault(c, []).append(k)
            break
    return out, score


def pass2(chapter, cards: Cards, s: np.ndarray, x: np.ndarray, cast: Cast, save: Path, tag: str):
    """Groups by appearance, matched to the cast, corrected by the reader. Returns (per card a cast id or "NEW",
    per card its group, {group: name} for NEW groups, reply)."""
    G = number_groups(witness_link(s, [c.frame for c in cards.cards]))
    frames = [c.frame for c in cards.cards]
    m, score = match(G, x, frames, cast)
    prop = {k: m[k] or "NEW" for k in m}
    names = {c["id"]: c["name"] for c in cast.chars}
    md, cast_sheets = ["# The known cast from the earlier episodes\n"], []
    for c in sorted(cast.chars, key=lambda c: -len(c["exemplars"])):
        th = cast.thumbs(c)
        pick = [th[int(i)] for i in sorted({int(i) for i in np.linspace(0, len(th) - 1, min(8, len(th)))})]
        cast_sheets.append((f"{c['id']}.png", sheet(pick, [""] * len(pick))))
        md.append(f"## {c['id']}: {c['name']} ({len(c['exemplars'])} cards kept)"
                  + ("\nlines: " + " / ".join(f'"{t}"' for t in c["lines"][:5]) if c["lines"] else ""))
    page_parts = [(f"page-{k:02d}.png", p) for k, p in enumerate(
        pages(chapter, cards, lambda n: f"G{G[n]} c{n} > {prop[int(G[n])]}", lambda n: PAL[(G[n] - 1) % len(PAL)]), 1)]
    gm, group_sheets = ["# The new episode's groups and their proposed characters\n"], []
    for k in range(1, G.max() + 1):
        mem = [n for n in range(len(cards)) if G[n] == k]
        best = sorted(names, key=lambda c: -score[(k, c)])[:3]
        lines = [t for n in mem for t in cards.cards[n].lines][:6]
        gm.append(f"## G{k}: {len(mem)} cards, proposed {prop[k]}" + (f" ({names[prop[k]]})" if m[k] else "")
                  + "; closest by appearance: " + ", ".join(f"{c} {score[(k, c)]:.2f}" for c in best)
                  + "\ncards: " + ", ".join(f"c{n}" for n in mem)
                  + ("\nlines: " + " / ".join(f'"{t}"' for t in lines) if lines else "") + "\n")
        group_sheets.append((f"G{k}.png", sheet([cards.cards[n].png for n in mem[:16]], [f"c{n}" for n in mem[:16]])))
    parts = [("cast.md", "\n".join(md))] + cast_sheets + page_parts + [("groups.md", "\n".join(gm))] + group_sheets \
        + [("script.md", script_md(cards, lambda n: f"G{G[n]} > {prop[int(G[n])]}"))]
    reply, _ = _ask(PASS2_TASK, parts, tag, save)
    known = set(names)
    norm = lambda v: (str(v).split()[0] if str(v).split() else "NEW").upper()  # noqa: E731
    lab = dict(prop)
    for k, v in (reply.get("groups") or {}).items():
        kk = str(k).lstrip("Gg")
        if kk.isdigit() and int(kk) in lab and (norm(v) in known or norm(v) == "NEW"):
            lab[int(kk)] = norm(v)
    out = [lab[int(k)] for k in G]
    group = G.copy()
    for mv in reply.get("moves") or []:
        try:
            c = int(str(mv["card"]).lstrip("cC"))
            to = norm(mv["to"])
            if to.startswith("G"):
                out[c], group[c] = lab[int(to[1:])], int(to[1:])
            elif to in known or to == "NEW":
                out[c] = to
                if to == "NEW":
                    group[c] = group.max() + 1  # a card moved to NEW is a character of its own
        except (KeyError, ValueError, IndexError, TypeError) as err:
            print(f"  skipped a malformed move {mv}: {err}")
    new_names = {}
    for k, v in (reply.get("names") or {}).items():
        kk = str(k).lstrip("Gg")
        if kk.isdigit():
            new_names[int(kk)] = str(v)
    print(f"  pass 2: {G.max()} groups, {sum(1 for v in prop.values() if v != 'NEW')} matched by appearance, "
          f"{len(reply.get('groups') or {})} changed and {len(reply.get('moves') or [])} cards moved by the reader")
    return out, group, new_names, reply


# ---------------------------------------------------------------- 7e. the reader's speaker corrections

def _words(s: str) -> str:
    return " ".join(str(s).lower().replace("“", '"').replace("”", '"').strip(' "\'…').split())


def speaker_edits(ep: Episode, cards: Cards, edits: list[dict] | None) -> list[dict]:
    """The reader's speaker corrections applied to the boxes' speaker records (apply_speakers). An edit names a box,
    the balloon's first words, the card it is linked to and who says it: any card of the episode (user, 2026-11-05:
    the speaker need not be drawn in the balloon's box or frame), or off-panel. The balloon is the box's record(s)
    starting with those words, the one(s) linked to the named card when several (a balloon transcribed whole and in
    parts is several records). On the labelled test episodes (2026-11-05) the reader's card-to-card corrections were
    right 11 times and wrong 0 (3 undecidable), its off-panel ones right 3 and wrong 3; the user chose to apply
    both. Returns one record per balloon: {pid, bubble, box, from, to} with the speaker as its card key when in the
    box, "<pid>/<key>" when in another, [] for off-panel, and the evidence; a malformed or unmatched edit is printed
    and skipped."""
    done, recs_of, confirmed = [], {}, 0
    key = lambda s: cards.cards[int(str(s).lstrip("cC"))].id.split("/", 1)[1]  # noqa: E731
    for e in edits or []:
        try:
            b, line, to = int(e["box"]), _words(e["line"]), str(e["said_by"]).strip().lower()
            recs = recs_of.setdefault(b, ep.box(b).speakers() or [])
            hits = [r for r in recs if r.get("kind") != "sfx" and line and
                    (_words(r.get("text", "")).startswith(line) or line.startswith(_words(r.get("text", ""))))]
            if str(e.get("card", "")).lstrip("cC").isdigit():  # the linked card; "off-panel" when there is none
                was = key(e["card"])
                hits = [r for r in hits if was in (r.get("speakers") or [])] or hits
            if to.startswith("off"):
                new = []
            else:  # one card, or several for a chorus ("c54, c56"); a card of another box by its full id
                nums = [int(t) for t in re.findall(r"\d+", to)]
                if not nums:
                    raise ValueError(f"no card in said_by {to!r}")
                new = [key(n) if cards.cards[n].box == b else cards.cards[n].id for n in nums]
            if not hits:
                print(f"  skipped a speaker edit: no balloon starting \"{e['line']}\" in box {b}")
                continue
            for r in hits:
                if (r.get("speakers") or []) == new:
                    confirmed += 1
                    continue
                done.append({"pid": r["pid"], "bubble": r["bubble"], "box": b, "from": list(r.get("speakers") or []),
                             "to": new, "evidence": e.get("evidence", "")})
        except (KeyError, ValueError, IndexError, TypeError) as err:
            print(f"  skipped a malformed speaker edit {e}: {err}")
    apply_speakers(ep, done)
    checks = sum(1 for s in cards.script if s[5])
    print(f"  speakers: {len(done)} links corrected, {confirmed} confirmed ({checks} marked check)")
    return done


def apply_speakers(ep: Episode, fixes: list[dict]) -> None:
    """Speaker corrections ({pid, bubble, box, to}: the speaker's card key in the box, "<pid>/<key>" in another box,
    [] for off-panel) written into the boxes' speaker records, rule "reader"; the record keeps the link it had under
    "was". speaker_kind stays "card" only for a card of the box, as the labels define it; a speaker drawn in another
    box is "off_panel" with its card in speakers, so the line is still voiced."""
    by_box: dict[int, list[dict]] = {}
    for x in fixes:
        by_box.setdefault(int(x["box"]), []).append(x)
    for b, xs in by_box.items():
        box = ep.box(b)
        recs = box.speakers() or []
        for r in recs:
            for x in xs:
                if r["bubble"] == x["bubble"]:
                    r["was"] = {k: r.get(k) for k in ("speakers", "speaker_kind", "rule", "confidence")}
                    kind = "card" if x["to"] and all("/" not in s for s in x["to"]) else "off_panel"
                    r["speakers"], r["speaker_kind"], r["rule"] = list(x["to"]), kind, "reader"
        box.save_speakers(recs)


# ---------------------------------------------------------------- step 7

def series_of(stem: str) -> str:
    """"true-beauty-4" -> "true-beauty": the stem without its trailing episode number."""
    head, _, tail = stem.rpartition("-")
    return head if head and tail.isdigit() else stem


def cast_root(ep: Episode) -> Path:
    return ep.run / "cast"


def identity_step(ep: Episode, chapter, series: str) -> dict | None:
    """Step 7: the episode's cards given cast characters (pass 1 when the series has no cast from other episodes,
    pass 2 otherwise), saved to <episode>/identity/identity.json and the series cast; the reader's speaker
    corrections applied to the boxes' speaker records (speaker_edits). Skipped when identity.json was made from the
    same cards and speakers. Returns identity.json's content, or None (no cards, the cap)."""
    out = ep.out / "identity"
    cards = read_cards(ep, len(chapter))
    have = sum(1 for i in range(len(chapter)) if ep.box(i).scene() is not None)
    print(f"  {len(cards)} character cards in {have} of {len(chapter)} boxes with layers")
    if not len(cards):
        return None
    f = out / "identity.json"
    cast = Cast(cast_root(ep), series)
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if old.get("stamp") == cards.stamp and ep.stem in cast.d["episodes"]:
        print("  current (same cards and speakers): nothing to do")
        return old
    if old.get("where") and ep.stem in cast.d["episodes"] and (carried := same_cards(old, cards)) is not None:
        # the layers were rebuilt and the cards renumbered (a lettering mask gone), the characters themselves the
        # same: the identity carries over by each card's place in its box, no reading needed (2026-11-06)
        old["cards"], old["where"], old["stamp"] = carried, {c.id: [c.box, list(c.bbox)] for c in cards.cards}, cards.stamp
        f.write_text(json.dumps(old, indent=1, ensure_ascii=False), encoding="utf-8")
        print("  cards renumbered, the same characters: identity carried over")
        return old
    old_voices = {c["id"]: c["voice"] for c in cast.chars if c["voice"]}
    feats = embed(cards, out / "feats.npz")
    s = similarity(feats)
    x = match_features(feats)
    cast.without(ep.stem)
    tag = f"{ep.stem} identity"

    def fix_speakers(reply: dict) -> list[dict]:
        """The reader's speaker corrections applied; the cards read again (their lines and stamp change)."""
        nonlocal cards
        fixes = speaker_edits(ep, cards, reply.get("speakers"))
        if fixes:
            cards = read_cards(ep, len(chapter))
        return fixes

    try:
        if not cast.chars:
            final, names, reply = pass1(chapter, cards, s, out / "reader", tag)
            fixes = fix_speakers(reply)
            per, mode = {}, 1
            for k in sorted(set(final.tolist()), key=lambda k: int(np.where(final == k)[0][0])):
                idx = [n for n in range(len(cards)) if final[n] == k]
                per[k] = cast.add(ep.stem, names.get(k, "unnamed"), [cards.cards[n] for n in idx], x[idx],
                                  [t for n in idx for t in cards.cards[n].lines])
            ids = [per[int(k)] for k in final]
        else:
            got, group, names, reply = pass2(chapter, cards, s, x, cast, out / "reader", tag)
            fixes = fix_speakers(reply)
            mode, new = 2, {}
            for n, v in enumerate(got):
                if v == "NEW":
                    new.setdefault(int(group[n]), []).append(n)
            ids = list(got)
            for k, idx in new.items():
                cid = cast.add(ep.stem, names.get(k, "unnamed"), [cards.cards[n] for n in idx], x[idx],
                               [t for n in idx for t in cards.cards[n].lines])
                for n in idx:
                    ids[n] = cid
    except (BudgetExceeded, Truncated) as e:
        print(f"  no identity ({e}); the next run asks again")
        return None
    if old.get("cards"):
        n = inherit_voices(cast, old["cards"], old_voices, cards, ids)
        if n:
            print(f"  {n} voices kept from the earlier run")
    cast.d["episodes"][ep.stem] = f"pass {mode}"
    cast.save()
    chars = {}
    for n, cid in enumerate(ids):
        c = chars.setdefault(cid, {"name": cast.char(cid)["name"], "cards": 0, "lines": 0})
        c["cards"] += 1
        c["lines"] += len(cards.cards[n].lines)
    res = {"episode": ep.stem, "series": series, "pass": mode, "stamp": cards.stamp,
           "cards": {c.id: cid for c, cid in zip(cards.cards, ids)}, "characters": chars,
           "where": {c.id: [c.box, list(c.bbox)] for c in cards.cards},
           "reader": {k: reply.get(k) for k in ("edits", "groups", "moves", "names", "notes") if k in reply}
           | {"speakers": fixes}}
    out.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(chars)} characters: " + ", ".join(f"{k} {v['name']} ({v['cards']})" for k, v in
                                                       sorted(chars.items(), key=lambda kv: -kv[1]["cards"])))
    return res


SAME_CARD_IOU = 0.9  # a new card at the place of an old one in its box (box overlap) is that card


def same_cards(old: dict, cards: Cards) -> dict | None:
    """The saved identity's {card id: character} for the current cards, when every current card stands where a card
    of the saved identity stood in its box (bbox overlap at least SAME_CARD_IOU) and every saved card is matched: the
    cards were renumbered, not re-segmented. None otherwise."""
    where = old["where"]
    by_box: dict[int, list[tuple[str, list]]] = {}
    for cid, (b, bbox) in where.items():
        by_box.setdefault(int(b), []).append((cid, bbox))
    out, taken = {}, set()
    for c in cards.cards:
        best, best_iou = None, 0.0
        for oid, bb in by_box.get(c.box, []):
            if oid in taken:
                continue
            x0, y0, x1, y1 = (max(c.bbox[0], bb[0]), max(c.bbox[1], bb[1]), min(c.bbox[2], bb[2]), min(c.bbox[3], bb[3]))
            inter = max(0, x1 - x0) * max(0, y1 - y0)
            union = (c.bbox[2] - c.bbox[0]) * (c.bbox[3] - c.bbox[1]) + (bb[2] - bb[0]) * (bb[3] - bb[1]) - inter
            iou = inter / union if union else 0.0
            if iou > best_iou:
                best, best_iou = oid, iou
        if best is None or best_iou < SAME_CARD_IOU:
            return None
        out[c.id], _ = old["cards"][best], taken.add(best)
    return out if len(taken) == len(where) else None


def inherit_voices(cast: Cast, old_cards: dict, old_voices: dict, cards: Cards, ids: list[str]) -> int:
    """A rerun of an episode founds its characters again under new ids (Cast.without dropped the old ones): each
    new character without a voice takes the voice of the earlier character that held most of its cards (the cards
    are the same ones: a rerun regroups, it does not segment again), a shared voice (same_voice_as) re-pointed at
    the new id. Returns how many were kept."""
    share: dict[tuple[str, str], int] = {}
    for c, cid in zip(cards.cards, ids):
        o = old_cards.get(c.id)
        if o:
            share[(cid, o)] = share.get((cid, o), 0) + 1
    to_new: dict[str, str] = {}
    for (cid, o), _ in sorted(share.items(), key=lambda kv: -kv[1]):
        to_new.setdefault(o, cid)
    kept = 0
    for o, cid in to_new.items():
        c, v = cast.char(cid), old_voices.get(o)
        if c and v and not c["voice"]:
            v = dict(v)
            if v.get("same_voice_as"):
                v["same_voice_as"] = to_new.get(v["same_voice_as"], v["same_voice_as"])
            c["voice"] = v
            kept += 1
    return kept


# ---------------------------------------------------------------- step 8

VOICE_TASK = """# Task: design a voice for each speaking character

The episode's characters will be voiced by a text-to-speech model, Gemini 3.8 Flash TTS. Its voice design creates one persistent voice per character from a short text description. Write that description for every character listed in `voices.md`, the way a casting director would after reading the comic.

## Material (below, in this order)
- `page-NN.png`: the episode in reading order. Read every page. Each character card is tagged `K<n> c<card>`.
- `voices.md`: the characters to voice, each with every line it speaks; then the characters of the series that already have a voice.
- `K<n>.png`: each character's cards as thumbnails.
- `script.md`: every balloon in order, for context.

## What the voice model needs (from its documentation)
- **description**: ONE or TWO clear sentences of PERMANENT traits: approximate age, gender, timbre (warm, bright, husky, breathy, deep, nasal...), vocal texture, accent if any, and the baseline manner of speaking that fits the personality (e.g. quick and chatty, slow and dry, soft and hesitant). Example of the expected form: "A warm, thoughtful astronomer in his late 60s with a gentle British accent, speaking with quiet wonder." Long or self-contradictory descriptions make the voice drift.
- NOT in the description: situational emotions (crying, shouting, whispering, scared). Those change line by line and are added later per line. Describe the voice the character has on an ordinary day.
- The voice model refuses to design the voice of anyone under 18 and rejects the whole description. State an age in the description only for adults. For a child or teenage character describe the SOUND that makes a voice young instead (a light, bright or higher timbre, youthful energy, quick delivery) and the role or manner, without an age, school stage or any other word that says they are a minor.
- **age**: the character's approximate age or range as the story shows it (e.g. "about 13", "late teens", "60s", "ageless creature"), for EVERY character, minors included: it is kept in the cast beside the voice, and only the description goes to the voice model.
- **gender**: "female", "male", or "neutral" when the story gives no clue (a creature, an unseen narrator).
- **language_code**: the language the characters speak, as a BCP-47 code (e.g. "en-US").
- **display_name**: the character's name in the story, or a short description if the story never names them.

## Rules
1. Base every trait on the story: what the character looks like, their age, role, relationships, and how they talk (word choice, length of lines, politeness, slang). Give that evidence briefly.
2. Make the voices of one cast clearly DISTINCT from one another and from the voices the series already has (pitch, age, timbre, pace), so a listener can tell who is speaking without seeing the page.
3. A person shown in a deliberately different look (heavy makeup against none, a disguise, a costume, a performance) is a separate character here, but all their looks share ONE voice: describe it once, on the look that speaks most, and give each other look `"same_voice_as": "K<n>"` instead of a description. If that person already has a voice in the series, point to it. This holds even when the look performs, sings or puts on an act: the voice is still that person's, and the act is a per-line delivery, not a new voice.
4. Non-human characters still get a voice if they speak words; describe what they should sound like.
5. If a character seems to mix several people, say so in `notes`, and voice the person who speaks most of its lines.

## Output
Reply with ONE JSON object:

```json
{
  "language_code": "en-US",
  "voices": [
    {"character": "K1", "display_name": "...", "gender": "female", "age": "late teens",
     "description": "One or two sentences.", "evidence": "box 3: ...; her lines are short and blunt ..."},
    {"character": "K7", "display_name": "...", "age": "late teens", "same_voice_as": "K1", "evidence": "the same person with makeup on"}
  ],
  "notes": "anything uncertain"
}
```
"""


def voices_step(ep: Episode, chapter, identity: dict) -> None:
    """Step 8: a voice for every character of the episode with at least MIN_LINES lines and none in the cast yet,
    from one reader call, saved in the series cast (character "voice"); then every described voice of the cast not
    designed yet is designed on Gemini (design_voices)."""
    cast = Cast(cast_root(ep), identity["series"])
    cards = read_cards(ep, len(chapter))
    ids = [identity["cards"].get(c.id) for c in cards.cards]
    lines = {}
    for n, cid in enumerate(ids):
        lines.setdefault(cid, []).extend(cards.cards[n].lines)
    todo = [cid for cid in sorted(lines, key=lambda c: -len(lines[c]))
            if cid and len(lines[cid]) >= MIN_LINES and cast.char(cid) and not cast.char(cid)["voice"]]
    print(f"  {len(todo)} characters to voice ({sum(1 for c in cast.chars if c['voice'])} in the series have one)")
    if not todo:
        design_voices(cast)
        record_lines(ep, len(chapter), identity, cast)
        return
    col = {cid: PAL[i % len(PAL)] for i, cid in enumerate(sorted(set(filter(None, ids))))}
    parts = [(f"page-{k:02d}.png", p) for k, p in enumerate(
        pages(chapter, cards, lambda n: f"{ids[n]} c{n}", lambda n: col.get(ids[n], (90, 90, 90))), 1)]
    md = [f"# Characters to voice (at least {MIN_LINES} lines in this episode)\n"]
    for cid in todo:
        md.append(f"## {cid}: {cast.char(cid)['name']} ({len(lines[cid])} lines)\n"
                  + "\n".join(f'- "{t}"' for t in lines[cid][:40]) + "\n")
    voiced = [c for c in cast.chars if c["voice"]]
    if voiced:
        md.append("# Characters of the series that already have a voice\n")
        md += [f"- {c['id']}: {c['name']}: " + (c["voice"].get("description") or
                                               f"same voice as {c['voice'].get('same_voice_as')}") for c in voiced]
    parts.append(("voices.md", "\n".join(md)))
    for cid in todo + [c["id"] for c in voiced if c["id"] in lines]:
        mem = [n for n in range(len(cards)) if ids[n] == cid][:16]
        parts.append((f"{cid}.png", sheet([cards.cards[n].png for n in mem], [f"c{n}" for n in mem])))
    parts.append(("script.md", script_md(cards, lambda n: ids[n] or "?")))
    try:
        reply, _ = _ask(VOICE_TASK, parts, f"{ep.stem} voices", ep.out / "identity" / "voices")
    except (BudgetExceeded, Truncated) as e:
        print(f"  no voices ({e}); the next run asks again")
        return
    lang = reply.get("language_code") or "en-US"
    done = []
    for v in reply.get("voices") or []:
        c = cast.char(str(v.get("character", "")).split()[0] if v.get("character") else "")
        if c is None or c["id"] not in todo:
            continue
        same = str(v.get("same_voice_as") or "").split()[0] if v.get("same_voice_as") else None
        if same and same != c["id"] and cast.char(same):
            c["voice"] = {"same_voice_as": same, "age": v.get("age"), "evidence": v.get("evidence", "")}
        elif v.get("description"):
            c["voice"] = {k: v.get(k) for k in ("display_name", "gender", "age", "description", "evidence")} | \
                         {"language_code": lang, "episode": ep.stem}
        else:
            continue
        done.append(c["id"])
    cast.save()
    print(f"  voices for {len(done)} of {len(todo)}: " + "; ".join(
        f"{cid} " + (cast.char(cid)["voice"].get("description") or f"= {cast.char(cid)['voice']['same_voice_as']}")
        for cid in done))
    design_voices(cast)
    record_lines(ep, len(chapter), identity, cast)


def design_voices(cast: Cast) -> None:
    """Every described voice of the cast without a designed one, designed on Inworld (inworld.design_voice, the
    character's own lines as the preview script) and published: the voice id in the cast (voice "id"), its sample in
    <cast>/voices/K<n>.wav. A description the service refuses is printed and tried again on the next run; the cap
    stops the rest for the next run."""
    todo = [c for c in cast.chars if c["voice"] and c["voice"].get("description") and not c["voice"].get("id")]
    if not todo:
        return
    (cast.dir / "voices").mkdir(parents=True, exist_ok=True)
    made, cost = 0, 0.0
    for c in todo:
        v = c["voice"]
        preview = " ".join(c.get("lines") or [])[:400] or v["description"]
        try:
            got = IW.design_voice(v["description"], v.get("display_name") or c["name"], preview,
                                  v.get("language_code") or "en-US", tag=f"{cast.d['series']} voice {c['id']}")
        except BudgetExceeded as e:
            print(f"  voices not designed ({e}); the next run designs them")
            break
        except RuntimeError as e:
            print(f"  {c['id']} {c['name']}: {e}")
            continue
        v["id"], v["design_cost"] = got["id"], got["cost"]
        (cast.dir / "voices" / f"{c['id']}.wav").write_bytes(got["sample"])
        made, cost = made + 1, cost + got["cost"]
    cast.save()
    print(f"  {made} of {len(todo)} voices designed ({cost:.4f} USD at list price): " +
          ", ".join(f"{c['id']} {c['name']}" for c in todo if c['voice'].get('id')))


STYLE = {"shout": "shouting", "thought": "thinking to themself, a quiet inner voice", "whisper": "whispering"}


def style_of(r: dict) -> str | None:
    """A line's delivery note for the voice model: what the balloon's kind says (STYLE) and what Transcribe read in
    the drawing (the record's delivery: emotion and manner), joined; None when neither says anything."""
    return ", ".join(s for s in (STYLE.get(r.get("kind")), (r.get("delivery") or "").strip()) if s) or None
LINE_WORKERS = 4  # speech calls in flight (Inworld's free plan allows 5 concurrent)
PACE = {"slow": 0.9, "fast": 1.1}  # a line's tempo as Transcribe read it, times the character's rate (user, 2026-11-06)
CONTEXT_LINES = 2  # balloons before a line, any speaker, sent as the scene so far (inworld.speech context)


def record_lines(ep: Episode, n_boxes: int, identity: dict, cast: Cast) -> None:
    """Every spoken balloon with a speaker card (speakers.json: kind not sfx; the card in the box, or in another box
    by the reader's correction) as audio in its character's designed voice, the delivery from the balloon's kind
    and Transcribe's note on the drawing (style_of), to <episode>/audio/<pid>.b<bubble>.wav
    and audio/lines.json (one record per balloon: who, voice, text, style, seconds, cost). A balloon already recorded
    with the same text, voice and style is kept; one whose character has no designed voice is skipped, counted."""
    out = ep.out / "audio"
    index = out / "lines.json"
    have = {(l["pid"], l["bubble"]): l for l in json.loads(index.read_text(encoding="utf-8"))} if index.exists() else {}

    def voice_of(cid: str | None, hops: int = 0) -> tuple[str, str | None]:
        """(the character whose voice is used, its voice id or None): looks sharing a voice point at its owner."""
        c = cast.char(cid) if cid else None
        v = (c or {}).get("voice") or {}
        if v.get("same_voice_as") and hops < 4:
            return voice_of(v["same_voice_as"], hops + 1)
        return cid or "", v.get("id")

    def rate_of(cid: str, pace: str | None) -> float:
        """The line's speaking rate: the character's (its cast record's "rate", else the backend's default) times
        the line's pace as Transcribe read it (PACE: slow 0.9, fast 1.1)."""
        v = (cast.char(cid) or {}).get("voice") or {}
        return round(float(v.get("rate") or IW.SPEAKING_RATE) * PACE.get(pace or "", 1.0), 3)

    todo, kept, unvoiced, wanted, spoken = [], 0, {}, set(), []
    for i in range(n_boxes):
        box = ep.box(i)
        for r in sorted(box.speakers() or [], key=lambda r: r["order"]):
            text = (r.get("text") or "").strip()
            if r.get("kind") == "sfx" or not text:
                continue
            context = " ".join(spoken[-CONTEXT_LINES:]) or None  # the scene so far, whoever spoke
            spoken.append(text)
            if not r.get("speakers"):
                continue
            if not re.search(r"[^\W_]", text):  # a balloon of marks alone ("...", "?!!"): a reaction, no words to say
                continue
            s = r["speakers"][0]  # a card of the box, or "<pid>/<key>" of another box (the reader's correction)
            cid = identity["cards"].get(s if "/" in s else f"{r['pid']}/{s}")
            who, vid = voice_of(cid)
            if not vid:
                unvoiced[who or "?"] = unvoiced.get(who or "?", 0) + 1
                continue
            line = {"pid": r["pid"], "bubble": r["bubble"], "box": i, "order": r["order"], "character": cid, "voice": who,
                    "voice_id": vid, "text": text, "style": style_of(r), "context": context,
                    "rate": rate_of(who, r.get("pace")),
                    "file": f"{r['pid']}.b{r['bubble']}.wav"}
            wanted.add((line["pid"], line["bubble"]))
            old = have.get((line["pid"], line["bubble"]))
            # current when the same words go to the same designed voice at the same rate (a rerun renumbers the
            # characters, K12 to K11, while the voice they inherited is the same one)
            if old and all(old.get(k) == line[k] for k in ("voice_id", "text", "style", "rate")) and (out / old["file"]).exists():
                kept += 1
                continue
            todo.append(line)
    stale = [k for k in have if k not in wanted]  # recorded earlier, no longer a voiced balloon (its speaker changed)
    for k in stale:
        (out / have.pop(k)["file"]).unlink(missing_ok=True)
    print(f"  {len(todo)} lines to record, {kept} current" + (f", {len(stale)} dropped" if stale else "") +
          (f"; no voice for {sum(unvoiced.values())}: " + ", ".join(f"{k} {n}" for k, n in unvoiced.items())
           if unvoiced else ""))
    if stale:
        index.write_text(json.dumps(sorted(have.values(), key=lambda l: (l["box"], l["order"])), indent=1,
                                    ensure_ascii=False), encoding="utf-8")
    if not todo:
        return
    out.mkdir(parents=True, exist_ok=True)
    vid = {cid: voice_of(cid)[1] for cid in {l["voice"] for l in todo}}

    def one(n: int) -> dict:
        l = todo[n]
        wav, cost = IW.speech(l["text"], vid[l["voice"]], l["style"], tag=f"{ep.stem} line {l['pid']} b{l['bubble']}",
                              context=l.get("context"), rate=l["rate"])
        (out / l["file"]).write_bytes(wav)
        import soundfile as sf
        info = sf.info(out / l["file"])
        return l | {"seconds": round(info.duration, 2), "cost": round(cost, 5)}

    def save(n: int, l: dict) -> None:  # after each line: a run stopped half-way keeps what it recorded
        have[(l["pid"], l["bubble"])] = l
        lines = sorted(have.values(), key=lambda l: (l["box"], l["order"]))
        index.write_text(json.dumps(lines, indent=1, ensure_ascii=False), encoding="utf-8")

    done, stopped = paid_map(one, range(len(todo)), workers=LINE_WORKERS, on_done=save)
    cost = sum(done[n]["cost"] for n in done)
    secs = sum(done[n]["seconds"] for n in done)
    print(f"  {len(done)} lines recorded, {secs:.0f} s of audio, {cost:.4f} USD at list price" +
          (f"; {len(stopped)} stopped by the cap: the next run records them" if stopped else ""))
    if done or stale:
        episode_audio(ep)


GAP_S = 0.6  # silence between lines in the episode's listening file


def episode_audio(ep: Episode) -> Path | None:
    """The episode's recorded lines joined in reading order with GAP_S of silence between them, as
    <episode>/audio/episode.mp3 for listening and sharing, with episode.txt beside it (the time, speaker and text
    of each line). Written after each recording run; None when there are no lines."""
    import numpy as np
    import soundfile as sf
    index = ep.out / "audio" / "lines.json"
    if not index.exists():
        return None
    lines = json.loads(index.read_text(encoding="utf-8"))
    parts, cues, t, sr = [], [], 0.0, 24000
    for l in lines:
        f = ep.out / "audio" / l["file"]
        if not f.exists():
            continue
        data, rate = sf.read(f)
        if rate != sr:
            continue
        cues.append(f"{int(t // 60)}:{t % 60:04.1f} {l['voice']:>4} {l['text'][:80]}")
        parts += [data, np.zeros(int(GAP_S * sr))]
        t += len(data) / sr + GAP_S
    if not parts:
        return None
    out = ep.out / "audio" / "episode.mp3"
    sf.write(out, np.concatenate(parts), sr, format="MP3")
    out.with_suffix(".txt").write_text("\n".join(cues), encoding="utf-8")
    print(f"  episode audio: {len(cues)} lines, {t / 60:.1f} min, {out.name}")
    return out


if __name__ == "__main__":
    import argparse
    from chapter import Chapter
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--series", default="")
    ap.add_argument("--no-voices", action="store_true")
    a = ap.parse_args()
    ch = Chapter(a.zumi)
    e = Episode(a.out, ch.stem)
    ident = identity_step(e, ch, a.series or series_of(ch.stem))
    if ident and not a.no_voices:
        voices_step(e, ch, ident)
