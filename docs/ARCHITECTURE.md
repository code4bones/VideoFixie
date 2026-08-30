# Architecture

## Goal
VideoFixie is a desktop orchestration layer over media-analysis, AI-restoration and encoding tools. The application should remain usable even if specific backend tools change over time.

## High-level flow

```text
Source video
   |
   v
Probe / analyze (ffprobe, optional MediaInfo)
   |
   v
Source model
   |
   +--> Preview range selection
   |
   v
Processing backend + processing profile + output preset
   |
   v
Job planner
   |
   +--> optional ffmpeg pre-process
   +--> Video2X AI processor
   +--> optional ffmpeg post-process
   +--> mux/copy source streams
   |
   v
Preview/output
```

## Layers

### UI
PySide6 only. UI owns presentation state, not processing semantics.

Responsibilities:
- file selection;
- metadata presentation;
- profile controls;
- preview in/out selection;
- queue display;
- progress/log display;
- before/after comparison.

UI must not build shell commands directly.

### Domain
Pure Python models without Qt dependencies.

Suggested objects:
- `MediaInfo`
- `VideoStreamInfo`
- `AudioStreamInfo`
- `GpuDevice`
- `BackendCapabilities`
- `ProcessingProfile`
- `PreviewRange`
- `ProcessingJob`
- `JobResult`

### Backend adapters
Backend-specific capability discovery and command construction.

Backends are selected through a small registry of processing backend descriptors. The first execution backend is Video2X. VapourSynth is available for script-based preview pipelines through Python/vspipe diagnostics and explicit VapourSynth-compatible profiles. Video2X-only profiles must not be routed through VapourSynth.

#### FFmpeg adapter
- locate `ffmpeg` / `ffprobe`;
- probe source;
- cut preview segments;
- perform resize/post-processing;
- mux/copy streams;
- encode output.

#### Video2X adapter
- locate executable;
- read version;
- list devices;
- validate requested processor/model/scale combination;
- build arguments;
- parse progress;
- expose backend limitations.

Treat Video2X as a replaceable backend.

### Job runner
Centralized subprocess lifecycle management.

Must provide:
- stdout/stderr capture;
- structured logs;
- progress events;
- cancellation;
- pause/resume when backend supports it;
- exit-code handling;
- temporary file cleanup.

Prefer `QProcess` at the outer execution boundary if it simplifies Qt event integration, but keep command planning independent from Qt.

## Capability-driven UI
Controls must be derived from backend capabilities rather than static assumptions.

Example:
- if model supports only x4, do not offer x2 as a valid direct AI scale;
- if processor does not support noise control, disable/hide the control;
- GPU list comes from `video2x --list-devices`;
- version-specific behavior belongs in the Video2X adapter.

## Processing plans
A profile should compile into a processing plan rather than directly into one command.

Example:

```text
Profile: archival-natural-720

1. Create 15 s preview source (ffmpeg)
2. AI upscale x2 with RealCUGAN
3. Optional mild post-resize
4. Encode H.264 CRF 17
5. Copy/mux audio
```

Future plans may contain multiple stages, e.g. AI x4 followed by high-quality downscale and grain.

## Temporary storage
Use an application-specific cache directory, e.g. via Qt standard paths.

Store:
- preview source clips;
- partial stage outputs;
- logs;
- thumbnails.

Each job should receive an isolated temp directory.
Runtime diagnostics are written under project-local ignored storage, currently `cache/runs/<run-id>/`.
The run id is emitted into the Properties command log. Preview runs write `preview.log`; Video2X
benchmark runs write `shared-source.log` plus one `variant-XX-*.log` per tile. These logs are
plain text so a failed backend command can be inspected after the UI run has finished.

## Configuration
Keep two kinds of configuration separate:

### Machine configuration
- active processing backend;
- Video2X executable path;
- VapourSynth Python/vspipe paths;
- ffmpeg/ffprobe paths;
- preferred GPU;
- cache directory;
- default output directory;
- managed models directory.

Machine configuration is persisted locally in the current working directory SQLite database. The preferred local backend layout keeps executables under `./bin/` and shared backend data under `./share/`. The default managed Video2X models directory is `./share/video2x/models`, not `$HOME`, so future model downloads stay under the project/user-selected workspace. Video2X stages run from the parent directory of the configured models directory because Video2X 6.4 resolves model files relative to `models/...`.

### Processing profiles
Portable restoration settings without machine-specific absolute paths or GPU indices.
Profiles declare backend compatibility. A planner must reject incompatible backend/profile combinations instead of silently trying to run them through Video2X.

### Output presets
Portable encoding settings separate from restoration profiles.

Bundled output presets describe user intent:
- Preview;
- High Quality;
- Balanced;
- Compact;
- Archive.

Each preset compiles to explicit backend encoder settings such as codec, CRF and encoder preset. Preview/intermediate output defaults to a high-fidelity preview preset, while future full exports should default to a practical final-output preset.

### Saved cuts and preview results
Saved cuts are reusable source-specific test ranges. A single source may have many named cuts with backend/profile/output choices, while preview results are immutable links to processed files created from a cut snapshot. Legacy single-cut rows remain readable as fallback data.

### Release presets
Release presets are user-facing final export configurations. They compose lower-level output presets with container, stream preservation, destination and naming policy. The Release Preset Wizard must show recommended choices and a final technical summary before the preset is used for rendering.

### Model catalog
Model catalog and installation state are separate from processing profiles. A future Model Manager should discover bundled Video2X models and install trusted official models into the configured managed models directory.

## Error model
Translate raw backend failures into useful categories while preserving raw logs.

Examples:
- executable missing;
- unsupported parameter/model combination;
- model files missing;
- Vulkan device lost;
- decoder failure;
- encoder failure;
- disk full;
- cancelled by user.

Never hide stderr; provide an expandable raw-log view.
Also preserve stdout/stderr, command, cwd, exit code and elapsed time in the corresponding run log file.
