import tempfile
import unittest
from pathlib import Path

from videofixie.domain.capabilities import GpuDevice
from videofixie.services.environment import choose_preferred_gpu, find_video2x_executable


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
