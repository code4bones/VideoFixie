import importlib.util
import os
import sys
import tempfile
import unittest


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class GuiSmokeTest(unittest.TestCase):
    def test_main_window_can_be_constructed_offscreen(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.resize(900, 600)
        app.processEvents()

        self.assertEqual(window.windowTitle(), "VideoFixie")
        self.assertGreater(window.profile_combo.count(), 0)
        self.assertGreaterEqual(window.output_combo.count(), 5)
        self.assertEqual(window.tabs.tabText(3), "Variants")
        self.assertEqual(window.run_variants_button.text(), "Run Variants")
        self.assertEqual(window.variant_parallel_spin.value(), 3)
        self.assertEqual(window.variant_metrics_layout.count(), 4)
        self.assertEqual(window.gpu_metric.title, "GPU load")
        self.assertEqual(window.cpu_metric.title, "CPU load")
        self.assertTrue(window.ram_metric_label.text().startswith("RAM "))
        self.assertFalse(hasattr(window, "env_box"))
        self.assertFalse(hasattr(window, "source_box"))
        self.assertFalse(hasattr(window, "profile_box"))
        self.assertFalse(window.command_text.isVisible())

        window.open_properties()
        app.processEvents()
        self.assertIsNotNone(window.properties_dialog)
        self.assertIn("Open a source video", window.properties_dialog.command_text.toPlainText())
        self.assertTrue(hasattr(window.properties_dialog, "vapoursynth_plugins_label"))

    def test_variant_grid_can_apply_generated_video2x_profile(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.benchmarks import Video2XBenchmarkVariant
        from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG
        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.commands import PlannedCommand
        from videofixie.domain.jobs import ProcessingJob, ProcessingStage, TestSegment
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.output_presets import preview_output_preset
        from videofixie.domain.profiles import ProcessingProfile, bundled_profiles
        from videofixie.domain.settings import AppSettings
        from videofixie.services.app import PlannedBenchmarkVariant, PlannedPreview, PlannedVideo2XBenchmark
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profile = ProcessingProfile(
            slug="benchmark-realcugan-models-pro-x2-noise0",
            name="Benchmark RealCUGAN models-pro noise0",
            summary="Benchmark profile",
            processor="realcugan",
            model="models-pro",
            scale=2,
            noise_level=0,
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
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-pro",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
            vspipe=ToolStatus("vspipe", "/venv/bin/vspipe", True, "VSPipe R79"),
        )
        segment = TestSegment("Preview", 1, 4)
        job = ProcessingJob(
            source_path=Path("samples/1.mp4"),
            output_path=Path("cache/previews/variant.mp4"),
            profile=profile,
            stages=(ProcessingStage("fake", PlannedCommand("python", ("-c", "pass"), "fake")),),
        )
        benchmark = PlannedVideo2XBenchmark(
            media=media,
            environment=environment,
            segment=segment,
            output_preset=preview_output_preset(),
            variants=(
                PlannedBenchmarkVariant(
                    variant=Video2XBenchmarkVariant(profile, "RealCUGAN models-pro noise0", "realcugan / models-pro / x2 / no denoise"),
                    preview=PlannedPreview(media=media, environment=environment, profile=profile, segment=segment, job=job),
                ),
            ),
        )

        class FakeService:
            def __init__(self) -> None:
                self.saved_settings = None

            def profiles(self):
                return bundled_profiles()

            def load_settings(self):
                return AppSettings(active_backend_slug=VAPOURSYNTH_BACKEND_SLUG)

            def save_settings(self, settings):
                self.saved_settings = settings

            def discover_environment(self):
                return environment

            def plan_video2x_benchmark_with_context(self, *args, **kwargs):
                del args, kwargs
                return benchmark

            def plan_preview_with_context(self, *args, **kwargs):
                del args, kwargs
                return PlannedPreview(media=media, environment=environment, profile=profile, segment=segment, job=job)

        service = FakeService()
        window = MainWindow(service=service)
        window.source_path = Path("samples/1.mp4")
        window.media = media
        window.environment = environment
        window.benchmark_plan = benchmark
        window._build_variant_tiles()
        window.apply_benchmark_variant(0)
        app.processEvents()

        self.assertEqual(window.profile_combo.currentData(), profile.slug)
        self.assertEqual(window.settings.active_backend_slug, VIDEO2X_BACKEND_SLUG)
        self.assertEqual(service.saved_settings.active_backend_slug, VIDEO2X_BACKEND_SLUG)
        self.assertFalse(hasattr(window.variant_tiles[0], "player"))
        self.assertFalse(hasattr(window.variant_tiles[0], "video_widget"))

    def test_trigger_buttons_and_timecode_inputs_are_wired(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.resize(900, 600)

        self.assertFalse(hasattr(window, "stop_button"))
        self.assertFalse(hasattr(window, "cancel_preview_button"))
        self.assertEqual(window.play_button.text(), "Play")
        self.assertEqual(window.run_preview_button.text(), "Run Preview")
        self.assertEqual(window.run_action.text(), "Run Preview")

        window.in_spin.setText("1:02.500")
        window.in_spin.editingFinished.emit()
        window.out_spin.setText("1:10.000")
        window.out_spin.editingFinished.emit()
        app.processEvents()

        self.assertEqual(window.in_spin.value(), 62.5)
        self.assertEqual(window.out_spin.value(), 70.0)
        self.assertEqual(window._current_segment().start_seconds, 62.5)
        self.assertEqual(window._current_segment().end_seconds, 70.0)

        window._set_preview_running(True)
        self.assertEqual(window.run_preview_button.text(), "Cancel Preview")
        self.assertEqual(window.run_action.text(), "Cancel Preview")
        window._set_preview_running(False)
        self.assertEqual(window.run_preview_button.text(), "Run Preview")
        self.assertEqual(window.run_action.text(), "Run Preview")

    def test_release_preset_wizard_builds_recommended_summary(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.ui.release_preset_wizard import ReleasePresetWizard

        app = QApplication.instance() or QApplication([])
        wizard = ReleasePresetWizard()
        app.processEvents()

        self.assertIn("Recommended", wizard.goal_page.combo.currentText())
        preset = wizard.release_preset()
        wizard.summary_page.initializePage()

        self.assertEqual(preset.output_preset_slug, "balanced")
        self.assertIn("Technical settings", wizard.summary_page.summary_text.toPlainText())

    def test_replanning_uses_cached_media_and_environment(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import ProcessingJob
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
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

        class FakeService:
            def __init__(self) -> None:
                self.context_plan_count = 0
                self.heavy_plan_count = 0
                self.work_dirs = []

            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def plan_preview(self, *args, **kwargs):
                del args, kwargs
                self.heavy_plan_count += 1
                raise AssertionError("GUI must not use heavy plan_preview for replanning")

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                del device_index, output_preset
                self.context_plan_count += 1
                self.work_dirs.append(work_dir)
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=__import__("pathlib").Path("out.mp4"), profile=profile, stages=()),
                )

        service = FakeService()
        window = MainWindow(service=service)
        window.source_path = __import__("pathlib").Path("samples/1.mp4")
        window.media = media
        window.environment = environment

        window.plan_preview()
        window.plan_preview()
        app.processEvents()

        self.assertEqual(service.context_plan_count, 2)
        self.assertEqual(service.heavy_plan_count, 0)
        self.assertEqual(str(service.work_dirs[-1]), "cache/previews")

    def test_settings_defaults_apply_to_profile_output_and_cache(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG, bundled_processing_backends
        from videofixie.domain.jobs import ProcessingJob
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.domain.settings import AppSettings
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow
        from videofixie.ui.settings_dialog import SettingsDialog

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
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

        class FakeService:
            def __init__(self) -> None:
                self.work_dir = None

            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def load_settings(self):
                return AppSettings(
                    active_backend_slug=VIDEO2X_BACKEND_SLUG,
                    cache_directory="scratch",
                    models_directory="models",
                    default_profile_slug="balanced-realcugan-x2",
                    default_output_preset_slug="balanced",
                )

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                del device_index
                self.work_dir = work_dir
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=Path("out.mp4"), profile=profile, stages=()),
                    output_preset=output_preset,
                )

        service = FakeService()
        window = MainWindow(service=service)
        window.source_path = Path("samples/1.mp4")
        window.media = media
        window.environment = environment
        window.plan_preview()
        app.processEvents()

        self.assertEqual(window.profile_combo.currentData(), "balanced-realcugan-x2")
        self.assertEqual(window.output_combo.currentData(), "balanced")
        self.assertEqual(str(service.work_dir), "scratch/previews")

        dialog = SettingsDialog(
            window.settings,
            window.profiles,
            window.output_presets,
            window.environment,
            processing_backends=bundled_processing_backends(),
        )
        app.processEvents()

        self.assertEqual(dialog.backend_combo.currentData(), VIDEO2X_BACKEND_SLUG)
        self.assertFalse(dialog.video2x_group.isHidden())
        self.assertTrue(dialog.vapoursynth_group.isHidden())

        dialog.backend_combo.setCurrentIndex(dialog.backend_combo.findData(VAPOURSYNTH_BACKEND_SLUG))
        app.processEvents()

        self.assertTrue(dialog.video2x_group.isHidden())
        self.assertFalse(dialog.vapoursynth_group.isHidden())

    def test_vapoursynth_backend_selects_compatible_profile(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.domain.settings import AppSettings
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", None, False, error="Executable not found"),
            video2x_capabilities=None,
            preferred_gpu=None,
            vapoursynth=ToolStatus("vapoursynth", "/venv/bin/python", True, "VapourSynth R79"),
            vspipe=ToolStatus("vspipe", "/venv/bin/vspipe", True, "VSPipe R79"),
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def load_settings(self):
                return AppSettings(active_backend_slug=VAPOURSYNTH_BACKEND_SLUG)

        window = MainWindow(service=FakeService())
        app.processEvents()

        self.assertEqual(window.profile_combo.currentData(), "vapoursynth-natural-x2")

    def test_loading_saved_video2x_cut_with_vapoursynth_backend_normalizes_before_planning(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path
        from unittest.mock import patch

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG
        from videofixie.domain.jobs import ProcessingJob, TestSegment, TestSegmentKind
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.domain.settings import AppSettings
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.services.history import SavedCut
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
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
            path="clip.mp4",
            format_name="mp4",
            duration_seconds=120,
            bit_rate=100,
            size_bytes=1000,
            video_streams=(),
            audio_streams=(),
        )
        saved_cut = SavedCut(
            segment=TestSegment("Saved", 10, 20, TestSegmentKind.CUSTOM),
            profile_slug="natural-realcugan-x2",
            output_preset_slug="preview",
            updated_at="2026-08-30T13:45:00+00:00",
        )

        class FakeService:
            def __init__(self) -> None:
                self.planned_profile_slugs = []

            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def load_settings(self):
                return AppSettings(
                    active_backend_slug=VAPOURSYNTH_BACKEND_SLUG,
                    default_profile_slug="natural-realcugan-x2",
                )

            def analyze_source(self, path):
                del path
                return media

            def load_source_cut(self, path):
                del path
                return saved_cut

            def preview_results_for_source(self, path):
                del path
                return ()

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                del work_dir, device_index, output_preset
                self.planned_profile_slugs.append(profile.slug)
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=Path("out.mp4"), profile=profile, stages=()),
                )

        service = FakeService()
        with patch("videofixie.ui.main_window.QMessageBox.critical") as critical:
            window = MainWindow(service=service)
            window.load_source(Path("/media/clip.mp4"))
            app.processEvents()

        critical.assert_not_called()
        self.assertEqual(window.profile_combo.currentData(), "vapoursynth-natural-x2")
        self.assertIn("vapoursynth-natural-x2", service.planned_profile_slugs)
        self.assertNotIn("natural-realcugan-x2", service.planned_profile_slugs)

    def test_processed_playback_maps_local_time_to_source_segment(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        del app
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

        window = MainWindow(service=FakeService())
        window.timeline.set_duration(60)
        window.processed_segment = TestSegment("Preview", 10.0, 22.5, TestSegmentKind.CUSTOM)

        self.assertEqual(window._processed_milliseconds_for_source_time(5.0), 0)
        self.assertEqual(window._processed_milliseconds_for_source_time(15.0), 5000)
        self.assertEqual(window._processed_milliseconds_for_source_time(30.0), 12500)
        self.assertEqual(window._source_seconds_for_processed_milliseconds(0), 10.0)
        self.assertEqual(window._source_seconds_for_processed_milliseconds(5000), 15.0)
        self.assertEqual(window._source_seconds_for_processed_milliseconds(25000), 22.5)
        window._seek_processed_from_source_time(30.0)
        self.assertEqual(window.timeline_playhead_seconds(), 22.5)

    def test_compare_tabs_zoom_timeline_to_processed_segment(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        del app
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

        window = MainWindow(service=FakeService())
        window.timeline.set_duration(100)
        window.processed_segment = TestSegment("Preview", 20.0, 35.0, TestSegmentKind.CUSTOM)

        window.tabs.setCurrentIndex(1)
        self.assertEqual(window.timeline.display_window(), (20.0, 35.0))
        window.tabs.setCurrentIndex(2)
        self.assertEqual(window.timeline.display_window(), (20.0, 35.0))
        window.tabs.setCurrentIndex(0)
        self.assertEqual(window.timeline.display_window(), (0.0, 100))

    def test_timeline_display_window_uses_full_track_width(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from PySide6.QtWidgets import QApplication

        from videofixie.ui.timeline import SegmentTimeline

        app = QApplication.instance() or QApplication([])
        del app
        timeline = SegmentTimeline()
        timeline.resize(1000, 118)
        timeline.set_duration(100)
        timeline.set_display_window(20, 35, show_segment_handles=False)

        self.assertEqual(timeline.display_window(), (20, 35))
        self.assertAlmostEqual(timeline._x_to_time(timeline._time_to_x(20)), 20, places=3)
        self.assertAlmostEqual(timeline._x_to_time(timeline._time_to_x(35)), 35, places=3)
        self.assertGreater(timeline._time_to_x(35) - timeline._time_to_x(20), 900)

    def test_large_view_can_be_toggled_and_closed(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

        window = MainWindow(service=FakeService())
        window.source_path = Path("samples/1.mp4")
        window._update_large_view_state()
        window.open_large_view()
        app.processEvents()
        self.assertTrue(window.video_widget.isFullScreen())

        toggle_calls = []
        window.toggle_playback = lambda: toggle_calls.append("toggle")
        space_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.video_widget, space_event)
        app.processEvents()
        self.assertEqual(toggle_calls, ["toggle"])

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.video_widget, event)
        app.processEvents()
        self.assertFalse(window.video_widget.isFullScreen())

        window.processed_output_path = Path("samples/1.mp4")
        window.processed_segment = TestSegment("Preview", 10.0, 20.0, TestSegmentKind.CUSTOM)
        window.timeline.set_duration(60)
        window.timeline.set_playhead(14.0, emit=False)
        window.tabs.setCurrentIndex(1)
        app.processEvents()
        self.assertTrue(window.large_view_button.isEnabled())
        self.assertTrue(window.large_view_action.isEnabled())

        window.tabs.setCurrentIndex(2)
        app.processEvents()
        self.assertTrue(window.large_view_button.isEnabled())
        self.assertTrue(window.large_view_action.isEnabled())
        window.open_large_view()
        app.processEvents()
        self.assertIsNotNone(window.large_split_window)
        self.assertEqual(window.large_split_window._last_source_seek_ms, 14_000)
        self.assertEqual(window.large_split_window._last_processed_seek_ms, 4_000)
        self.assertIs(window.split_original_player.videoOutput(), window.split_original_widget)
        self.assertIs(window.split_processed_player.videoOutput(), window.split_processed_widget)
        self.assertFalse(window.large_split_window.isFullScreen())

        split_toggle_calls = []
        window.large_split_window.toggle_playback = lambda: split_toggle_calls.append("toggle")
        split_space_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(window.large_split_window, split_space_event)
        app.processEvents()
        self.assertEqual(split_toggle_calls, ["toggle"])

        window.open_large_view()
        app.processEvents()
        self.assertIsNone(window.large_split_window)
        self.assertIs(window.split_original_player.videoOutput(), window.split_original_widget)
        self.assertIs(window.split_processed_player.videoOutput(), window.split_processed_widget)

    def test_playback_end_restarts_active_view(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

        window = MainWindow(service=FakeService())
        restart_calls = []
        window._restart_active_playback_from_start = lambda: restart_calls.append(window.tabs.currentIndex())

        window.tabs.setCurrentIndex(0)
        window._on_media_status_changed(window.processed_player, QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(restart_calls, [])
        window._on_media_status_changed(window.player, QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(restart_calls, [0])

        window.processed_output_path = Path("samples/1.mp4")
        window.processed_segment = TestSegment("Preview", 10.0, 20.0, TestSegmentKind.CUSTOM)
        window.tabs.setCurrentIndex(2)
        window._active_player_is_playing = lambda: True
        window._on_split_original_position(20_000)
        self.assertEqual(restart_calls[-1], 2)
        app.processEvents()

    def test_load_source_restores_saved_cut_and_results(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.services.history import PreviewResult
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        saved_segment = TestSegment("Saved", 42.0, 55.0, TestSegmentKind.CUSTOM)
        result = PreviewResult(
            id=1,
            source_name="clip.mp4",
            source_path=Path("/media/clip.mp4"),
            output_path=Path("/tmp/clip.preview.mp4"),
            profile_slug=profiles[0].slug,
            profile_name=profiles[0].name,
            segment_label=saved_segment.label,
            segment_kind=saved_segment.kind,
            start_seconds=saved_segment.start_seconds,
            end_seconds=saved_segment.end_seconds,
            created_at="2026-08-30T12:00:00+00:00",
        )
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )
        media = MediaInfo(
            path="clip.mp4",
            format_name="mp4",
            duration_seconds=120,
            bit_rate=100,
            size_bytes=1000,
            video_streams=(),
            audio_streams=(),
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def analyze_source(self, path):
                del path
                return media

            def load_source_segment(self, path):
                del path
                return saved_segment

            def preview_results_for_source(self, path):
                del path
                return (result,)

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                from videofixie.domain.jobs import ProcessingJob
                from videofixie.services.app import PlannedPreview

                del work_dir, device_index, output_preset
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=Path("out.mp4"), profile=profile, stages=()),
                )

        window = MainWindow(service=FakeService())
        window.load_source(Path("/media/clip.mp4"))
        app.processEvents()

        self.assertEqual(window._current_segment(), saved_segment)
        self.assertEqual(window.cut_combo.count(), 1)
        self.assertEqual(window.result_combo.count(), 1)
        self.assertIs(window.result_combo.currentData(), result)

    def test_saved_cut_combo_loads_multiple_ranges(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path
        from unittest.mock import patch

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import ProcessingJob, TestSegment, TestSegmentKind
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.services.history import SavedCut
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        face = SavedCut(
            id=1,
            source_name="clip.mp4",
            source_path=Path("/media/clip.mp4"),
            segment=TestSegment("Face", 10.0, 20.0, TestSegmentKind.FACE),
            profile_slug="natural-realcugan-x2",
            output_preset_slug="preview",
            backend_slug="video2x",
            updated_at="2026-08-30T13:00:00+00:00",
        )
        motion = SavedCut(
            id=2,
            source_name="clip.mp4",
            source_path=Path("/media/clip.mp4"),
            segment=TestSegment("Motion", 30.0, 45.0, TestSegmentKind.MOTION),
            profile_slug="balanced-realcugan-x2",
            output_preset_slug="balanced",
            backend_slug="video2x",
            updated_at="2026-08-30T13:01:00+00:00",
        )
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )
        media = MediaInfo(
            path="clip.mp4",
            format_name="mp4",
            duration_seconds=120,
            bit_rate=100,
            size_bytes=1000,
            video_streams=(),
            audio_streams=(),
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def analyze_source(self, path):
                del path
                return media

            def load_source_cut(self, path):
                del path
                return face

            def saved_cuts_for_source(self, path):
                del path
                return (face, motion)

            def preview_results_for_source(self, path):
                del path
                return ()

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                del work_dir, device_index, output_preset
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=Path("out.mp4"), profile=profile, stages=()),
                )

        window = MainWindow(service=FakeService())
        window.load_source(Path("/media/clip.mp4"))
        app.processEvents()

        self.assertEqual(window.cut_combo.count(), 2)
        self.assertEqual(window._current_segment(), face.segment)

        with patch("videofixie.ui.main_window.QInputDialog.getItem", return_value=(window.cut_combo.itemText(1), True)):
            window.load_selected_cut()
        app.processEvents()

        self.assertEqual(window._current_segment(), motion.segment)
        self.assertEqual(window.profile_combo.currentData(), "balanced-realcugan-x2")
        self.assertEqual(window.output_combo.currentData(), "balanced")

    def test_save_cut_prompts_for_name(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path
        from unittest.mock import patch

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.services.history import SavedCut
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def __init__(self) -> None:
                self.saved_cut: SavedCut | None = None

            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def save_source_segment(self, source_path, segment, profile_slug=None, output_preset_slug=None, backend_slug=None):
                self.saved_cut = SavedCut(
                    id=7,
                    source_name=Path(source_path).name,
                    source_path=Path(source_path),
                    segment=segment,
                    profile_slug=profile_slug,
                    output_preset_slug=output_preset_slug,
                    backend_slug=backend_slug,
                    updated_at="2026-08-30T14:05:00+00:00",
                )
                return self.saved_cut

            def saved_cuts_for_source(self, path):
                del path
                return (self.saved_cut,) if self.saved_cut is not None else ()

            def preview_results_for_source(self, path):
                del path
                return ()

        service = FakeService()
        window = MainWindow(service=service)
        window.source_path = Path("/media/clip.mp4")
        window._set_segment(TestSegment("Preview", 3.0, 9.0, TestSegmentKind.DETAIL))

        with patch("videofixie.ui.main_window.QInputDialog.getText", return_value=("Named Detail", True)):
            window.save_current_cut()
        app.processEvents()

        self.assertIsNotNone(service.saved_cut)
        assert service.saved_cut is not None
        self.assertEqual(service.saved_cut.segment.label, "Named Detail")
        self.assertEqual(window.segment_label.currentText(), "Named Detail")
        self.assertEqual(window.cut_combo.count(), 1)
        self.assertIs(window.cut_combo.currentData(), service.saved_cut)

    def test_opening_different_filename_without_cuts_resets_timeline(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.jobs import ProcessingJob, TestSegment, TestSegmentKind
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.services.history import SavedCut
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        profiles = bundled_profiles()
        saved_cut = SavedCut(
            id=1,
            source_name="clip-a.mp4",
            source_path=Path("/media/clip-a.mp4"),
            segment=TestSegment("Detail", 40.0, 55.0, TestSegmentKind.DETAIL),
            profile_slug="balanced-realcugan-x2",
            output_preset_slug="preview",
            backend_slug="video2x",
            updated_at="2026-08-30T13:10:00+00:00",
        )
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

            def analyze_source(self, path):
                return MediaInfo(
                    path=path,
                    format_name="mp4",
                    duration_seconds=120,
                    bit_rate=100,
                    size_bytes=1000,
                    video_streams=(),
                    audio_streams=(),
                )

            def load_source_cut(self, path):
                return saved_cut if Path(path).name == "clip-a.mp4" else None

            def saved_cuts_for_source(self, path):
                return (saved_cut,) if Path(path).name == "clip-a.mp4" else ()

            def preview_results_for_source(self, path):
                del path
                return ()

            def plan_preview_with_context(
                self,
                source_path,
                work_dir,
                profile,
                segment,
                media,
                environment,
                device_index=None,
                output_preset=None,
            ):
                del work_dir, device_index, output_preset
                return PlannedPreview(
                    media=media,
                    environment=environment,
                    profile=profile,
                    segment=segment,
                    job=ProcessingJob(source_path=source_path, output_path=Path("out.mp4"), profile=profile, stages=()),
                )

        window = MainWindow(service=FakeService())
        window.load_source(Path("/media/clip-a.mp4"))
        app.processEvents()
        self.assertEqual(window._current_segment(), saved_cut.segment)

        window.load_source(Path("/media/clip-b.mp4"))
        app.processEvents()

        self.assertEqual(window._current_segment(), TestSegment("Preview", 0.0, 15.0, TestSegmentKind.CUSTOM))
        self.assertEqual(window.cut_combo.count(), 1)
        self.assertIsNone(window.cut_combo.currentData())

    def test_finished_preview_uses_running_segment_not_latest_replanned_segment(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.commands import PlannedCommand
        from videofixie.domain.jobs import ProcessingJob, ProcessingStage, TestSegment, TestSegmentKind
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.jobs.runner import JobRunResult, StageRunResult
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        del app
        profiles = bundled_profiles()
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )
        environment = MachineEnvironment(
            ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
            ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
            video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
            video2x_capabilities=capabilities,
            preferred_gpu=capabilities.devices[0],
        )

        class FakeService:
            def profiles(self):
                return profiles

            def discover_environment(self):
                return environment

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "preview.mp4"
            output_path.write_bytes(b"preview")
            profile = profiles[0]
            command = PlannedCommand(sys.executable, ("-c", "print('ok')"), "fake preview")
            stage = ProcessingStage("fake preview", command)
            running_segment = TestSegment("Started", 10.0, 20.0, TestSegmentKind.CUSTOM)
            replanned_segment = TestSegment("Later", 30.0, 45.0, TestSegmentKind.CUSTOM)
            window = MainWindow(service=FakeService())
            window.timeline.set_duration(60)
            window.running_preview_job = ProcessingJob(Path("samples/1.mp4"), output_path, profile, (stage,))
            window.running_preview_segment = running_segment
            window.current_plan_segment = replanned_segment

            result = JobRunResult(
                stages=(StageRunResult("fake preview", command, exit_code=0),),
                cancelled=False,
            )
            window._on_preview_finished(result)

            self.assertEqual(window.processed_segment, running_segment)
            self.assertEqual(window.timeline_playhead_seconds(), running_segment.start_seconds)

    def test_run_preview_executes_job_in_worker_thread(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from pathlib import Path

        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication

        from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
        from videofixie.domain.commands import PlannedCommand
        from videofixie.domain.jobs import ProcessingJob, ProcessingStage
        from videofixie.domain.media import MediaInfo
        from videofixie.domain.profiles import bundled_profiles
        from videofixie.services.app import PlannedPreview
        from videofixie.services.environment import MachineEnvironment, ToolStatus
        from videofixie.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "preview.mp4"
            profiles = bundled_profiles()
            capabilities = BackendCapabilities(
                name="Video2X",
                version="6.4.0",
                processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
                devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
            )
            environment = MachineEnvironment(
                ffmpeg=ToolStatus("ffmpeg", "/usr/bin/ffmpeg", True),
                ffprobe=ToolStatus("ffprobe", "/usr/bin/ffprobe", True),
                video2x=ToolStatus("video2x", "video2x", True, "6.4.0"),
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

            class FakeService:
                def profiles(self):
                    return profiles

                def discover_environment(self):
                    return environment

                def plan_preview_with_context(
                    self,
                    source_path,
                    work_dir,
                    profile,
                    segment,
                    media,
                    environment,
                    device_index=None,
                    output_preset=None,
                ):
                    del work_dir, device_index, output_preset
                    command = PlannedCommand(
                        sys.executable,
                        (
                            "-c",
                            f"from pathlib import Path; Path({str(output_path)!r}).write_bytes(b'preview'); print('frame=1/1; fps=1.0')",
                        ),
                        "fake preview",
                    )
                    job = ProcessingJob(
                        source_path=source_path,
                        output_path=output_path,
                        profile=profile,
                        stages=(ProcessingStage("fake preview", command),),
                    )
                    return PlannedPreview(media=media, environment=environment, profile=profile, segment=segment, job=job)

            window = MainWindow(service=FakeService())
            window.source_path = Path("samples/1.mp4")
            window.media = media
            window.environment = environment

            loop = QEventLoop()
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            timeout.start(5000)
            window.run_preview()

            def maybe_quit() -> None:
                if window.preview_thread is None:
                    loop.quit()

            poll = QTimer()
            poll.timeout.connect(maybe_quit)
            poll.start(20)
            loop.exec()
            poll.stop()

            self.assertIsNone(window.preview_thread)
            self.assertTrue(output_path.exists())
            self.assertIn("Preview ready", window.preview_status.text())
