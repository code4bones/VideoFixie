import dataclasses
import importlib.util
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from videofixie.domain.benchmarks import Video2XBenchmarkVariant
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import JobProgress, ProcessingJob, ProcessingStage, TestSegment
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import preview_output_preset
from videofixie.domain.profiles import ProcessingProfile
from videofixie.backends.video2x import VIDEO2X_PROCESSING_LABEL
from videofixie.jobs.runner import ProcessLogLine, StageRunResult
from videofixie.services.app import PlannedBenchmarkVariant, PlannedPreview, PlannedVideo2XBenchmark
from videofixie.services.environment import MachineEnvironment, ToolStatus


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class BenchmarkWorkerTest(unittest.TestCase):
    def test_worker_continues_after_failed_variant(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.benchmark_worker import BenchmarkWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_1 = Path(tmp_dir) / "one.mp4"
            output_2 = Path(tmp_dir) / "two.mp4"
            benchmark = _benchmark((output_1, output_2))
            finished = []
            calls = []

            def fake_run_stage(stage, **kwargs):
                calls.append(stage.command.label)
                if stage.command.label == "shared cut":
                    return StageRunResult(stage.label, stage.command, exit_code=0)
                if stage.command.label == "variant one":
                    return StageRunResult(stage.label, stage.command, exit_code=1, stderr=("failed",))
                output_2.write_bytes(b"ok")
                on_progress = kwargs.get("on_progress")
                if on_progress is not None:
                    on_progress(JobProgress(current_frame=1, total_frames=1, percent=100.0, fps=2.5))
                return StageRunResult(
                    stage.label,
                    stage.command,
                    exit_code=0,
                    progress=(JobProgress(current_frame=1, total_frames=1, percent=100.0, fps=2.5),),
                )

            worker = BenchmarkWorker(benchmark)
            worker.variantFinished.connect(finished.append)
            with patch("videofixie.ui.benchmark_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

        self.assertEqual(len(finished), 2)
        self.assertEqual(calls, ["shared cut", "variant one", "variant two"])
        self.assertIsNotNone(finished[0].error)
        self.assertIsNone(finished[0].output_path)
        self.assertEqual(finished[1].output_path, output_2)

    def test_worker_respects_parallel_variant_limit(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.benchmark_worker import BenchmarkWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_paths = (
                Path(tmp_dir) / "one.mp4",
                Path(tmp_dir) / "two.mp4",
                Path(tmp_dir) / "three.mp4",
            )
            benchmark = _benchmark(output_paths)
            finished = []
            lock = threading.Lock()
            active = 0
            max_active = 0
            outputs_by_label = {
                "variant one": output_paths[0],
                "variant two": output_paths[1],
                "variant three": output_paths[2],
            }

            def fake_run_stage(stage, **kwargs):
                nonlocal active, max_active
                if stage.command.label == "shared cut":
                    return StageRunResult(stage.label, stage.command, exit_code=0)
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    time.sleep(0.05)
                    outputs_by_label[stage.command.label].write_bytes(b"ok")
                    return StageRunResult(stage.label, stage.command, exit_code=0)
                finally:
                    with lock:
                        active -= 1

            worker = BenchmarkWorker(benchmark, max_parallel_jobs=2)
            worker.variantFinished.connect(finished.append)
            with patch("videofixie.ui.benchmark_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

        self.assertEqual(len(finished), 3)
        self.assertEqual(max_active, 2)
        self.assertTrue(all(run.output_path is not None for run in finished))

    def test_worker_rejects_video2x_vulkan_failure_even_when_output_exists(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.benchmark_worker import BenchmarkWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "corrupt.mp4"
            benchmark = _benchmark((output_path,))
            planned_variant = benchmark.variants[0]
            original_job = planned_variant.preview.job
            video2x_command = PlannedCommand("video2x", ("--fake",), VIDEO2X_PROCESSING_LABEL)
            job = dataclasses.replace(
                original_job,
                stages=(
                    original_job.stages[0],
                    ProcessingStage(VIDEO2X_PROCESSING_LABEL, video2x_command),
                ),
            )
            preview = dataclasses.replace(planned_variant.preview, job=job)
            benchmark = dataclasses.replace(
                benchmark,
                variants=(dataclasses.replace(planned_variant, preview=preview),),
            )
            finished = []

            def fake_run_stage(stage, **kwargs):
                del kwargs
                if stage.command.label == "shared cut":
                    return StageRunResult(stage.label, stage.command, exit_code=0)
                output_path.write_bytes(b"bad but present")
                return StageRunResult(
                    stage.label,
                    stage.command,
                    exit_code=0,
                    stdout=("vkQueueSubmit failed -4",),
                )

            worker = BenchmarkWorker(benchmark)
            worker.variantFinished.connect(finished.append)
            with patch("videofixie.ui.benchmark_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

        self.assertEqual(len(finished), 1)
        self.assertIsNone(finished[0].output_path)
        self.assertIsNotNone(finished[0].error)
        assert finished[0].error is not None
        self.assertIn("Vulkan", finished[0].error)

    def test_worker_writes_run_logs_for_shared_cut_and_variants(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.benchmark_worker import BenchmarkWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_1 = Path(tmp_dir) / "one.mp4"
            output_2 = Path(tmp_dir) / "two.mp4"
            logs_root = Path(tmp_dir) / "runs"
            benchmark = _benchmark((output_1, output_2))
            finished = []

            def fake_run_stage(stage, **kwargs):
                on_output = kwargs.get("on_output")
                if on_output is not None:
                    on_output(ProcessLogLine("stdout", f"live {stage.command.label}"))
                if stage.command.label == "shared cut":
                    return StageRunResult(stage.label, stage.command, exit_code=0, stdout=("cut",))
                if stage.command.label == "variant one":
                    return StageRunResult(stage.label, stage.command, exit_code=1, stderr=("failed",))
                output_2.write_bytes(b"ok")
                return StageRunResult(stage.label, stage.command, exit_code=0, stdout=("ready",))

            worker = BenchmarkWorker(benchmark, run_logs_root=logs_root)
            worker.variantFinished.connect(finished.append)
            with patch("videofixie.ui.benchmark_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

            log_paths = sorted(logs_root.glob("variants-*/**/*.log"))
            shared_log = next(path for path in log_paths if path.name == "shared-source.log")
            failed_log = next(path for path in log_paths if "variant-01" in path.name)
            completed_log = next(path for path in log_paths if "variant-02" in path.name)
            shared_text = shared_log.read_text(encoding="utf-8")
            failed_text = failed_log.read_text(encoding="utf-8")
            completed_text = completed_log.read_text(encoding="utf-8")

        self.assertEqual(len(finished), 2)
        self.assertGreaterEqual(len(log_paths), 3)
        self.assertIn("shared cut", shared_text)
        self.assertIn("status: running", shared_text)
        self.assertIn("stdout: live shared cut", shared_text)
        self.assertIn("failed", failed_text)
        self.assertIn("stdout: live variant one", failed_text)
        self.assertIn("status: succeeded", completed_text)
        self.assertIn("stdout: live variant two", completed_text)
        self.assertEqual(finished[0].log_path, failed_log)

    def test_preview_worker_writes_run_log(self) -> None:
        from PySide6.QtWidgets import QApplication

        from videofixie.ui.preview_worker import PreviewWorker

        app = QApplication.instance() or QApplication([])
        del app
        with tempfile.TemporaryDirectory() as tmp_dir:
            logs_root = Path(tmp_dir) / "runs"
            output_path = Path(tmp_dir) / "preview.mp4"
            profile = ProcessingProfile(
                slug="preview-profile",
                name="Preview Profile",
                summary="Fixture",
                processor="realcugan",
                model="models-se",
                scale=2,
                noise_level=None,
            )
            command = PlannedCommand("python", ("-c", "pass"), "preview command")
            job = ProcessingJob(
                source_path=Path("samples/1.mp4"),
                output_path=output_path,
                profile=profile,
                stages=(ProcessingStage("preview command", command),),
            )

            def fake_run_stage(stage, **kwargs):
                return StageRunResult(stage.label, stage.command, exit_code=0, stdout=("preview-ready",))

            worker = PreviewWorker(job, run_logs_root=logs_root)
            with patch("videofixie.ui.preview_worker.SubprocessJobRunner.run_stage", side_effect=fake_run_stage):
                worker.run()

            log_paths = sorted(logs_root.glob("preview-*/preview.log"))
            text = log_paths[0].read_text(encoding="utf-8")

        self.assertEqual(len(log_paths), 1)
        self.assertIn("VideoFixie preview run", text)
        self.assertIn("preview command", text)
        self.assertIn("preview-ready", text)


def _benchmark(output_paths: tuple[Path, ...]) -> PlannedVideo2XBenchmark:
    media = MediaInfo(
        path="samples/1.mp4",
        format_name="mp4",
        duration_seconds=60,
        bit_rate=100,
        size_bytes=1000,
        video_streams=(),
        audio_streams=(),
    )
    environment = MachineEnvironment(
        ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
        ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
        video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
        video2x_capabilities=None,
        preferred_gpu=None,
    )
    segment = TestSegment("Preview", 1, 2)
    variants = []
    labels = ("one", "two", "three", "four")
    for index, output_path in enumerate(output_paths, start=1):
        profile = ProcessingProfile(
            slug=f"variant-{index}",
            name=f"Variant {index}",
            summary="Benchmark fixture",
            processor="realcugan",
            model="models-se",
            scale=2,
            noise_level=None,
        )
        command = PlannedCommand("python", ("-c", "pass"), f"variant {labels[index - 1]}")
        shared_cut = PlannedCommand("python", ("-c", "pass"), "shared cut")
        job = ProcessingJob(
            source_path=Path("samples/1.mp4"),
            output_path=output_path,
            profile=profile,
            stages=(
                ProcessingStage(shared_cut.label, shared_cut),
                ProcessingStage(command.label, command),
            ),
        )
        preview = PlannedPreview(media=media, environment=environment, profile=profile, segment=segment, job=job)
        variants.append(
            PlannedBenchmarkVariant(
                variant=Video2XBenchmarkVariant(profile=profile, label=profile.name, parameters="fixture"),
                preview=preview,
            )
        )
    return PlannedVideo2XBenchmark(
        media=media,
        environment=environment,
        segment=segment,
        output_preset=preview_output_preset(),
        variants=tuple(variants),
    )
