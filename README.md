# VideoFixie

VideoFixie is a local desktop application for restoring and upscaling old or low-resolution video.

The first implementation layer focuses on deterministic, testable foundations:

- media probing through `ffprobe`;
- Video2X capability detection and command planning;
- portable processing profiles;
- preview-first job planning;
- progress parsing.

The GUI will sit on top of these layers and must not build backend commands directly.

Inspect the local environment:

```bash
python3 -m videofixie.cli env
```

Analyze a source video:

```bash
python3 -m videofixie.cli probe samples/1.mp4
```

Print a preview plan without running expensive AI inference:

```bash
python3 -m videofixie.cli plan-preview samples/1.mp4 --start 0 --duration 15
python3 -m videofixie.cli plan-preview samples/1.mp4 --output balanced --start 0 --duration 15
```

Launch the desktop UI:

```bash
./run-videofixie.sh
```

Or launch the module directly:

```bash
.venv/bin/python -m videofixie.ui.app --source samples/1.mp4
```

In the UI, select a test segment on the timeline and press `Run Preview`.
Use `Profile` for AI/model/scale/noise selection and `Output` for the encoding preset.
The same button changes to `Cancel Preview` while the job is running.
The preview runs in the background, can be cancelled, writes logs into `Properties`, and opens the result in the `Processed` tab when finished.
IN/OUT fields accept exact timecodes such as `12.5`, `1:02.500`, or `1:02:03.250`.
`Large View` opens fullscreen playback for Original/Processed and a separate resizable side-by-side window for Split; Space toggles play/stop there.
Use `Properties` for source/environment/profile details and the planned/run command log.
Use `Settings` for the active processing backend, tool paths, output/cache/models directories, preferred GPU, VapourSynth Python/vspipe diagnostics, and default profile/output preset.
Use `Release` to open the Release Preset Wizard for guided final-export choices with Recommended defaults and a technical summary.
VapourSynth preview profiles currently use BestSource plus built-in resize filters as a runnable baseline; external AI model plugins are not bundled yet.

Preview cuts and result history are persisted in a local SQLite database:

- `Save Cut` stores the current named segment, selected backend/profile and output preset for the source file;
- a source can have multiple saved cuts, shown in the `Cut` list;
- `Load Cut` restores the selected segment and its profile/output choices;
- reopening the same file restores the most recently saved cut;
- opening a different filename without saved cuts resets the timeline to the default preview range;
- successful preview runs are added to the `Result` list with links to output files;
- `Load Result` opens a saved output in `Processed`/`Split` for comparison.

By default the database lives in the current working directory as `./videofixie.sqlite3`.
Managed model downloads should use the configured models directory, defaulting to `./models`, not `$HOME`.

Run deterministic tests with:

```bash
python3 -m unittest discover -v
```
