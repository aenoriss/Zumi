# Qwen-Image-Edit 2509/2511 in diffusers: parameters, sizes, masks (2026-10)

Question: which knobs of `QwenImageEditPlusPipeline` (and its siblings) explain the failures seen when cleaning
point-cloud renders of comic panels (duplicated characters, deleted characters, invented text, drift outside
the holes, an added border, 1200x434 in, 1696x608 out), and what configuration to use instead.
Sources: diffusers main at [`aaf57d0`][D] (read 2026-10-25), the Qwen [model cards][C09], the
[Qwen-Image repo][QR] (`6b5e1f5`), the [Lightning repo][LR] (`115d41a`), GitHub issues. Nothing was run.
Labels: **[inference]** = my reasoning from the code, not a source; **[unverified]** = not confirmed in a
primary source. Line links are permalinks to the commits above.

## Summary

1. **The 1696x608 output is by design.** Output size = 1024x1024 area at the *last* input image's aspect,
   rounded to 32: 1200x434 gives 1696x608 ([L645-L652][P645]). Every input image is also VAE-encoded at its
   own 1024² size ([L66-L67][P66], [L699-L706][P699]). Passing `height/width` does not resize the conditions.
2. **Do not pass `height=434, width=1200`.** RoPE positions are centred integers per image ([L311-L315][T311]),
   so a 75x27-token output against a 106x38-token condition lines up as a centre crop: a zoom [inference]. The
   Qwen author says custom sizes are "not recommended" and conditions "should match the final output
   resolution" ([naykun, diffusers#12216][I12216]). Render the point cloud at 1696x608 instead.
3. **Nothing in `QwenImageEditPlusPipeline` copies input pixels.** The output starts from pure noise
   ([L497-L499][P497]); preservation is only learned. Drift outside the holes is expected; only a mask can stop it.
4. **A masked variant exists, single-image only:** `QwenImageEditInpaintPipeline` (`mask_image`, `strength`,
   `padding_mask_crop`). It loads 2509 weights and the Lightning LoRA; the HF Space by a diffusers maintainer
   does exactly that ([Space app.py L155-L204][SP]). There is no multi-image ("Plus") inpaint, not even in
   modular diffusers ([edit-plus blocks][MBP] vs [edit blocks L147][MBE]).
5. **Our Lightning runs use the wrong scheduler.** The LoRA was distilled with shift 3 and no terminal stretch
   (`base_shift = max_shift = log 3`, `shift_terminal: None`, [generate_with_diffusers.py L56-L72][LG]);
   `qwen_angles.py` (pipeline/modal, deleted 2026-10-30, in the git history) keeps the 2509 default (`max_shift 0.9`, `shift_terminal 0.02`, [scheduler config][SC09]),
   which for 4028 tokens gives shift ≈ 2.0 instead of 3 [inference, from [L70-L81][P70] and [L655-L656][S655]].
6. **Official prompt for hole filling is a fixed template:** "Perform inpainting on this image. The original
   caption is: " ([prompt_utils.py L225-L226][PU]). Images are labelled "Picture 1:", "Picture 2:" in the
   encoder template ([L239-L247][P239]), so prompts should say "Picture N", not "image N".

## 1. Call signatures

`QwenImageEditPlusPipeline.__call__` ([L528-L552][P528]); `QwenImageEditPipeline` is identical ([L506-L529][E506]):

| Argument | Default | What it does |
|---|---|---|
| `image` | None | PIL or list; Plus accepts several, Edit takes one (`image[0]` sets the size, [E L623][E623]) |
| `prompt`, `negative_prompt` | None | Plus: one prompt only, `batch_size > 1` raises ([L681-L686][P681]) |
| `true_cfg_scale` | **4.0** (docstring says 1.0, [L570][P570]) | real CFG: two transformer passes, `neg + s·(cond − neg)`, then rescaled to the cond norm ([L828-L845][P828]) |
| `height`, `width` | None → computed | floored to multiples of 16 (`vae_scale_factor*2`, [L650-L652][P645]); conditions unaffected |
| `num_inference_steps` | 50 | official cards use 40 for 2509/2511 ([2509 card L61-L63][C09L], [README L150-L156][QR140]) |
| `sigmas` | None → `linspace(1, 1/N, N)` | then shifted by `mu` from the token count ([L764-L776][P764]) |
| `guidance_scale` | None | **ignored**: both checkpoints have `guidance_embeds: false` ([2509][TC09], [2511][TC11]); a value only logs a warning ([L784-L795][P784]) |
| `num_images_per_prompt` | 1 | repeats the embeddings ([L311-L325][P311]) |
| `generator`, `latents` | None | `latents` = packed initial noise, shape `[1, (H/16)(W/16), 64]` |
| `prompt_embeds(_mask)`, `negative_prompt_embeds(_mask)` | None | precomputed; they contain the image tokens too |
| `attention_kwargs` | None | forwarded to the transformer; key `scale` scales LoRAs ([transformer L868][T868], [peft_utils L310][PE]) |
| `callback_on_step_end(_tensor_inputs)` | None, `["latents"]` | allowed: `latents`, `prompt_embeds` ([L187][P187]); may return new `latents` |
| `max_sequence_length` | 512 | only checked `≤ 1024` ([L392-L393][P392]); never truncates in `encode_prompt` |

**CFG gate** ([L708-L719][P708]): CFG runs only if `true_cfg_scale > 1` **and** a negative prompt is given;
`negative_prompt=None` with 4.0 silently disables it (a warning). `" "` counts as a negative prompt. With
Lightning (`true_cfg_scale=1.0`) the negative prompt is unused; one transformer pass per step.

**2511 difference:** its transformer config adds `zero_cond_t: true` ([TC11]); condition-image tokens are then
modulated with timestep 0 (clean) instead of the current t ([transformer L920-L928][T920]). No new call argument.

## 2. How inputs are processed

Per image, aspect preserved, sides rounded to 32 ([`calculate_dimensions` L158-L165][P158]):

| Path | Area target | 1200x434 becomes | Source |
|---|---|---|---|
| Qwen2.5-VL encoder (semantics) | `CONDITION_IMAGE_SIZE = 384*384` | 640x224, then the processor rounds to 28 px ([smart_resize][SR]) | [L66][P66], [L699-L705][P699] |
| VAE condition latents (pixels) | `VAE_IMAGE_SIZE = 1024*1024` | 1696x608 (106x38 tokens) | [L67][P66], [L702-L706][P699] |
| Output | 1024² at `image[-1]`'s aspect | 1696x608 | [L645-L648][P645] |

- **Order:** the prompt becomes `Picture 1: <img> Picture 2: <img> … <prompt>` in list order ([L239-L247][P239]),
  inside a fixed system prompt that already asks to keep "consistency with the original input" ([L215][P215]).
  Condition latents are concatenated in the same order after the noisy latents ([L489-L491][P489]); each image gets its
  own RoPE frame index ([transformer L279-L282, L310][T279]).
- **Size follows the last image**, not the first ([L645][P645]); `QwenImageEditPipeline` uses the first ([E L623][E623]).
  Same-aspect inputs make this moot.
- **Limit:** the 2509 card: "Optimal performance is currently achieved with 1 to 3 input images" ([L26][C09L26]).
- **Fidelity:** the VL encoder sees the panel at ~640x224, so fine detail must come from the 1696x608 VAE
  latents. Non-Plus `QwenImageEditPipeline` feeds the VL encoder the 1024² image instead ([E L660-L664][E660]).
- **Same size in, same size out keeps framing:** `calculate_dimensions` is a fixed point at 1696x608
  (1696x608 → 1696x608) [inference, by evaluating the formula]. Feeding exactly that size removes every hidden
  resample. Diffusers maintainers measured that passing explicit `height/width` hurt preservation, leaving
  them unset matched ComfyUI ([linoytsaban][I12216b]). Residual zoom is still reported at matched sizes
  ([Qwen-Image#229][I229], open, no answer), so a pixel-space composite is still needed.

## 3. Masked inpainting in diffusers

`QwenImageEditInpaintPipeline` ([signature L639-L666][N639]) adds `mask_image` (white = repaint, black = keep,
[L692-L695][N692]), `masked_image_latents`, `strength` (signature default **0.6**, docstring says 1.0, [L650][N639],
[L713][N713]) and `padding_mask_crop`. Mechanism:

- **Single image only.** `image[0]` only, template has one `<|image_pad|>` and no "Picture" label ([L222][N222]); no reference image.
- **`height/width` are overwritten** with the 1024²-area size ([L783-L788][N783]).
- **Latent blending:** after every step, latents outside the mask are replaced by the source latents noised to the
  next sigma; on the last step by the clean source ([L1022-L1031][N1022]). The mask is downsampled to the 1/8
  latent grid ([L562][N562]), so the blend is 8 px coarse and the whole image is still VAE-decoded:
  pixels outside the mask still change slightly unless composited back [inference].
- **`padding_mask_crop`:** crops image and mask to the mask's bounding box plus padding, works on that crop,
  and pastes the result back over the original with the mask ([L828-L845][N828], [L1072-L1075][N1072],
  [`apply_overlay`][AO]). For holes scattered over a whole panel the box is the whole panel, so no gain [inference].
- **The condition still contains the holes:** the transformer is conditioned on the *unmasked* source latents
  ([L980-L981][N980]); `masked_image_latents` is computed ([L927-L942][N927]) but never used in the loop. So the
  model sees black areas as content.
- **`strength`:** `t_start = int(N − N·strength)` ([L464-L473][N464]). With N = 8: 1.0 → 8 steps, 0.75 → 6,
  0.6 → 5 (starting at sigma index 3). Whether Lightning holds up on the shortened trajectory: [unverified].
- **2509/2511 and LoRAs:** the class has `QwenImageLoraLoaderMixin` ([L167][N167]); 2509 + Lightning 8-step,
  Lightning scheduler, `strength=1.0`, 8 steps, `true_cfg_scale=1.0` runs in [the HF Space][SP]. With 2511's
  `zero_cond_t` the two-entry `img_shapes` ([L944-L949][N944]) fits the modulation split [inference]. Quality versus
  training (2509 was trained with a 384² VL image and "Picture" labels) is [unverified].
- `QwenImageInpaintPipeline` is for the text-to-image `Qwen/Qwen-Image`: no condition latents are concatenated.
  Not for edit checkpoints.

## 4. Official recommendations

- **Settings:** 2509 and 2511: `true_cfg_scale=4.0`, `negative_prompt=" "`, 40 steps ([2509 card][C09L],
  [README L131-L156][QR140]). README: "use Qwen-Image-Edit-2509 directly, for both single image input and
  multiple image inputs" over the original ([L227][QR227]).
- **Prompt rewriting:** "editing results may become unstable if prompt rewriting is not used" ([README L266][QR266]);
  tool `polish_edit_prompt` with Qwen-VL-Max ([L324-L330][QR324]). Its rules: inpainting uses the fixed template
  above; keep-unchanged is phrased as an explicit list ("…; keep smile, short hair, and gray jacket unchanged",
  [L213][PU213]); multi-image prompts "must clearly point out which image's element is being modified" ([L228-L231][PU228]).
- **2511 notes:** "mitigate image drift, improved character consistency, integrated LoRA capabilities…"
  ([2511 card L27][C11]); no new arguments in its code sample. Lightning for 2511 exists only as 4-step
  ([Lightning README L7][LR7]).
- **Lightning 2509:** 8 steps, cfg 1.0 ([README L266-L276][LR266]); `true_cfg_scale = 1.0` whenever a LoRA is
  given ([L157][LG157]); scheduler shift 3 as in summary point 5.

## 5. Known issues and fixes

| Symptom | Evidence | Mechanism / fix |
|---|---|---|
| Zoom / pixel shift | [Qwen-Image#229][I229] (open) | mismatched token grids + centred RoPE [inference]; keep sizes at the pipeline's own value; register or composite afterwards |
| Size changes | [#94][I94], [#154][I154] | the 1024² area rule above |
| Weaker preservation with explicit `height/width` | [diffusers#12216][I12216] | author's advice: leave size to the pipeline |
| Duplicated people/heads (2509) | [#167][I167] | "too focused on consistency" (reporter); in our case the reference's characters are attendable tokens, holes copy them [inference] |
| Content not fitting the mask | [#137][I137] | model plans objects larger than the mask; the blend clips them |
| Square outputs degrade (2511) | [#243][I243] | we are 2.8:1, not affected |
| Added border, colour shift | no primary source found | [unverified]; "finished comic panel" wording may invite a frame [inference]; a mask + composite removes both outside the holes |

## Recommended configuration

**A (default): masked, no reference.** `QwenImageEditInpaintPipeline.from_pretrained("Qwen/Qwen-Image-Edit-2509",
scheduler=FlowMatchEulerDiscreteScheduler.from_config(<Lightning config, LG L56-L72>))` + 8-step Lightning LoRA.
- Render the point cloud at **1696x608** (pipeline's own size); mask = no-splat pixels ∪ stretched triangles,
  dilated 16 px (one packed token). Pre-fill holes (OpenCV Telea or blur) rather than black, since the condition
  sees them [inference].
- `strength=1.0`, `num_inference_steps=8`, `true_cfg_scale=1.0`, no `height/width`, `negative_prompt=None`.
- Prompt: `"Perform inpainting on this image. The original caption is: <panel caption from Understand>."` No
  "panel", "comic" or "border" wording; no text request.
- Composite in pixels: `out = src·(1−feather(mask)) + gen·feather(mask)`; drift outside the holes becomes 0.
- 2511: same, base 40 steps cfg 4 with `negative_prompt=" "`, or its 4-step Lightning LoRA.

**B (style reference needed): Plus pipeline + latent blend in a callback** [unverified, not run]. `image=[render, panel]`
(render first, same aspect; output size follows the last), prompt "Fill only the black regions of Picture 1 with
background that continues around them. Picture 2 shows the style only; do not copy its characters." Blend as
the inpaint pipeline does (L1022-L1031):

```python
H, W = 608, 1696
def enc(img):  # same path as the pipeline: preprocess, VAE (argmax), pack
    x = pipe.image_processor.preprocess(img, H, W).unsqueeze(2).to("cuda", torch.bfloat16)
    return pipe._pack_latents(pipe._encode_vae_image(x, generator=None), 1, 16, H // 8, W // 8)
z_src = enc(render)
m = torch.nn.functional.interpolate(mask_t[None, None].float(), size=(H // 8, W // 8))  # 1 = repaint
m = pipe._pack_latents(m.repeat(1, 16, 1, 1), 1, 16, H // 8, W // 8).to(z_src)
noise = torch.randn_like(z_src)
def blend(p, i, t, kw):
    s = p.scheduler.sigmas[i + 1]                    # sigma after this step, 0 after the last
    return {"latents": (1 - m) * ((1 - s) * z_src + s * noise) + m * kw["latents"]}
out = pipe(image=[render, panel], prompt=..., latents=noise, callback_on_step_end=blend, ...)
```

## A/B tests, in order of expected value

1. Scheduler with the Lightning LoRA: 2509 default vs Lightning config (shift 3, no terminal).
2. Pipeline: unmasked Plus (current) vs Inpaint (A) vs Plus + callback blend (B).
3. Hole fill before the model: black vs Telea vs blurred neighbours.
4. Prompt: fixed inpainting template + caption vs current instruction; "Picture N" vs "image N".
5. Mask dilation 8 / 16 / 32 px; `strength` 1.0 vs 0.8 on stretched (non-hole) areas.
6. Model: 2509 Lightning 8 steps vs 2511 base 40 steps cfg 4 vs 2511 Lightning 4 steps.
7. Input size: native 1200x434 vs pre-rendered 1696x608 (measure shift with phase correlation).
8. Three seeds per cell; score drift outside the mask (should be 0 after composite) and duplicates inside.

[D]: https://github.com/huggingface/diffusers/tree/aaf57d03a3edfbd9de457d2872417a92f149a91d
[P66]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L66-L67
[P70]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L70-L81
[P158]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L158-L165
[P187]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L187
[P215]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L215-L216
[P239]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L239-L247
[P311]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L311-L325
[P392]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L392-L393
[P489]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L485-L491
[P497]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L497-L499
[P528]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L528-L552
[P570]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L570-L575
[P645]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L645-L652
[P681]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L681-L686
[P699]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L691-L706
[P708]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L708-L719
[P764]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L764-L776
[P784]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L784-L795
[P828]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_plus.py#L828-L845
[E506]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit.py#L506-L529
[E623]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit.py#L623-L631
[E660]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit.py#L660-L664
[N167]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L167
[N222]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L222
[N464]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L464-L473
[N562]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L559-L562
[N639]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L639-L666
[N692]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L692-L695
[N713]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L713-L718
[N783]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L783-L788
[N828]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L828-L845
[N927]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L926-L942
[N944]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L944-L949
[N980]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L978-L981
[N1022]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L1022-L1031
[N1072]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/pipelines/qwenimage/pipeline_qwenimage_edit_inpaint.py#L1072-L1075
[T279]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/models/transformers/transformer_qwenimage.py#L279-L310
[T311]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/models/transformers/transformer_qwenimage.py#L311-L315
[T868]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/models/transformers/transformer_qwenimage.py#L868
[T920]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/models/transformers/transformer_qwenimage.py#L920-L928
[PE]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/utils/peft_utils.py#L310
[S655]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/schedulers/scheduling_flow_match_euler_discrete.py#L655-L656
[AO]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/image_processor.py#L789-L834
[MBP]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/modular_pipelines/qwenimage/modular_blocks_qwenimage_edit_plus.py#L335-L346
[MBE]: https://github.com/huggingface/diffusers/blob/aaf57d03a3edfbd9de457d2872417a92f149a91d/src/diffusers/modular_pipelines/qwenimage/modular_blocks_qwenimage_edit.py#L147
[SR]: https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/image_processing_qwen2_vl.py
[C09]: https://huggingface.co/Qwen/Qwen-Image-Edit-2509
[C09L]: https://huggingface.co/Qwen/Qwen-Image-Edit-2509/blob/main/README.md#L54-L66
[C09L26]: https://huggingface.co/Qwen/Qwen-Image-Edit-2509/blob/main/README.md#L26
[C11]: https://huggingface.co/Qwen/Qwen-Image-Edit-2511/blob/main/README.md#L27
[TC09]: https://huggingface.co/Qwen/Qwen-Image-Edit-2509/blob/main/transformer/config.json
[TC11]: https://huggingface.co/Qwen/Qwen-Image-Edit-2511/blob/main/transformer/config.json
[SC09]: https://huggingface.co/Qwen/Qwen-Image-Edit-2509/blob/main/scheduler/scheduler_config.json
[QR]: https://github.com/QwenLM/Qwen-Image/tree/6b5e1f5cec987d404be5ac6657db3b9aacb56a89
[QR140]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/README.md#L131-L162
[QR227]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/README.md#L227
[QR266]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/README.md#L266
[QR324]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/README.md#L324-L330
[PU]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/src/examples/tools/prompt_utils.py#L225-L226
[PU213]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/src/examples/tools/prompt_utils.py#L213
[PU228]: https://github.com/QwenLM/Qwen-Image/blob/6b5e1f5cec987d404be5ac6657db3b9aacb56a89/src/examples/tools/prompt_utils.py#L228-L231
[LR]: https://github.com/ModelTC/Qwen-Image-Lightning/tree/115d41afa959f0bc858d25d3b3fddd44054767ad
[LR7]: https://github.com/ModelTC/Qwen-Image-Lightning/blob/115d41afa959f0bc858d25d3b3fddd44054767ad/README.md#L7
[LR266]: https://github.com/ModelTC/Qwen-Image-Lightning/blob/115d41afa959f0bc858d25d3b3fddd44054767ad/README.md#L266-L276
[LG]: https://github.com/ModelTC/Qwen-Image-Lightning/blob/115d41afa959f0bc858d25d3b3fddd44054767ad/generate_with_diffusers.py#L56-L72
[LG157]: https://github.com/ModelTC/Qwen-Image-Lightning/blob/115d41afa959f0bc858d25d3b3fddd44054767ad/generate_with_diffusers.py#L157
[SP]: https://huggingface.co/spaces/linoyts/Qwen-Image-Edit-2509-Inpaint/blob/main/app.py#L155-L204
[I12216]: https://github.com/huggingface/diffusers/issues/12216#issuecomment-3217943114
[I12216b]: https://github.com/huggingface/diffusers/issues/12216#issuecomment-3215096069
[I229]: https://github.com/QwenLM/Qwen-Image/issues/229
[I94]: https://github.com/QwenLM/Qwen-Image/issues/94
[I154]: https://github.com/QwenLM/Qwen-Image/issues/154
[I167]: https://github.com/QwenLM/Qwen-Image/issues/167
[I137]: https://github.com/QwenLM/Qwen-Image/issues/137
[I243]: https://github.com/QwenLM/Qwen-Image/issues/243
