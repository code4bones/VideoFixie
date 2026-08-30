import sys
import threading
import time
import unittest
import tempfile
from pathlib import Path

from videofixie.backends.video2x import parse_progress_line
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import GeneratedFile, ProcessingStage
from videofixie.jobs.runner import CancellationToken, SubprocessJobRunner


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
