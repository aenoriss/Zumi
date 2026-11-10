# What the prop picture should look like for FLUX.2 [klein] and for TRELLIS: background, resolution, alpha — 2026-11-10

Research date: 2026-11-10. Primary sources: the TRELLIS and TRELLIS.2 source code and their maintainers' issue replies, the TRELLIS paper, fal's model sheet, BFL's docs and its reference `flux2` code, the diffusers klein pipeline, and the preprocessing code of Hunyuan3D-2, TripoSR, SF3D and TripoSG. No paid calls. Context: `pipeline/segment/experiments/prop_trellis.py` **[in-house]** (SAM 2 + BiRefNet cutout, enlarged to 1024 px, klein repaint on white, BiRefNet matte, fal TRELLIS).

Conventions: **[docs]** read in the cited code or page. **[est]** my inference. **[unverified]** not confirmable from a primary source.

## Summary

1. **TRELLIS never saw a background in training.** Its conditioning images are Blender renders with `film_transparent = True`, cropped to 1.2 × the alpha bounding box, resized to 518 and multiplied by alpha, so the object sits on **black** ([render.py L43](https://github.com/microsoft/TRELLIS/blob/main/dataset_toolkits/blender_script/render.py#L43), [components.py L103-136](https://github.com/microsoft/TRELLIS/blob/main/trellis/datasets/components.py#L103-L136)) **[docs]**. Inference does the same to your picture. Any background pixels that survive are out of distribution.
2. **A partly transparent RGBA picture is used as-is. Any other picture goes through `rembg` u2net**, then a crop at alpha > 0.8 × 255, 1.2× margin, 518 px and premultiplication ([trellis_image_to_3d.py L82-116](https://github.com/microsoft/TRELLIS/blob/main/trellis/pipelines/trellis_image_to_3d.py#L82-L116)) **[docs]**. An RGB picture on white therefore depends on u2net, a 2020 salient-object model that the maintainers call "only for demo" ([#46](https://github.com/microsoft/TRELLIS/issues/46)) **[docs]**. Whether fal runs this same step is not documented ([sheet](https://fal.ai/models/fal-ai/trellis/llms.txt)) **[unverified]**.
3. **The maintainer names leftover background as the cause of flat output**: "Those remaining background parts may make the model to interpret the image as poster-liked object" ([#46](https://github.com/microsoft/TRELLIS/issues/46)) **[docs]**. That is your failure (d) exactly.
4. **For flat 2D drawings the TRELLIS.2 maintainer recommends upscaling and a more 3D-rendered look**: "try upscaling the image and adjusting its style to make it look more like 3D rendering… Some planar 2D drawings in the training set may be causing this issue" ([TRELLIS.2 #45](https://github.com/microsoft/TRELLIS.2/issues/45)) **[docs]**.
5. **klein never upscales a reference.** References are only capped: 2024² px for one reference, 1024² px each when there are several. Anything under 64 px on a side is rejected, and alpha is dropped with `convert("RGB")` ([flux2 sampling.py L52-65, L178-237](https://github.com/black-forest-labs/flux2/blob/main/src/flux2/sampling.py#L52-L65)) **[docs]**. The latent works in 16 px tokens, so a 150 px reference is about 9 × 9 = 81 tokens, against 4,096 for the 1024² output **[est from code]**. A small reference leaves the model to invent nearly all the detail.
6. **BFL gives no guidance on isolating a subject or on low-resolution references** **[docs, absence]**. For klein its guide says "What you write is exactly what the model receives", with no prompt upsampling, and recommends prose plus "`Style: [style]. Mood: [mood].` at the end" ([prompt reference](https://docs.bfl.ml/guides/prompting_unified_reference.md)) **[docs]**.
7. **Every comparable image-to-3D pipeline mats the object first.** Hunyuan3D-2, TripoSR, SF3D, TripoSG and TRELLIS.2 all remove the background or use the given alpha, then recentre the object with a margin (§ 3) **[docs]**.

## 1. TRELLIS (v1, what `fal-ai/trellis` serves)

**The preprocessing** ([L82-116](https://github.com/microsoft/TRELLIS/blob/main/trellis/pipelines/trellis_image_to_3d.py#L82-L116)) **[docs]**:

```python
if input.mode == 'RGBA':
    alpha = np.array(input)[:, :, 3]
    if not np.all(alpha == 255):
        has_alpha = True
if has_alpha: output = input
else: ... scale = min(1, 1024 / max_size) ... rembg.new_session('u2net') ... rembg.remove(input, ...)
bbox = np.argwhere(alpha > 0.8 * 255)
size = int(size * 1.2)
output = output.resize((518, 518), Image.Resampling.LANCZOS)
output = output[:, :, :3] * output[:, :, 3:4]
```

What happens to each kind of picture:

- **Transparent background (RGBA with real alpha)**: the alpha is trusted as given, the object is cropped square with a 20% margin, resized to 518 and put on black. This matches training (Summary 1).
- **RGBA with alpha all 255, or plain RGB**: the image is downscaled to 1024 if larger, then u2net cuts it. On a white background u2net usually finds the object, but its matte quality decides the result **[est]**. In [#76](https://github.com/microsoft/TRELLIS/issues/76) a "square floor beneath the object" went away when the user swapped in RMBG 2.0, which "generates the alpha channel more reliably" **[docs]**. This is the likeliest mechanism for your failure (c) **[est]**.
- **Cluttered background**: u2net keeps whatever it finds salient, such as a table top or a neighbour, and the model reads the whole silhouette as one object, a "poster-liked object" ([#46](https://github.com/microsoft/TRELLIS/issues/46)) **[docs]**.
- **Small source**: after the crop, the object always fills about 83% of 518 px (1/1.2) **[est from code]**. Size never changes framing. It only changes sharpness: a 150 px object is LANCZOS-upscaled 3.5× into a blur before DINOv2 sees it ([encode_image L133](https://github.com/microsoft/TRELLIS/blob/main/trellis/pipelines/trellis_image_to_3d.py#L118-L143)) **[docs]**. No source states a minimum useful size **[unverified]**.
- **The demo's own instruction**: "If the image has alpha channel, it be used as the mask. Otherwise, we use `rembg` to remove the background" ([app.py L256](https://github.com/microsoft/TRELLIS/blob/main/app.py#L256)) **[docs]**. TRELLIS.2's demo says "preferably with an alpha-masked foreground object" ([TRELLIS.2 app.py L520](https://github.com/microsoft/TRELLIS.2/blob/main/app.py#L520)) **[docs]**.

**Failure modes the sources document:**

- **Flat planes**: background is the first fix and "lower stage 1 guidance strength and different seeds" the second, for images that "lack 3D information" ([#46](https://github.com/microsoft/TRELLIS/issues/46)) **[docs]**. On fal that is `ss_guidance_strength`, default 7.5 ([sheet](https://fal.ai/models/fal-ai/trellis/llms.txt)) **[docs]**.
- **Severe artifacts and holes without background removal** in TRELLIS.2 ([#65](https://github.com/microsoft/TRELLIS.2/issues/65)) **[docs]**.
- **Cartoon and anime input**: proportions get distorted ([#70](https://github.com/microsoft/TRELLIS/issues/70), user reports, no maintainer reply) **[docs]**.
- **Baked lighting**: the paper says the model "does not separate lighting effects… resulting in baked-in shading and highlights from the reference image" ([arXiv 2412.01506, App. E](https://arxiv.org/html/2412.01506)) **[docs]**. Training renders use "a smooth area lighting" (same, App. B) **[docs]**.
- **Thin structures** such as chair legs: none of the sources I read address them **[unverified]**.

**TRELLIS.2** uses the same rule (alpha if present) but swaps u2net for BiRefNet with `briaai/RMBG-2.0` at 1024 px, and uses a 1.0× margin instead of 1.2× ([trellis2_image_to_3d.py L127-162](https://github.com/microsoft/TRELLIS.2/blob/main/trellis2/pipelines/trellis2_image_to_3d.py#L127-L162), [pipeline.json](https://huggingface.co/microsoft/TRELLIS.2-4B/blob/main/pipeline.json)) **[docs]**.

## 2. FLUX.2 [klein] 4B reference editing

- **What klein is**: "4 (step-distilled)" inference steps, sub-second, Apache 2.0 ([overview](https://docs.bfl.ml/flux_2/flux2_overview.md)) **[docs]**. Diffusers ignores guidance above 1 for distilled models ([pipeline_flux2_klein.py L587](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L587)) **[docs]**. The API has no guidance or steps parameter ([API ref](https://docs.bfl.ml/api-reference/models/generate-or-edit-an-image-with-flux2-%5Bklein%5D-4b.md)) **[docs]**.
- **How many references**: up to 4 for klein, against 8 for pro and max (same overview) **[docs]**. BFL markets [max] alone for "faithful style representation" (same) **[docs]**. klein makes no such claim.
- **How references are fed**: each reference is VAE-encoded at its own size, never upscaled (Summary 5). References are told apart only by a time-offset position id (10, 20, …), and no weight parameter exists ([sampling.py L76](https://github.com/black-forest-labs/flux2/blob/main/src/flux2/sampling.py#L76), [diffusers L766-784](https://github.com/huggingface/diffusers/blob/main/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py#L766-L784)) **[docs]**. What each image contributes is set in the prompt: "Specify what each image supplies… Put the base image first" ([multi-reference guide](https://docs.bfl.ml/guides/prompting_editing_multi_reference.md)) **[docs]**. Whether the hosted API resizes the same way is not stated **[unverified]**.
- **Style**: BFL's pitch is photorealism: "maintaining photorealism that matches professional photography" ([editing](https://docs.bfl.ml/flux_2/flux2_image_editing.md)) **[docs]**. For a style edit the guide says to "say what should keep its shape" ([single-reference guide](https://docs.bfl.ml/guides/prompting_editing_single_reference.md)) **[docs]**. A crop that looks like a photo of a painted room, with its background and soft focus, plausibly pulls the output toward photography. A cutout on white looks like a product shot of an illustration **[est]**.
- **Extraction onto white**: the closest documented pattern is the product edit "…on white background, studio lighting" (same guide) **[docs]**. There is no documented recipe for "extract one object from a scene" **[docs, absence]**. Your failure (a), where the neighbour was kept, is consistent with the prompt not saying which object. The `what` field in the current code addresses that **[in-house, est]**.

## 3. Other image-to-3D pipelines

| Model | Background handling | Framing |
|---|---|---|
| Hunyuan3D-2 | rembg when RGB; composites onto **white** | recentred, `border_ratio` 0.15, 512 px ([preprocessors.py](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/hy3dgen/shapegen/preprocessors.py)) |
| TripoSR | rembg unless `--no-remove-bg` | `foreground_ratio` 0.85 ([run.py](https://github.com/VAST-AI-Research/TripoSR/blob/main/run.py)) |
| SF3D / SPAR3D | rembg | `foreground_ratio` 0.85 ([run.py](https://github.com/Stability-AI/stable-fast-3d/blob/main/run.py)) |
| TripoSG | uses alpha if valid, else RMBG-1.4; composites onto white | `padding_ratio` 0.1 ([image_process.py](https://github.com/VAST-AI-Research/TripoSG/blob/main/scripts/image_process.py)) |
| TRELLIS / TRELLIS.2 | alpha if present, else u2net / RMBG-2.0; composites onto **black** | 1.2× / 1.0× margin |

All **[docs]**. One trap: Hunyuan3D-2's `minimal_demo.py` calls `.convert("RGBA")` before testing `mode == 'RGB'`, so its rembg never runs, and a picture without alpha becomes a fully opaque mask ([minimal_demo.py L26-29](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/minimal_demo.py#L26-L29), [preprocessors.py L51](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/hy3dgen/shapegen/preprocessors.py#L51)) **[docs]**.

## 4. Verdict on the hypothesis

**The background is the best-supported cause, but it is two separate problems, and resolution is a separate, real cause.**

- **TRELLIS: background, through the alpha.** The model was trained only on matted objects on black (Summary 1). The maintainer ties leftover background to poster-flat output (#46). Failure (d) is this case directly. Failure (c) is the same problem one step removed: without alpha, the matte came from u2net, or from nothing if fal skips preprocessing **[unverified]**. Resolution matters less here, because every picture is resampled to 518. It still matters through blur, and the TRELLIS.2 maintainer recommends upscaling **[docs]**.
- **klein: background and resolution both, by different mechanisms.** A cluttered crop gives the model two subjects and a scene context, which explains (a) **[est]**. A 100-270 px reference is fed as 40-280 tokens and never upscaled, which explains (b) **[est from code]**. Neither effect is measured in any BFL source.
- **One tension in the current recipe** **[est]**: the repaint prompt asks for "evenly lit… no cast shadows". Soft form shading is in TRELLIS's training distribution ("smooth area lighting"), and the evidence for flat-coloured input pushes the other way (TRELLIS.2 #45; Art3D in `3d-generative-cheapest-2026-11.md` § 6). Fully flat light may flatten geometry. Keep "no cast shadows" and allow gentle shading.

## 5. Recommended input recipe

**To klein**: a single RGB image of the object alone, SAM 2 + BiRefNet cutout composited on white, upscaled so its long side is about 1024 px. Never send RGBA, because the alpha is dropped and transparent pixels become whatever RGB lies under them. Name the object (the `what` field) and the medium, and end the prompt with `Style: <painted style>. Mood: …`. Ask for "soft studio light from the upper front with gentle shading, no cast shadows", not "evenly lit". Output at 1024² **[est, from §§ 1-2]**.

**To TRELLIS**: RGBA PNG with a real alpha (BiRefNet on the repaint), the object complete with no ground or neighbour, at least about 518 px across the object after the 1.2× crop. Framing does not matter, because the code recentres. If the result is flat, lower `ss_guidance_strength` (for example 5) and try 2-3 seeds before changing anything else **[docs #46, est values]**.

## 6. Cheapest experiments to settle what the sources leave open

1. **Does fal TRELLIS mat an RGB picture? (0.04)** Send one repaint twice, once as RGBA and once flattened onto white RGB, with the same seed. Identical meshes mean fal runs u2net and the difference lies in the matte. A white slab means fal skips preprocessing.
2. **Reference size for klein (about 0.05)**: one cutout at 150 px (native), 512 px and 1024 px (LANCZOS upscale), same prompt and seed. Judge style fidelity and detail by eye.
3. **Shading vs geometry (about 0.07)**: two repaints of a flat-coloured prop, "evenly lit" against "gentle form shading", each through TRELLIS (0.02). Compare thickness, for example the bounding-box depth ratio of the GLB.
