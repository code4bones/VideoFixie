import unittest
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import ProcessingJob, ProcessingStage
from videofixie.domain.profiles import ProcessingProfile
from videofixie.jobs.output_validation import (
    MEDIA_VALIDATION_LABEL,
    apply_media_validation_error,
    build_media_validation_stage,
    media_validation_ffmpeg_path,
    missing_media_validation_result,
)
from videofixie.jobs.runner import StageRunResult


class OutputValidationTest(unittest.TestCase):
    def test_build_media_validation_stage_decodes_video_and_optional_audio(self) -> None:
        stage = build_media_validation_stage("out.mp4", ffmpeg_path="/opt/ffmpeg", max_seconds=20)

        self.assertEqual(stage.label, MEDIA_VALIDATION_LABEL)
        self.assertEqual(stage.command.program, "/opt/ffmpeg")
        self.assertEqual(stage.command.args, (
            "-v",
            "error",
            "-xerror",
            "-i",
            "out.mp4",
            "-t",
            "20.000",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-f",
            "null",
            "-",
        ))

    def test_media_validation_ffmpeg_path_prefers_job_ffmpeg(self) -> None:
        profile = ProcessingProfile("fixture", "Fixture", "Fixture", "realcugan", "models-se", 2, None)
        job = ProcessingJob(
            source_path=Path("in.mp4"),
            output_path=Path("out.mp4"),
            profile=profile,
            stages=(
                ProcessingStage("probe", PlannedCommand("/usr/bin/ffprobe", ("--fake",), "probe")),
                ProcessingStage("mux", PlannedCommand("/custom/ffmpeg", ("--fake",), "mux")),
            ),
        )

        self.assertEqual(media_validation_ffmpeg_path(job), "/custom/ffmpeg")

    def test_failed_validation_gets_human_runtime_error(self) -> None:
        stage = build_media_validation_stage("bad.mp4")
        result = StageRunResult(
            stage.label,
            stage.command,
            exit_code=1,
            stderr=("Invalid NAL unit size", "Prediction is not allowed in AAC-LC"),
        )

        result = apply_media_validation_error(stage, result, "bad.mp4")

        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.runtime_error)
        assert result.runtime_error is not None
        self.assertIn("Output media validation failed for bad.mp4", result.runtime_error)
        self.assertIn("Invalid NAL unit size", result.runtime_error)

    def test_missing_output_is_failed_validation_result(self) -> None:
        stage = build_media_validation_stage("missing.mp4")

        result = missing_media_validation_result(stage, "missing.mp4")

        self.assertFalse(result.succeeded)
        self.assertEqual(result.exit_code, -1)
        self.assertIn("Output file was not created", result.runtime_error or "")
