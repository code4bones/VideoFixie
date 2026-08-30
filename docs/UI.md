# UI / UX

## Main window
The main window should make the restoration loop obvious rather than exposing every backend flag immediately.

Suggested layout:

```text
+-----------------------------------------------------------+
| File | Profile | GPU | Settings                           |
+-----------------------------------------------------------+
| Source info            | Preview / Compare                |
| 500x360                |                                  |
| 25 fps CFR             |   video player                   |
| H.264 385 kb/s         |                                  |
| Progressive            |                                  |
|                        | [Original | Processed | Split]    |
+------------------------+----------------------------------+
| Preview range / timeline                                  |
+-----------------------------------------------------------+
| Profile: Natural       Scale: 2x     Noise: -1            |
| Processor: RealCUGAN   Model: models-se                   |
| Output: 1000x720       Codec: H264 CRF 17                 |
+-----------------------------------------------------------+
| [Run Preview] [Add Full Job]                              |
| Progress  80/442   18.1%   2.7 fps   ~02:10 remaining    |
+-----------------------------------------------------------+
```

Exact visuals may evolve; preserve the workflow.

## Source panel
After opening a file, automatically show only restoration-relevant facts:
- resolution;
- display aspect ratio;
- FPS and CFR/VFR;
- progressive/interlaced;
- video codec;
- approximate video bitrate;
- duration;
- audio tracks.

Full ffprobe/MediaInfo data should be available in a details dialog, not dumped into the main screen.

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
Every planned stage should have a reproducibility view such as "Show commands".

Example:

```text
Stage 1 - preview cut
ffmpeg ...

Stage 2 - AI
video2x ...
```

Provide a copy button. This is important both for debugging and for expert users.

## Compare view
At minimum support:
- Original
- Processed
- side-by-side
- resizable large side-by-side window for Split comparison

Desired later:
- draggable split/wipe;
- synchronized zoom;
- synchronized playback;
- still-frame comparison.

Always synchronize time positions between original and processed preview.

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

## Settings
Application settings should include:
- Video2X executable/AppImage path;
- FFmpeg/ffprobe paths or auto-detection;
- preferred GPU;
- cache directory;
- output directory;
- cache cleanup policy.

On first run, run a lightweight environment check and clearly show missing dependencies.
