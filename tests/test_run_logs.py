import sys
import tempfile
import unittest
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import ProcessingStage
from videofixie.jobs.runner import SubprocessJobRunner
from videofixie.services.run_logs import RunLogFile, create_run_directory


class RunLogTest(unittest.TestCase):
    def test_run_log_file_records_stage_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = create_run_directory(tmp_dir, "preview")
            log = RunLogFile.create(run_dir, "preview", "Preview run", {"source": "clip.mp4"})
            command = PlannedCommand(sys.executable, ("-c", "print('ok')"), "fake command")
            stage = ProcessingStage("fake stage", command)

            log.append_stage_start(stage)
            log.append_process_line("stdout", "live ok")
            result = SubprocessJobRunner().run_stage(stage)
            log.append_stage_result(stage, result)
            log.append_status("succeeded")

            text = Path(log.path).read_text(encoding="utf-8")

        self.assertIn("Preview run", text)
        self.assertIn("source: clip.mp4", text)
        self.assertIn("label: fake stage", text)
        self.assertIn("status: running", text)
        self.assertIn("stdout: live ok", text)
        self.assertIn("exit_code: 0", text)
        self.assertIn(command.display(), text)
        self.assertIn("  ok", text)
        self.assertIn("status: succeeded", text)
