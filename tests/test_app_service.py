import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

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

    def test_plan_preview_rejects_unimplemented_active_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            store.save(AppSettings(active_backend_slug="vapoursynth"))
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

            with self.assertRaisesRegex(RuntimeError, "not implemented yet: vapoursynth"):
                service.plan_preview_with_context(
                    "samples/1.mp4",
                    "cache/previews",
                    bundled_profiles()[0],
                    TestSegment("Face", 1, 6),
                    media=media,
                    environment=environment,
                )

    def test_history_facade_saves_segment_and_preview_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            service = VideoFixieService(history=history)
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
            video2x=ToolStatus("video2x", "bin/Video2X-x86_64.AppImage", True, "6.4.0"),
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

        plan = VideoFixieService().plan_preview(
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
            video2x=ToolStatus("video2x", "bin/Video2X-x86_64.AppImage", True, "6.4.0"),
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

        plan = VideoFixieService().plan_preview_with_context(
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
