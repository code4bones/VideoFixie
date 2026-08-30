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
Video2X may still return exit code 0 and write an MP4 after this failure; treat the preview as
corrupt and do not mark it ready when this marker appears in stdout/stderr.

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
- no denoise and supported explicit denoise levels
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
VapourSynth is tracked as its own backend, not as a Video2X replacement inside the same adapter. On Linux, prefer detecting an installed Python/VapourSynth runtime and `vspipe` path. The preferred install path for VideoFixie is the official pip flow:

```text
pip install vapoursynth
vapoursynth config
```

Reference: `https://vapoursynth.com/doc/installation.html`

Windows portable archives are useful as references but should not be treated as a Linux runtime.

The default VapourSynth restoration profile is `vapoursynth-natural-x2`. It uses BestSource for decode and built-in VapourSynth primitives for a conservative local restoration chain:

1. source decode and high-bit-depth working format;
2. mild compression cleanup using luma median and chroma blur;
3. conservative temporal denoise with `std.AverageFrames`, preserving frame count and FPS;
4. x2 upscale with `resize.Spline36`;
5. restrained luma sharpen blended back into the upscaled clip;
6. subtle source texture reintroduction with a high-frequency diff;
7. final `YUV420P8` handoff to the existing encode/mux path.

The Lanczos/Bicubic VapourSynth profiles remain available as resize baselines, not restoration profiles. External AI plugins and model parameters must be introduced only after their capabilities are detected and documented.

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

## Video2X local layout
Prefer an unpacked/local Video2X runtime over AppImage execution:

- executable: `./bin/video2x`;
- models: `./share/video2x/models`;
- runtime working directory for Video2X stages: `./share/video2x`.

Video2X 6.4 has no documented `--model-dir` option and resolves model files through relative paths such as `models/realcugan/models-se/up2x-denoise1x.param`. VideoFixie therefore preflights the required `.param`/`.bin` files and runs the Video2X processing stage from the parent directory of the configured models directory while passing preview input/output paths as absolute paths.

Do not auto-detect `Video2X-x86_64.AppImage` as the default Video2X executable. AppImage can still be configured manually for experiments, but the normal project-local runtime should be unpacked and inspectable.

When only the AppImage is available locally, run:

```bash
python3 scripts/bootstrap_video2x_runtime.py --force
```

The bootstrap step extracts the AppImage into ignored local runtime files under `./share/video2x`, creates `./share/video2x/models` as a symlink to the extracted model directory, and writes `./bin/video2x` as a wrapper. This is an explicit setup operation, not GUI startup behavior.

Do not assume every RealCUGAN model supports every noise level. In the verified Video2X 6.4 AppImage model set, `models-pro` includes `up2x-no-denoise`, `up2x-conservative`, and `up2x-denoise3x`, but not `up2x-denoise1x`; `models-se` includes `up2x-denoise1x`. The current Video2X 6.4 CLI rejects `-n -1`, so conservative model files must not be treated as runnable through Video2X unless a future backend capability proves otherwise.

## Video2X variant benchmark
Video2X quality should be compared on identical source content before choosing a final profile. The Variants workflow builds several temporary Video2X profiles for the current TestSegment, prepares the shared preview source once, and runs Video2X variants through a bounded queue with the same preview output preset. The UI exposes a small parallelism limit capped at 3 active Video2X variants; use lower values if VRAM pressure appears.
Every Variants run writes diagnostics to `cache/runs/<run-id>/`: `shared-source.log` for the cut
stage and `variant-XX-*.log` files for each tile. Logs include command, cwd, stdout, stderr,
exit code, elapsed time and final status.
Known fatal backend markers such as `vkQueueSubmit failed` and `device lost` must fail the variant
even when the backend process exits with code 0, because the produced MP4 can be visually corrupt.
Each nominally completed Preview/Variant output is then passed through an FFmpeg decode validation
stage before it is marked Ready or offered to the player. Decoder errors such as invalid H.264 NAL
units or AAC bitstream errors must fail the tile and remain visible in the run log.
If Video2X writes final encoder statistics and then remains alive without output, the runner should
terminate the silent stage through the inactivity watchdog and keep the tile failed for inspection.

Default live-action matrix:
- RealCUGAN `models-pro`: default/no denoise, explicit noise 0 and denoise 3 where installed;
- RealCUGAN `models-se`: default/no denoise, explicit noise 0, denoise 1 and denoise 2 where installed;
- RealCUGAN `models-nose`: explicit noise 0 where installed; default is excluded because Video2X 6.4 tries the missing conservative model file;
- RealESRGAN `realesrgan-plus` x4 only when capability and model-file validation says it is runnable.

Anime-specific Video2X models are intentionally excluded from the default live-action matrix. A failed variant should record its error and allow the remaining variants to continue.
