import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videofixie.backends.video2x import VIDEO2X_PROCESSING_LABEL
from videofixie.domain.capabilities import GpuDevice
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import ProcessingJob, ProcessingStage
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import bundled_output_presets
from videofixie.domain.profiles import bundled_profiles
from videofixie.domain.release_presets import default_release_preset
from videofixie.jobs.runner import ProcessLogLine, StageRunResult
from videofixie.services.app import PlannedRelease
from videofixie.services.environment import MachineEnvironment, ToolStatus


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class ReleaseWorkerTest(unittest.TestCase):
    def test_release_worker_writes_live_log_and_finishes_output(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.release_worker import ReleaseWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "outputs" / "release.mp4"
            logs_root = Path(tmp_dir) / "runs"
            release = _planned_release(output_path)
            finished = []

            def fake_run_stage(stage, **kwargs):
                on_output = kwargs.get("on_output")
                if on_output is not None:
                    on_output(ProcessLogLine("stdout", f"live {stage.label}"))
                if stage.label == "Mux release streams":
                    output_path.write_bytes(b"ok")
                return StageRunResult(stage.label, stage.command, exit_code=0)

            worker = ReleaseWorker(release, run_logs_root=logs_root)
            worker.finished.connect(finished.append)
            with patch("videofixie.ui.release_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

            log_path = next(logs_root.glob("release-*/release.log"))
            text = log_path.read_text(encoding="utf-8")

        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0].succeeded)
        self.assertIn("VideoFixie release run", text)
        self.assertIn("status: running", text)
        self.assertIn("stdout: live Run Video2X AI processing", text)
        self.assertIn("status: succeeded", text)

    def test_release_worker_rejects_video2x_runtime_error(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.release_worker import ReleaseWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "outputs" / "release.mp4"
            release = _planned_release(output_path)
            finished = []

            def fake_run_stage(stage, **kwargs):
                del kwargs
                if stage.label == VIDEO2X_PROCESSING_LABEL:
                    return StageRunResult(stage.label, stage.command, exit_code=0, stdout=("device lost",))
                output_path.write_bytes(b"should not run")
                return StageRunResult(stage.label, stage.command, exit_code=0)

            worker = ReleaseWorker(release)
            worker.finished.connect(finished.append)
            with patch("videofixie.ui.release_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

        self.assertEqual(len(finished), 1)
        self.assertFalse(finished[0].succeeded)
        self.assertFalse(output_path.exists())


def _planned_release(output_path: Path) -> PlannedRelease:
    profile = bundled_profiles()[0]
    output_preset = next(preset for preset in bundled_output_presets() if preset.slug == "balanced")
    video2x_command = PlannedCommand("video2x", ("--fake",), VIDEO2X_PROCESSING_LABEL)
    mux_command = PlannedCommand("ffmpeg", ("--fake",), "Mux release streams")
    job = ProcessingJob(
        source_path=Path("samples/1.mp4"),
        output_path=output_path,
        profile=profile,
        stages=(
            ProcessingStage(VIDEO2X_PROCESSING_LABEL, video2x_command),
            ProcessingStage("Mux release streams", mux_command),
        ),
        output_preset=output_preset,
    )
    environment = MachineEnvironment(
        ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
        ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
        video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
        video2x_capabilities=None,
        preferred_gpu=GpuDevice(0, "NVIDIA", "Discrete GPU"),
    )
    media = MediaInfo(
        path="samples/1.mp4",
        format_name="mp4",
        duration_seconds=60,
        bit_rate=100,
        size_bytes=1000,
        video_streams=(),
        audio_streams=(),
    )
    return PlannedRelease(
        media=media,
        environment=environment,
        profile=profile,
        release_preset=default_release_preset(),
        output_preset=output_preset,
        job=job,
    )
