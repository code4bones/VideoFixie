import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from videofixie.backends.video2x import required_model_relative_paths
from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG
from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.domain.jobs import TestSegment
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import bundled_output_presets
from videofixie.domain.profiles import bundled_profiles
from videofixie.domain.settings import AppSettings
from videofixie.services.app import VideoFixieService
from videofixie.services.environment import MachineEnvironment, ToolStatus
from videofixie.services.history import VideoFixieHistory
from videofixie.services.settings import VideoFixieSettingsStore


class VideoFixieServiceTest(unittest.TestCase):
    def test_profiles_returns_bundled_profiles(self) -> None:
        self.assertGreaterEqual(len(VideoFixieService().profiles()), 3)

    def test_output_presets_returns_bundled_presets(self) -> None:
        self.assertEqual(VideoFixieService().output_presets(), bundled_output_presets())

    def test_default_release_preset_is_available(self) -> None:
        self.assertEqual(VideoFixieService().default_release_preset().output_preset_slug, "balanced")

    def test_settings_facade_persists_app_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            service = VideoFixieService(settings_store=store)
            settings = AppSettings(models_directory="models-local", default_output_preset_slug="balanced")

            service.save_settings(settings)

            self.assertEqual(service.load_settings(), settings)

    def test_plan_preview_reports_missing_vspipe_for_vapoursynth_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings(active_backend_slug=VAPOURSYNTH_BACKEND_SLUG))
            service = VideoFixieService(settings_store=store)
            environment = MachineEnvironment(
                ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
                ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
                video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
                video2x_capabilities=None,
                preferred_gpu=None,
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

            with self.assertRaisesRegex(RuntimeError, "vspipe is unavailable"):
                service.plan_preview_with_context(
                    "samples/1.mp4",
                    "cache/previews",
                    next(profile for profile in bundled_profiles() if profile.slug == "vapoursynth-lanczos-x2"),
                    TestSegment("Face", 1, 6),
                    media=media,
                    environment=environment,
                )

    def test_plan_preview_uses_vapoursynth_backend_when_vspipe_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings(active_backend_slug=VAPOURSYNTH_BACKEND_SLUG))
            service = VideoFixieService(settings_store=store)
            environment = MachineEnvironment(
                ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
                ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
                video2x=ToolStatus("video2x", None, False, error="Executable not found"),
                video2x_capabilities=None,
                preferred_gpu=None,
                vapoursynth=ToolStatus("vapoursynth", "/venv/bin/python", True, "VapourSynth R79"),
                vspipe=ToolStatus("vspipe", "/venv/bin/vspipe", True, "VSPipe R79"),
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

            plan = service.plan_preview_with_context(
                "samples/1.mp4",
                "cache/previews",
                next(profile for profile in bundled_profiles() if profile.slug == "vapoursynth-lanczos-x2"),
                TestSegment("Face", 1, 6),
                media=media,
                environment=environment,
            )

            self.assertEqual(plan.job.stages[1].command.argv()[0], "/venv/bin/vspipe")
            self.assertEqual(plan.job.stages[2].label, "Encode and mux preview")

    def test_plan_preview_reports_missing_vapoursynth_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings(active_backend_slug=VAPOURSYNTH_BACKEND_SLUG))
            service = VideoFixieService(settings_store=store)
            environment = MachineEnvironment(
                ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
                ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
                video2x=ToolStatus("video2x", None, False, error="Executable not found"),
                video2x_capabilities=None,
                preferred_gpu=None,
                vapoursynth=ToolStatus("vapoursynth", "/venv/bin/python", True, "VapourSynth R79"),
                vspipe=ToolStatus("vspipe", "/venv/bin/vspipe", True, "VSPipe R79"),
                vapoursynth_plugins=("std", "resize"),
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

            with self.assertRaisesRegex(RuntimeError, "Missing VapourSynth plugin dependency"):
                service.plan_preview_with_context(
                    "samples/1.mp4",
                    "cache/previews",
                    next(profile for profile in bundled_profiles() if profile.slug == "vapoursynth-natural-x2"),
                    TestSegment("Face", 1, 6),
                    media=media,
                    environment=environment,
                )

    def test_history_facade_saves_segment_and_preview_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings())
            service = VideoFixieService(history=history, settings_store=store)
            profile = bundled_profiles()[0]
            output_preset = bundled_output_presets()[1]
            segment = TestSegment("Preview", 2.0, 7.0)
            source = Path(tmp_dir) / "clip.mp4"
            output = Path(tmp_dir) / "clip.preview.mp4"
            output.write_bytes(b"preview")

            service.save_source_segment(source, segment, profile.slug, output_preset.slug)
            result = service.record_preview_result(source, output, profile, segment, output_preset)

            self.assertEqual(service.load_source_segment(source), segment)
            saved_cut = service.load_source_cut(source)
            self.assertIsNotNone(saved_cut)
            self.assertEqual(saved_cut.profile_slug, profile.slug)
            self.assertEqual(saved_cut.output_preset_slug, output_preset.slug)
            self.assertEqual(saved_cut.backend_slug, "video2x")
            self.assertEqual(service.saved_cuts_for_source(source), (saved_cut,))
            self.assertEqual(result.output_preset_slug, output_preset.slug)
            self.assertEqual(service.preview_results_for_source(source), (result,))

    @patch("videofixie.services.app.FFmpegAdapter.probe")
    @patch("videofixie.services.app.discover_environment")
    def test_plan_preview_uses_discovered_environment(self, discover_environment, probe) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={
                "realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True),
            },
            devices=(GpuDevice(3, "NVIDIA", "Discrete GPU"),),
        )
        discover_environment.return_value = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "/project/bin/video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )
        probe.return_value = MediaInfo(
            path="samples/1.mp4",
            format_name="mp4",
            duration_seconds=60,
            bit_rate=100,
            size_bytes=1000,
            video_streams=(),
            audio_streams=(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            _create_model_files(Path(tmp_dir), bundled_profiles()[0])
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings())
            plan = VideoFixieService(project_root=tmp_dir, settings_store=store).plan_preview(
                "samples/1.mp4",
                "cache/previews",
                bundled_profiles()[0],
                TestSegment("Face", 1, 6),
            )

        self.assertEqual(plan.segment.duration_seconds, 5)
        self.assertIn("-d", plan.job.stages[1].command.argv())
        self.assertIn("3", plan.job.stages[1].command.argv())

    @patch("videofixie.services.app.FFmpegAdapter.probe")
    @patch("videofixie.services.app.discover_environment")
    def test_plan_preview_with_context_does_not_rediscover_or_reprobe(self, discover_environment, probe) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={
                "realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True),
            },
            devices=(GpuDevice(3, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "/project/bin/video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
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

        with tempfile.TemporaryDirectory() as tmp_dir:
            _create_model_files(Path(tmp_dir), bundled_profiles()[0])
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings())
            plan = VideoFixieService(project_root=tmp_dir, settings_store=store).plan_preview_with_context(
                "samples/1.mp4",
                "cache/previews",
                bundled_profiles()[0],
                TestSegment("Face", 1, 6),
                media=media,
                environment=environment,
            )

        self.assertEqual(plan.media, media)
        self.assertEqual(plan.environment, environment)
        discover_environment.assert_not_called()
        probe.assert_not_called()

    def test_plan_video2x_benchmark_with_context_builds_variant_jobs(self) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={
                "realcugan": ProcessorCapability(
                    "realcugan",
                    ("models-pro", "models-se", "models-nose"),
                    supports_noise_level=True,
                ),
            },
            devices=(GpuDevice(3, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "/project/bin/video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
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
        segment = TestSegment("Face", 1, 6)

        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = Path(tmp_dir) / "share" / "video2x" / "models"
            for profile in (
                _profile("realcugan", "models-pro", 2, None),
                _profile("realcugan", "models-pro", 2, -1),
                _profile("realcugan", "models-pro", 2, 0),
                _profile("realcugan", "models-nose", 2, None),
                _profile("realcugan", "models-nose", 2, 0),
            ):
                _create_model_files_for_profile(models_dir, profile)
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings())
            benchmark = VideoFixieService(project_root=tmp_dir, settings_store=store).plan_video2x_benchmark_with_context(
                "samples/1.mp4",
                "cache/previews",
                segment,
                media=media,
                environment=environment,
            )

        self.assertEqual(benchmark.segment, segment)
        self.assertEqual(len(benchmark.variants), 3)
        self.assertEqual({variant.preview.output_preset.slug for variant in benchmark.variants}, {"preview"})
        self.assertEqual({variant.preview.segment for variant in benchmark.variants}, {segment})
        self.assertTrue(all(variant.preview.job.stages[1].cwd.name == "video2x" for variant in benchmark.variants))


def _create_model_files(root: Path, profile) -> Path:
    models_dir = root / "share" / "video2x" / "models"
    for relative_path in required_model_relative_paths(profile):
        path = models_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model fixture\n", encoding="utf-8")
    return models_dir


def _profile(processor: str, model: str, scale: int, noise_level: int | None):
    from videofixie.domain.profiles import ProcessingProfile

    return ProcessingProfile(
        slug="fixture",
        name="Fixture",
        summary="Fixture",
        processor=processor,
        model=model,
        scale=scale,
        noise_level=noise_level,
    )


def _create_model_files_for_profile(models_dir: Path, profile) -> None:
    for relative_path in required_model_relative_paths(profile):
        path = models_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model fixture\n", encoding="utf-8")
