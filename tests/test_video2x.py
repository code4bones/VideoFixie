import dataclasses
import tempfile
import unittest
from pathlib import Path

from videofixie.backends.video2x import (
    parse_capabilities,
    parse_devices,
    parse_progress_line,
    parse_version,
    required_model_relative_paths,
    validate_model_files,
    validate_profile,
)
from videofixie.domain.output_presets import preview_output_preset
from videofixie.domain.profiles import bundled_profiles


HELP_TEXT = """
  -p [ --processor ] arg                Processor to use (libplacebo,
                                        realesrgan, realcugan, rife)
  --realesrgan-model arg (=realesr-animevideov3)
                                        Name of the RealESRGAN model to use
                                        (realesr-animevideov3,
                                        realesrgan-plus-anime, realesrgan-plus)
  --realcugan-model arg (=models-se)    Name of the RealCUGAN model to use
                                        (models-nose, models-pro, models-se)
  --rife-model arg (=rife-v4.6)         Name of the RIFE model to use (rife,
                                        rife-HD, rife-UHD)
"""

DEVICES_TEXT = """
0. NVIDIA GeForce RTX 3060 Laptop GPU
    Type: Discrete GPU
    Vulkan API Version: 1.4.329
    Driver Version: 595.336.0
    Device ID: 0x2560
1. AMD Radeon Graphics (RADV RENOIR)
    Type: Integrated GPU
"""


class Video2XTest(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("Video2X version 6.4.0\n"), "6.4.0")


    def test_parse_devices(self) -> None:
        devices = parse_devices(DEVICES_TEXT)

        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].index, 0)
        self.assertEqual(devices[0].name, "NVIDIA GeForce RTX 3060 Laptop GPU")
        self.assertEqual(devices[0].type, "Discrete GPU")
        self.assertEqual(devices[0].vulkan_api_version, "1.4.329")


    def test_parse_capabilities_from_help_text(self) -> None:
        capabilities = parse_capabilities(HELP_TEXT, "Video2X version 6.4.0", DEVICES_TEXT)

        self.assertEqual(capabilities.version, "6.4.0")
        self.assertEqual(set(capabilities.processors), {"libplacebo", "realesrgan", "realcugan", "rife"})
        self.assertIn("models-se", capabilities.processors["realcugan"].models)
        self.assertTrue(capabilities.processors["realcugan"].supports_noise_level)
        self.assertTrue(capabilities.devices[0].name.startswith("NVIDIA"))


    def test_parse_progress_line(self) -> None:
        progress = parse_progress_line("frame=80/442; fps=2.7; elapsed=00:00:29; remaining=00:02:10")

        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.current_frame, 80)
        self.assertEqual(progress.total_frames, 442)
        self.assertEqual(round(progress.percent or 0, 1), 18.1)
        self.assertEqual(progress.fps, 2.7)
        self.assertEqual(progress.remaining, "00:02:10")


    def test_realcugan_profile_command_is_inspectable(self) -> None:
        from videofixie.backends.video2x import Video2XAdapter

        profile = bundled_profiles()[0]
        capabilities = parse_capabilities(HELP_TEXT, "Video2X version 6.4.0", DEVICES_TEXT)
        command = Video2XAdapter("./bin/video2x").build_upscale_command(
            "in.mp4",
            "out.mp4",
            profile,
            preview_output_preset(),
            device_index=0,
            capabilities=capabilities,
        )

        self.assertEqual(command.argv()[:6], ["./bin/video2x", "-i", "in.mp4", "-o", "out.mp4", "-p"])
        self.assertIn("--realcugan-model", command.argv())
        self.assertIn("models-se", command.argv())
        self.assertTrue(command.display().startswith("./bin/video2x"))

    def test_required_model_paths_include_realcugan_noise_variant(self) -> None:
        profile = next(profile for profile in bundled_profiles() if profile.slug == "balanced-realcugan-x2")

        self.assertEqual(
            required_model_relative_paths(profile),
            (
                Path("realcugan/models-se/up2x-denoise1x.param"),
                Path("realcugan/models-se/up2x-denoise1x.bin"),
            ),
        )

    def test_validate_model_files_rejects_missing_realcugan_variant(self) -> None:
        profile = dataclasses.replace(bundled_profiles()[0], model="models-pro", noise_level=1)
        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = Path(tmp_dir) / "share" / "video2x" / "models"
            available = models_dir / "realcugan" / "models-pro" / "up2x-denoise3x.param"
            available.parent.mkdir(parents=True)
            available.write_text("fixture\n", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "up2x-denoise1x.param"):
                validate_model_files(profile, models_dir)

    def test_validate_profile_rejects_missing_model(self) -> None:
        capabilities = parse_capabilities(HELP_TEXT, "Video2X version 6.4.0", DEVICES_TEXT)
        profile = dataclasses.replace(bundled_profiles()[0], model="missing-model")

        with self.assertRaisesRegex(ValueError, "missing-model"):
            validate_profile(capabilities, profile)
