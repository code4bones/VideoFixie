# VideoFixie - AGENTS.md

## Purpose
VideoFixie is a local desktop application for restoring and upscaling old/low-resolution video. The immediate target is Linux/Kubuntu with an NVIDIA GPU, but architecture must not hard-code one machine.

The application exists to make video restoration repeatable and understandable. It should expose expert controls without forcing the user to memorize Video2X/FFmpeg CLI flags.

## Primary stack
- Python 3.12+
- PySide6 for desktop GUI
- FFmpeg / ffprobe for media analysis, cutting previews, encoding and muxing
- MediaInfo where useful for human-readable metadata
- Video2X 6.x as the initial AI processing backend
- subprocess-based integration first; do not embed or fork Video2X unless a clear need appears
- JSON/YAML profile files for processing presets

## Development principles
1. Keep GUI, domain logic, command construction and process execution separate.
2. Never scatter raw CLI strings throughout widgets. Build commands in dedicated backend/adapters.
3. Every generated command must be inspectable by the user before execution.
4. Preserve source audio/subtitles/metadata whenever practical; never silently discard streams.
5. Preview-first workflow is mandatory. Expensive full-video processing should not be the primary iteration path.
6. Processing must be cancellable and progress-aware.
7. Do not invent unsupported model parameters. Capabilities must come from the selected backend/version.
8. Prefer non-destructive output. Never overwrite source files by default.
9. Keep processing profiles serializable and portable.
10. Avoid hidden "magic". If the app applies denoise, grain, resize or interpolation, expose that in the job summary.

## Current verified environment
The current Video2X version used during initial experiments is 6.4.0.

Available processors observed in its CLI:
- libplacebo
- realesrgan
- realcugan
- rife

Current test GPU:
- NVIDIA GeForce RTX 3060 Laptop GPU
- Vulkan device index in Video2X: 0

The machine also exposes an AMD integrated GPU and llvmpipe. Device indices are runtime data and MUST NOT be hard-coded.

## Known findings from initial experiments
- RealESRGAN `realesrgan-plus` with scaling factor 2 attempted to load `realesrgan-plus-x2.param` and failed because that model file is not present.
- RealESRGAN x4 started fast (~16-17 fps on a 500x360 source) but produced repeated `vkQueueSubmit failed -4` / Vulkan device-lost errors.
- Kernel logs did not show NVIDIA Xid errors during that failure, suggesting a backend/Vulkan-context issue rather than a full GPU driver reset.
- RealCUGAN `models-pro`, scale x2 ran stably on the same RTX 3060 at roughly 2.7 fps.
- RealCUGAN x2 visibly improved the image but introduced a subtle AI/plastic/over-smoothed look.
- Therefore the GUI must make model/noise/profile comparison easy rather than treating one model as universally correct.

## Architecture expectations
Use a layered design similar to:

```text
videofixie/
  app/
    ui/
    domain/
    services/
    backends/
    profiles/
    jobs/
  docs/
  tests/
```

Suggested responsibilities:
- `ui/`: windows, dialogs, preview, comparison, job controls
- `domain/`: media/job/profile models independent of Qt
- `services/`: orchestration, preview workflow, validation
- `backends/ffmpeg.py`: ffprobe/ffmpeg command building and execution
- `backends/video2x.py`: Video2X capability detection and command building
- `profiles/`: preset schema and bundled presets
- `jobs/`: process lifecycle, progress parsing, cancellation, logs

Do not let Qt widgets directly invoke subprocesses.

## UX goals
The main workflow should be:

1. Open video.
2. Analyze source automatically.
3. Show concise technical facts: resolution, FPS/mode, scan type, codec, video bitrate, aspect ratio, audio tracks.
4. Select a short preview range, default around 10-15 seconds.
5. Choose a restoration profile or advanced settings.
6. Run preview.
7. Compare original vs processed output.
8. Adjust parameters and repeat.
9. Save chosen settings as a reusable profile.
10. Run full job or queue multiple files.

The user should always know:
- what model is used;
- scale/output size;
- denoise/noise setting;
- encoder and quality;
- selected GPU;
- expected/observed processing FPS;
- estimated remaining time.

## Initial product scope
Implement first:
- local file open
- ffprobe analysis
- Video2X executable discovery/version detection
- Vulkan device listing via Video2X
- preview range selection
- RealCUGAN processing
- RealESRGAN processing where supported
- output codec/CRF controls
- progress parsing
- cancel/pause if backend supports it
- before/after playback or side-by-side comparison
- profiles
- processing queue

Do later:
- RIFE frame interpolation
- automatic recommendations based on source properties
- artificial film grain
- richer restoration chain before/after AI
- multiple backend engines beyond Video2X
- scene-based processing

## Safety / source integrity
- Source files are immutable from the application's point of view.
- Default output must use a new filename.
- Preview files should live in an application cache/temp directory.
- On cancellation, remove incomplete temporary files unless explicitly retained for debugging.
- Never delete user media automatically.

## Testing
Keep unit tests focused on deterministic logic:
- metadata parsing
- profile serialization
- command construction
- capability validation
- progress parser
- output naming

Do not require expensive AI inference in normal unit tests. Integration tests may be optional/manual when they depend on Video2X/GPU.

## Agent workflow
Before implementing a feature:
1. Read `AGENTS.md`.
2. Read relevant files under `docs/`.
3. Inspect current backend capabilities instead of assuming CLI syntax.
4. Keep changes scoped and maintain the separation between UI/domain/backend.

When changing command-line behavior, include the exact resulting command in logs/debug output so it is reproducible outside the GUI.
