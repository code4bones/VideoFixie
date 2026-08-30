import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from videofixie.backends.ffmpeg import FFmpegAdapter
from videofixie.backends.vapoursynth import VapourSynthAdapter
from videofixie.backends.video2x import Video2XAdapter, required_model_relative_paths
from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG
from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.domain.jobs import PreviewRange, TestSegment, TestSegmentKind
from videofixie.domain.output_presets import bundled_output_presets, preview_output_preset
from videofixie.domain.profiles import bundled_profiles
from videofixie.domain.release_presets import default_release_preset
from videofixie.services.planner import build_preview_job, build_release_job, build_test_segment_job


class PlannerTest(unittest.TestCase):
    def test_build_preview_job_creates_inspectable_two_stage_plan(self) -> None:
        profile = bundled_profiles()[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            job = build_preview_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                preview_range=PreviewRange(start_seconds=5, duration_seconds=15),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                models_directory=models_dir,
            )

        self.assertEqual(len(job.stages), 2)
        self.assertEqual(job.stages[0].command.argv()[0], "ffmpeg")
        self.assertIn("-ss", job.stages[0].command.argv())
        self.assertIn("5.000", job.stages[0].command.argv())
        self.assertEqual(job.stages[1].command.argv()[0], "video2x")
        self.assertEqual(job.stages[1].cwd, models_dir.parent)
        self.assertTrue(Path(job.stages[1].command.argv()[2]).is_absolute())
        self.assertTrue(Path(job.stages[1].command.argv()[4]).is_absolute())
        self.assertEqual(job.output_preset, preview_output_preset())
        self.assertTrue(job.output_path.name.endswith(".preview.mp4"))

    def test_build_test_segment_job_uses_segment_label_and_range(self) -> None:
        profile = bundled_profiles()[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Face closeup", 12, 18, TestSegmentKind.FACE),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                models_directory=models_dir,
            )

        self.assertIn("face-closeup", job.output_path.name)
        self.assertIn("12.000", job.stages[0].command.argv())
        self.assertIn("6.000", job.stages[0].command.argv())

    def test_build_test_segment_job_uses_explicit_output_preset_for_ai_encode(self) -> None:
        profile = bundled_profiles()[0]
        compact = next(preset for preset in bundled_output_presets() if preset.slug == "compact")
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                output_preset=compact,
                models_directory=models_dir,
            )

        argv = job.stages[1].command.argv()
        self.assertEqual(job.output_preset, compact)
        self.assertIn("compact", job.output_path.name)
        self.assertIn("libx265", argv)
        self.assertIn("crf=24", argv)

    def test_build_video2x_job_sets_nvidia_vulkan_icd_environment(self) -> None:
        profile = bundled_profiles()[0]
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(
                GpuDevice(0, "NVIDIA GeForce RTX 3060 Laptop GPU", "Discrete GPU"),
                GpuDevice(1, "AMD Radeon Graphics", "Integrated GPU"),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            with patch(
                "videofixie.services.planner._first_existing_path",
                return_value=Path("/usr/share/vulkan/icd.d/nvidia_icd.json"),
            ):
                job = build_test_segment_job(
                    source_path="samples/1.mp4",
                    work_dir=Path(tmp_dir),
                    profile=profile,
                    segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                    device_index=0,
                    ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                    video2x=Video2XAdapter("video2x"),
                    capabilities=capabilities,
                    models_directory=models_dir,
                )

        self.assertEqual(
            job.stages[1].env,
            (("VK_ICD_FILENAMES", "/usr/share/vulkan/icd.d/nvidia_icd.json"),),
        )

    def test_build_video2x_job_does_not_force_icd_for_non_nvidia_gpu(self) -> None:
        profile = bundled_profiles()[0]
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(1, "AMD Radeon Graphics", "Integrated GPU"),),
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            job = build_test_segment_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir),
                profile=profile,
                segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                device_index=1,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                capabilities=capabilities,
                models_directory=models_dir,
            )

        self.assertEqual(job.stages[1].env, ())

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

    def test_build_test_segment_job_rejects_missing_video2x_model_files(self) -> None:
        profile = bundled_profiles()[0]
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = Path(tmp_dir) / "share" / "video2x" / "models"
            with self.assertRaisesRegex(FileNotFoundError, "Video2X model files are missing"):
                build_test_segment_job(
                    source_path="samples/1.mp4",
                    work_dir=Path(tmp_dir),
                    profile=profile,
                    segment=TestSegment("Preview", 0, 5, TestSegmentKind.CUSTOM),
                    device_index=0,
                    ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                    video2x=Video2XAdapter("video2x"),
                    models_directory=models_dir,
                )

    def test_build_release_job_creates_video2x_and_mux_stages(self) -> None:
        profile = bundled_profiles()[0]
        output_preset = next(preset for preset in bundled_output_presets() if preset.slug == "balanced")
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            output_path = Path(tmp_dir) / "outputs" / "clip.release.mp4"
            job = build_release_job(
                source_path="samples/1.mp4",
                work_dir=Path(tmp_dir) / "cache" / "releases",
                output_path=output_path,
                profile=profile,
                release_preset=default_release_preset(),
                device_index=0,
                ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                video2x=Video2XAdapter("video2x"),
                output_preset=output_preset,
                models_directory=models_dir,
            )

        self.assertEqual(job.output_path, output_path)
        self.assertEqual(len(job.stages), 2)
        self.assertEqual(job.stages[0].command.argv()[0], "video2x")
        self.assertIn("--no-copy-streams", job.stages[0].command.argv())
        self.assertEqual(job.stages[0].cwd, models_dir.parent)
        self.assertEqual(job.stages[1].label, "Mux release streams")
        self.assertIn("-c:v", job.stages[1].command.argv())
        self.assertIn("copy", job.stages[1].command.argv())

    def test_build_release_job_rejects_unimplemented_resolution_policy(self) -> None:
        profile = bundled_profiles()[0]
        release_preset = replace(default_release_preset(), resolution_policy="fit-1080p")
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = _create_model_files(Path(tmp_dir), profile)
            with self.assertRaisesRegex(ValueError, "not implemented"):
                build_release_job(
                    source_path="samples/1.mp4",
                    work_dir=Path(tmp_dir) / "cache" / "releases",
                    output_path=Path(tmp_dir) / "outputs" / "clip.release.mp4",
                    profile=profile,
                    release_preset=release_preset,
                    device_index=0,
                    ffmpeg=FFmpegAdapter(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe"),
                    video2x=Video2XAdapter("video2x"),
                    models_directory=models_dir,
                )


def _create_model_files(root: Path, profile) -> Path:
    models_dir = root / "share" / "video2x" / "models"
    for relative_path in required_model_relative_paths(profile):
        path = models_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model fixture\n", encoding="utf-8")
    return models_dir
