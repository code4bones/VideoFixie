import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.services.environment import choose_preferred_gpu, discover_environment, find_video2x_executable


class EnvironmentTest(unittest.TestCase):
    def test_choose_preferred_gpu_prefers_nvidia_without_hardcoded_index(self) -> None:
        devices = (
            GpuDevice(index=4, name="llvmpipe (LLVM 21.1.8, 256 bits)", type="CPU"),
            GpuDevice(index=7, name="NVIDIA GeForce RTX 3060 Laptop GPU", type="Discrete GPU"),
        )

        preferred = choose_preferred_gpu(devices)

        self.assertIsNotNone(preferred)
        assert preferred is not None
        self.assertEqual(preferred.index, 7)

    def test_find_video2x_executable_prefers_project_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bin_dir = root / "bin"
            executable = bin_dir / "video2x"
            appimage = bin_dir / "Video2X-x86_64.AppImage"
            bin_dir.mkdir()
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            appimage.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(find_video2x_executable(root), str(executable))

    def test_find_video2x_executable_does_not_auto_detect_appimage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            appimage = root / "bin" / "Video2X-x86_64.AppImage"
            appimage.parent.mkdir()
            appimage.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch("videofixie.services.environment.which", return_value=None):
                self.assertIsNone(find_video2x_executable(root))

    def test_discover_environment_honors_configured_paths_and_gpu(self) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={"realcugan": ProcessorCapability("realcugan", ("models-se",), supports_noise_level=True)},
            devices=(
                GpuDevice(index=3, name="AMD Radeon Graphics", type="Integrated GPU"),
                GpuDevice(index=7, name="NVIDIA GeForce RTX 3060 Laptop GPU", type="Discrete GPU"),
            ),
        )

        class Completed:
            stdout = "tool version\n"

        with (
            patch("videofixie.services.environment.subprocess.run", return_value=Completed()),
            patch("videofixie.services.environment.Video2XAdapter.version", return_value="6.4.0"),
            patch("videofixie.services.environment.Video2XAdapter.capabilities", return_value=capabilities),
        ):
            env = discover_environment(
                ".",
                ffmpeg_path="/custom/ffmpeg",
                ffprobe_path="/custom/ffprobe",
                video2x_path="/custom/video2x",
                preferred_gpu_index=7,
            )

        self.assertEqual(env.ffmpeg.path, "/custom/ffmpeg")
        self.assertEqual(env.ffprobe.path, "/custom/ffprobe")
        self.assertEqual(env.video2x.path, "/custom/video2x")
        self.assertIsNotNone(env.preferred_gpu)
        assert env.preferred_gpu is not None
        self.assertEqual(env.preferred_gpu.index, 7)

    def test_discover_environment_reports_vapoursynth_runtime(self) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={},
            devices=(),
        )

        class Completed:
            stdout = "vspipe R79\n"

        with (
            patch("videofixie.services.environment.subprocess.run", return_value=Completed()),
            patch("videofixie.services.environment.Video2XAdapter.version", return_value="6.4.0"),
            patch("videofixie.services.environment.Video2XAdapter.capabilities", return_value=capabilities),
            patch("videofixie.services.environment.VapourSynthAdapter.version", return_value="VapourSynth R79"),
        ):
            env = discover_environment(
                ".",
                video2x_path="/custom/video2x",
                vapoursynth_python_path="/custom/python",
                vspipe_path="/custom/vspipe",
            )

        self.assertEqual(env.vapoursynth.path, "/custom/python")
        self.assertTrue(env.vapoursynth.available)
        self.assertEqual(env.vapoursynth.version, "VapourSynth R79")
        self.assertEqual(env.vspipe.path, "/custom/vspipe")
        self.assertTrue(env.vspipe.available)
        self.assertEqual(env.vspipe.version, "vspipe R79")

    def test_discover_environment_finds_vspipe_next_to_configured_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            python = root / "bin" / "python"
            vspipe = root / "bin" / "vspipe"
            vspipe.parent.mkdir()
            python.write_text("#!/bin/sh\n", encoding="utf-8")
            vspipe.write_text("#!/bin/sh\n", encoding="utf-8")

            class Completed:
                stdout = "vspipe R79\n"

            with (
                patch("videofixie.services.environment.which", return_value=None),
                patch("videofixie.services.environment.subprocess.run", return_value=Completed()),
                patch("videofixie.services.environment.VapourSynthAdapter.version", return_value="VapourSynth R79"),
            ):
                env = discover_environment(
                    ".",
                    video2x_path=None,
                    vapoursynth_python_path=python,
                )

        self.assertEqual(env.vspipe.path, str(vspipe))
        self.assertTrue(env.vspipe.available)
