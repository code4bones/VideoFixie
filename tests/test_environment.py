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

    def test_find_video2x_executable_prefers_project_appimage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            executable = root / "bin" / "Video2X-x86_64.AppImage"
            executable.parent.mkdir()
            executable.write_text("#!/bin/sh\n", encoding="utf-8")

            self.assertEqual(find_video2x_executable(root), str(executable))

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
