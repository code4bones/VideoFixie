import sys
import threading
import time
import unittest
import tempfile
from pathlib import Path

from videofixie.backends.video2x import parse_progress_line
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import GeneratedFile, ProcessingStage
from videofixie.jobs.runner import CancellationToken, StageRunResult, SubprocessJobRunner


class SubprocessJobRunnerTest(unittest.TestCase):
    def test_run_command_captures_output_and_progress(self) -> None:
        command = PlannedCommand(
            sys.executable,
            (
                "-c",
                "print('frame=2/10; fps=3.5; elapsed=00:00:01; remaining=00:00:03')",
            ),
            "fake progress",
        )
        progress_seen = []

        result = SubprocessJobRunner(progress_parser=parse_progress_line).run_command(
            command,
            on_progress=progress_seen.append,
        )

        self.assertTrue(result.succeeded)
        self.assertIn("frame=2/10", result.stdout[0])
        self.assertEqual(len(result.progress), 1)
        self.assertEqual(progress_seen[0].current_frame, 2)

    def test_run_command_can_be_cancelled(self) -> None:
        command = PlannedCommand(
            sys.executable,
            ("-c", "import time; print('started', flush=True); time.sleep(5)"),
            "sleeping command",
        )
        token = CancellationToken()

        def cancel_soon() -> None:
            time.sleep(0.1)
            token.cancel()

        thread = threading.Thread(target=cancel_soon)
        thread.start()
        result = SubprocessJobRunner().run_command(command, cancellation_token=token)
        thread.join(timeout=1)

        self.assertTrue(result.cancelled)
        self.assertFalse(result.succeeded)
        self.assertIn("started", result.stdout)

    def test_run_command_times_out_after_output_inactivity(self) -> None:
        command = PlannedCommand(
            sys.executable,
            ("-c", "import time; print('started', flush=True); time.sleep(5)"),
            "silent command",
        )
        output = []

        result = SubprocessJobRunner(inactivity_timeout_seconds=0.2).run_command(command, on_output=output.append)

        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.runtime_error)
        self.assertIn("no output", result.runtime_error or "")
        self.assertIn("started", result.stdout)
        self.assertTrue(any(line.stream == "runtime" for line in output))

    def test_run_command_times_out_after_final_output_marker(self) -> None:
        command = PlannedCommand(
            sys.executable,
            (
                "-c",
                "import time; "
                "print('[FFmpeg] [libx264 @ 0x1] kb/s:296.77', flush=True); "
                "time.sleep(5)",
            ),
            "post encode hang",
        )
        output = []

        result = SubprocessJobRunner(
            final_output_detector=lambda line: "encoder summary" if "kb/s:" in line.text else None,
            final_output_grace_seconds=0.2,
            inactivity_timeout_seconds=5.0,
        ).run_command(command, on_output=output.append)

        self.assertFalse(result.succeeded)
        self.assertEqual(result.exit_code, -15)
        self.assertIn("after encoder summary", result.runtime_error or "")
        self.assertTrue(any(line.stream == "runtime" for line in output))

    def test_run_command_terminates_after_fatal_output_marker(self) -> None:
        command = PlannedCommand(
            sys.executable,
            (
                "-c",
                "import time; "
                "print('vkQueueSubmit failed -4', flush=True); "
                "time.sleep(5)",
            ),
            "fatal backend output",
        )
        output = []

        result = SubprocessJobRunner(
            fatal_output_detector=lambda line: "fatal backend marker" if "vkQueueSubmit failed" in line.text else None,
            inactivity_timeout_seconds=5.0,
        ).run_command(command, on_output=output.append)

        self.assertFalse(result.succeeded)
        self.assertEqual(result.exit_code, -15)
        self.assertEqual(result.runtime_error, "fatal backend marker")
        self.assertTrue(any(line.stream == "runtime" and line.text == "fatal backend marker" for line in output))

    def test_stage_runtime_error_marks_result_unsuccessful(self) -> None:
        command = PlannedCommand(sys.executable, ("-c", "pass"), "runtime failed")
        result = StageRunResult("runtime failed", command, exit_code=0, runtime_error="backend failed")

        self.assertFalse(result.succeeded)

    def test_run_stage_writes_generated_files_before_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            generated_path = Path(tmp_dir) / "script.vpy"
            command = PlannedCommand(
                sys.executable,
                ("-c", f"from pathlib import Path; print(Path({str(generated_path)!r}).read_text())"),
                "read generated file",
            )
            stage = ProcessingStage(
                "read generated file",
                command,
                generated_files=(GeneratedFile(generated_path, "clip.set_output()\\n", "VapourSynth script"),),
            )
            output = []

            result = SubprocessJobRunner().run_stage(stage, on_output=output.append)

        self.assertTrue(result.succeeded)
        self.assertTrue(any("clip.set_output()" in line for line in result.stdout))
        self.assertEqual(output[0].stream, "generated")
        self.assertIn("VapourSynth script", output[0].text)

    def test_run_stage_uses_stage_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "share" / "video2x"
            work_dir.mkdir(parents=True)
            command = PlannedCommand(
                sys.executable,
                ("-c", "from pathlib import Path; print(Path.cwd())"),
                "print cwd",
            )
            stage = ProcessingStage("print cwd", command, cwd=work_dir)

            result = SubprocessJobRunner().run_stage(stage)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, (str(work_dir),))
        self.assertEqual(result.cwd, work_dir)

    def test_run_stage_merges_stage_environment(self) -> None:
        command = PlannedCommand(
            sys.executable,
            ("-c", "import os; print(os.environ['VIDEOFIXIE_TEST_ENV'])"),
            "print env",
        )
        stage = ProcessingStage("print env", command, env=(("VIDEOFIXIE_TEST_ENV", "enabled"),))

        result = SubprocessJobRunner().run_stage(stage)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, ("enabled",))
