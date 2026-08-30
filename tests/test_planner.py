import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from videofixie.backends.ffmpeg import FFmpegAdapter
from videofixie.backends.vapoursynth import VapourSynthAdapter
from videofixie.backends.video2x import Video2XAdapter
from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG
from videofixie.domain.jobs import PreviewRange, TestSegment, TestSegmentKind
from videofixie.domain.output_presets import bundled_output_presets, preview_output_preset
from videofixie.domain.profiles import bundled_profiles
from videofixie.services.planner import build_preview_job, build_test_segment_job


class PlannerTest(unittest.TestCase):
    def test_build_preview_job_creates_inspectable_two_stage_plan(self) -> None:
        profile = bundled_profiles()[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = build_preview_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                preview_range=PreviewRange(start_seconds=5, duration_seconds=15),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
            )

        self.assertEqual(len(job.stages), 2)
        self.assertEqual(job.stages[0].command.argv()[0], "ffmpeg")
        self.assertIn("-ss", job.stages[0].command.argv())
        self.assertIn("5.000", job.stages[0].command.argv())
        self.assertEqual(job.stages[1].command.argv()[0], "video2x")
        self.assertEqual(job.output_preset, preview_output_preset())
        self.assertTrue(job.output_path.name.endswith(".preview.mp4"))

    def test_build_test_segment_job_uses_segment_label_and_range(self) -> None:
        profile = bundled_profiles()[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Face closeup", 12, 18, TestSegmentKind.FACE),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
            )

        self.assertIn("face-closeup", job.output_path.name)
        self.assertIn("12.000", job.stages[0].command.argv())
        self.assertIn("6.000", job.stages[0].command.argv())

    def test_build_test_segment_job_uses_explicit_output_preset_for_ai_encode(self) -> None:
        profile = bundled_profiles()[0]
        compact = next(preset for preset in bundled_output_presets() if preset.slug == "compact")
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                output_preset=compact,
            )

        argv = job.stages[1].command.argv()
        self.assertEqual(job.output_preset, compact)
        self.assertIn("compact", job.output_path.name)
        self.assertIn("libx265", argv)
        self.assertIn("crf=24", argv)

    def test_build_test_segment_job_rejects_incompatible_backend_profile(self) -> None:
        profile = replace(bundled_profiles()[0], compatible_backend_slugs=(VAPOURSYNTH_BACKEND_SLUG,))
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(ValueError, "not compatible with backend video2x"):
                build_test_segment_job(
                    source_path="samples/1.mp4",
                    work_dir=Path(tmp_dir),
                    profile=profile,
                    segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                    device_index=0,
                    ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                    video2x=Video2XAdapter("video2x"),
                    backend_slug=VIDEO2X_BACKEND_SLUG,
                )

    def test_build_vapoursynth_preview_job_creates_script_render_and_mux_stages(self) -> None:
        profile = next(profile for profile in bundled_profiles() if profile.slug == "vapoursynth-lanczos-x2")
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Detail", 4, 7, TestSegmentKind.DETAIL),
                device_index=None,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=None,
                vapoursynth=VapourSynthAdapter("/venv/bin/python", "/venv/bin/vspipe"),
                backend_slug=VAPOURSYNTH_BACKEND_SLUG,
            )

        self.assertEqual(len(job.stages), 3)
        self.assertEqual(job.stages[0].label, "Create preview source")
        self.assertEqual(job.stages[1].command.argv()[0], "/venv/bin/vspipe")
        self.assertEqual(job.stages[1].generated_files[0].path.suffix, ".vpy")
        self.assertIn("core.bs.VideoSource", job.stages[1].generated_files[0].content)
        self.assertEqual(job.stages[2].label, "Encode and mux preview")
        self.assertIn("-map_metadata", job.stages[2].command.argv())
