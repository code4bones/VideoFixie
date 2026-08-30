# UI / UX

## Main window
The main window should make the restoration loop obvious rather than exposing every backend flag immediately.

Suggested layout:

```text
+-----------------------------------------------------------+
| File | Profile | GPU | Settings                           |
+-----------------------------------------------------------+
| Preview / Compare                                         |
|                                                           |
|   video player                                            |
|                                                           |
|   [Original | Processed | Split]                          |
+-----------------------------------------------------------+
| Preview range / timeline                                  |
+-----------------------------------------------------------+
| Profile: Natural       Scale: 2x     Noise: default       |
| Processor: RealCUGAN   Model: models-se                   |
| Output: 1000x720       Codec: H264 CRF 17                 |
+-----------------------------------------------------------+
| [Run Preview] [Add Full Job]                              |
| Progress  80/442   18.1%   2.7 fps   ~02:10 remaining    |
+-----------------------------------------------------------+
```

Exact visuals may evolve; preserve the workflow.

## Properties
After opening a file, the Properties dialog should show restoration-relevant facts:
- resolution;
- display aspect ratio;
- FPS and CFR/VFR;
- progressive/interlaced;
- video codec;
- approximate video bitrate;
- duration;
- audio tracks.

Full ffprobe/MediaInfo data should be available in a details dialog, not dumped into the main screen. Environment, source facts, profile summary and command/run log belong in Properties so the main window stays focused on video review.

## Preview controls
Preview is central to the product.

Required:
- timeline/scrubber;
- start position;
- preview duration (default 15 s);
- quick presets: 5 / 10 / 15 / 30 s;
- ability to use current playhead as preview start.

The app should warn before running a full job if no preview has been successfully produced with the selected profile, but it need not forbid it.

## Profiles
Profiles should be the default UI. Advanced backend settings should be secondary.

Initial profile names can include:
- Natural
- Balanced
- Strong cleanup
- Experimental RealESRGAN

A profile summary should state what it actually does, e.g.:

```text
Natural
RealCUGAN / models-se / 2x
Minimal denoise, preserve texture
H.264 CRF 17
```

Allow:
- Save As profile;
- duplicate;
- rename;
- reset to bundled defaults.

## Advanced settings
Organize by semantic purpose, not by raw CLI syntax.

### AI
- processor;
- model;
- scale;
- noise level;
- GPU.

### Output
- named output preset;
- target dimensions / scale;
- codec;
- CRF/quality;
- encoder preset;
- pixel format when needed.

Output presets are separate from restoration profiles. The first bundled set is Preview, High Quality, Balanced, Compact and Archive.

### Streams
- preserve audio;
- preserve subtitles;
- preserve metadata.

### Experimental
Future options such as RIFE interpolation and grain can live here until mature.

## Command inspector
Every planned stage should have a reproducibility view in Properties.

Example:

```text
Stage 1 - preview cut
ffmpeg ...

Stage 2 - AI
video2x ...
```

Provide a copy button. This is important both for debugging and for expert users.

## Saved Cuts
The main preview controls should separate reusable ranges from rendered outputs. `Save Cut` should ask for a cut name before storing the current IN/OUT, kind, profile and output preset. `Load Cut` should open an explicit choice dialog and keep the inline `Cut` selector synchronized with the loaded range. `Result` lists generated preview files for visual comparison. Saving a cut with an existing label updates that cut only; other ranges for the same source remain available.

## Release Preset Wizard
Final export settings should be guided by a wizard rather than a single dense form. Each page should explain the current decision, visibly mark a safe contextual default as Recommended, and keep alternatives available. The final page must show both a human summary and exact technical settings.

## Compare view
At minimum support:
- Original
- Processed
- side-by-side
- resizable large side-by-side window for Split comparison
- Video2X variant comparison grid for the current test segment

Desired later:
- draggable split/wipe;
- synchronized zoom;
- synchronized playback;
- still-frame comparison.

Always synchronize time positions between original and processed preview.

## Video2X variant grid
The Variants tab benchmarks several practical Video2X live-action configurations on the current TestSegment without requiring the user to manually switch profiles between runs.
The top toolbar in this tab is reserved for live resource telemetry only:
- GPU load with a compact sparkline and current percent;
- CPU load with a compact sparkline and current percent;
- RAM current usage next to them.

Initial grid behavior:
- plan all variants from the same source segment and output preset;
- run variants sequentially by default to avoid VRAM contention;
- show an explicit queued/running/ready/failed state and keep a bounded active Video2X set;
- expose a small parallelism limit for advanced testing, capped at 3 active Video2X variants;
- show model, scale, noise mode, status, progress, elapsed time, observed fps and backend errors per tile;
- continue after a single variant fails;
- keep exact commands visible in Properties;
- allow opening a completed tile in Large View;
- allow applying a tile as the active Video2X processing profile.

Tiles should stay lightweight. Do not create a separate media player per variant tile; completed tiles open through the existing preview/Large View playback path.
Each benchmark run writes one ignored diagnostics directory containing the shared-source log and a
separate log file for every variant tile. Failed tiles should preserve enough error text in the card
and enough file path context in Properties to inspect the raw backend output later.

The default live-action set excludes anime-specific models. Separate anime/custom benchmark sets may be added later.

## Queue
A full processing job may take hours, so queue UI matters.

Each row should show:
- source filename;
- selected profile;
- current stage;
- progress;
- processing fps;
- ETA;
- status.

Actions:
- cancel current;
- remove pending;
- retry failed;
- open output directory;
- view logs.

Start with sequential processing. Parallel AI jobs can easily exhaust VRAM and are not necessary initially.

## Errors
Show human-oriented headline plus raw details.

Example:

```text
GPU processing stopped
Vulkan reported device lost while RealESRGAN was running.

[Show technical log]
```

Do not replace the raw backend message; retain it in the log.
The Properties command log should include `run_log:` or `run_log_dir:` entries for active preview
and Variants runs so failed tiles can be matched to `cache/runs/<run-id>/variant-XX-*.log`.

## Settings
Application settings should include:
- active processing backend;
- Video2X executable path;
- FFmpeg/ffprobe paths or auto-detection;
- preferred GPU;
- cache directory;
- output directory;
- managed models directory, defaulting to `./share/video2x/models`;
- default processing profile;
- default output preset;
- cache cleanup policy.

Backend-specific controls should be visible only for the selected backend. Video2X exposes its executable path, managed models directory and preferred Vulkan GPU.
VapourSynth exposes Python and `vspipe` paths for pip-installed runtime diagnostics and script-based preview execution. When VapourSynth is selected, the profile selector should move to a VapourSynth-compatible profile instead of leaving a Video2X-only profile selected.

On first run, run a lightweight environment check and clearly show missing dependencies.
