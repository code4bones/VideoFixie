import tempfile
import unittest
from pathlib import Path

from videofixie.domain.backends import VIDEO2X_BACKEND_SLUG
from videofixie.domain.settings import AppSettings
from videofixie.services.settings import VideoFixieSettingsStore


class SettingsTest(unittest.TestCase):
    def test_default_settings_use_project_local_directories(self) -> None:
        settings = AppSettings()

        self.assertEqual(settings.active_backend_slug, VIDEO2X_BACKEND_SLUG)
        self.assertEqual(settings.output_directory, "outputs")
        self.assertEqual(settings.cache_directory, "cache")
        self.assertEqual(settings.models_directory, "models")

    def test_settings_store_persists_paths_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            settings = AppSettings(
                active_backend_slug=VIDEO2X_BACKEND_SLUG,
                ffmpeg_path="/opt/ffmpeg",
                ffprobe_path="/opt/ffprobe",
                video2x_path="/opt/video2x",
                vapoursynth_python_path="/opt/vs/bin/python",
                vspipe_path="/opt/vs/bin/vspipe",
                output_directory="rendered",
                cache_directory="scratch",
                models_directory="vf-models",
                preferred_gpu_index=7,
                default_profile_slug="balanced-realcugan-x2",
                default_output_preset_slug="balanced",
            )

            store.save(settings)

            self.assertEqual(store.load(), settings)

    def test_settings_store_preserves_future_backend_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = VideoFixieSettingsStore(Path(tmp_dir) / "settings.sqlite3")
            settings = AppSettings(active_backend_slug="vapoursynth")

            store.save(settings)

            self.assertEqual(store.load().active_backend_slug, "vapoursynth")
