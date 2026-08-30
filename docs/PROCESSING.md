# Processing Pipeline

## Philosophy
Video restoration is subjective. The application should optimize for fast comparison and repeatability, not for a single automatic "best" setting.

A better-looking still frame can produce worse moving video. Therefore evaluate temporal stability, faces, textures and motion, not only sharpness.

## Preview-first workflow
Full AI inference can take hours. Every profile-tuning workflow should begin with a short representative source range.

Default preview duration: 10-15 seconds.

Good preview sections contain some combination of:
- faces;
- hair;
- motion;
- fine texture;
- text;
- flat surfaces;
- shadows;
- compression artifacts.

A preview clip may be generated using ffmpeg. For accurate in/out positions, re-encoding is acceptable for the preview source when necessary, but use high quality settings so the preview-generation encode does not dominate the result.

## Initial source example
One tested source had:
- 500x360;
- 25 fps CFR;
- progressive scan;
- H.264 AVC;
- approximately 385 kbit/s video bitrate;
- 4:2:0 8-bit.

This is a useful representative low-quality source: limited detail plus compression artifacts.

## Current Video2X 6.4.0 CLI capabilities observed
Processors:
- `libplacebo`
- `realesrgan`
- `realcugan`
- `rife`

Common relevant options:
- `-i / --input`
- `-o / --output`
- `-p / --processor`
- `-d / --device`
- `-s / --scaling-factor`
- `-w / --width`
- `-h / --height`
- `-n / --noise-level`
- `-c / --codec`
- `-e / --extra-encoder-option`

RealESRGAN models reported:
- `realesr-animevideov3`
- `realesrgan-plus-anime`
- `realesrgan-plus`

RealCUGAN models reported:
- `models-nose`
- `models-pro`
- `models-se`

RIFE is available for interpolation but is intentionally outside the first restoration pass.

## Verified GPU selection
Video2X device listing on the initial development machine returned:

```text
0. NVIDIA GeForce RTX 3060 Laptop GPU
1. AMD Radeon Graphics (RADV RENOIR)
2. llvmpipe
```

Do not assume this numbering on other machines. Always detect devices.

## Initial experimental findings

### RealESRGAN
`realesrgan-plus`, scale 2 attempted to access:

```text
models/realesrgan/realesrgan-plus-x2.param
```

and failed because the file did not exist.

Using x4 allowed inference to start, at approximately 16-17 fps on the tested 500x360 source, but after a short time emitted repeated:

```text
vkQueueSubmit failed -4
```

which corresponds to Vulkan device-lost behavior. Kernel NVIDIA logs showed no Xid at that time.

Do not present this combination as a stable default without further testing.

### RealCUGAN
Tested combination:

```text
processor: realcugan
model: models-pro
scale: 2
GPU: RTX 3060
H.264 CRF 17
```

Observed speed was roughly 2.7 fps. It completed a short preview stably.

Visual result improved apparent detail but introduced a subtle synthetic/plastic/smoothed look. This is an important UX requirement: the app must make it easy to compare softer profiles such as different RealCUGAN models and noise levels.

## Plastic / synthetic look
Possible visual symptoms:
- natural skin texture disappears;
- broad surfaces become unnaturally smooth;
- edges become too geometrically clean;
- fine structures look "rendered" or slightly polygonal;
- AI-created texture may differ between adjacent frames.

Avoid assuming that maximum denoise equals maximum quality.

For archival material, retaining a small amount of natural noise/texture can look more authentic than aggressive cleanup.

## Initial profile ideas
These are product-level starting points, not hard-coded truths.

### Natural
Goal: improve scale/details while retaining source character.
- RealCUGAN
- x2
- conservative/no denoise where supported
- high-quality encode
- no FPS interpolation

### Balanced
Goal: more cleanup at some risk of smoothing.
- RealCUGAN
- x2
- mild noise processing
- high-quality encode

### Experimental RealESRGAN
Goal: test detail recovery where backend is stable.
- RealESRGAN `realesrgan-plus`
- supported scale only
- clearly marked experimental until Vulkan/device-loss issue is understood

## Encoding
For preview comparisons, encode quality should be high enough not to mask model differences. Preview/intermediate encoding policy is separate from final export policy.

Initial preview H.264 example:

```text
codec: libx264
crf: 16
preset: slow
```

The GUI exposes named output presets instead of requiring raw CRF choices first. Bundled presets:
- Preview: high-fidelity H.264 for visual comparison;
- High Quality: high-quality H.264 final output;
- Balanced: practical H.264 size/quality tradeoff;
- Compact: HEVC/x265 for smaller files;
- Archive: very high-quality H.264, larger files expected.

Restoration profiles control AI/model/scale/noise behavior. Output presets control codec/CRF/encoder preset and stream-copy policy.
Profiles also declare compatible processing backends. The first bundled profiles target Video2X; future VapourSynth profiles should be explicit rather than being routed through Video2X by accident.

## VapourSynth notes
VapourSynth is tracked as a future backend, not as a Video2X replacement inside the same adapter. On Linux, prefer detecting an installed Python/VapourSynth runtime and `vspipe` path. The preferred install path for VideoFixie is the official pip flow:

```text
pip install vapoursynth
vapoursynth config
```

Reference: `https://vapoursynth.com/doc/installation.html`

Windows portable archives are useful as references but should not be treated as a Linux runtime.

## Output resolution
Do not force every source to 1920x1080.

Preserve aspect ratio. Prefer meaningful multiples or target dimensions and optionally letterbox/pillarbox only when the user requests a fixed canvas.

Examples:
- 500x360 x2 -> 1000x720
- 640x480 x2 -> 1280x960

For models that only support x4, a future plan may use AI x4 followed by a high-quality downscale. This must be represented explicitly as a multi-stage plan.

## Frame rate
Do not interpolate FPS during initial restoration tuning.

Keep original timestamps/frame rate unless the user explicitly enables RIFE. Upscaling and interpolation should be evaluated separately so artifacts have an identifiable cause.

## Audio and subtitles
AI processing applies to video frames only. Preserve/copy source audio and subtitle streams whenever possible.

## Progress
Video2X progress output contains data similar to:

```text
frame=80/442; fps=2.7; elapsed=...; remaining=...
```

Parse this into structured job progress:
- current frame;
- total frames;
- percent;
- processing fps;
- elapsed;
- estimated remaining.

Do not rely on exact spacing or terminal control characters; parser should tolerate variations.
