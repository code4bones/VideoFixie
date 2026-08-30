import tempfile
import unittest
from pathlib import Path

from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.services.benchmarks import build_video2x_benchmark_variants
from videofixie.backends.video2x import required_model_relative_paths


class Video2XBenchmarkMatrixTest(unittest.TestCase):
    def test_matrix_filters_live_action_variants_by_capability_and_model_files(self) -> None:
        capabilities = BackendCapabilities(
            name="Video2X",
            version="6.4.0",
            processors={
                "realcugan": ProcessorCapability(
                    "realcugan",
                    ("models-nose", "models-pro", "models-se"),
                    supports_noise_level=True,
                ),
                "realesrgan": ProcessorCapability("realesrgan", ("realesrgan-plus",)),
            },
            devices=(GpuDevice(0, "NVIDIA", "Discrete GPU"),),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            models_dir = Path(tmp_dir) / "share" / "video2x" / "models"
            for profile in (
                _profile("realcugan", "models-pro", 2, None),
                _profile("realcugan", "models-pro", 2, -1),
                _profile("realcugan", "models-pro", 2, 0),
                _profile("realcugan", "models-se", 2, 1),
                _profile("realcugan", "models-nose", 2, None),
                _profile("realcugan", "models-nose", 2, 0),
                _profile("realesrgan", "realesrgan-plus", 4, None),
            ):
                _create_model_files(models_dir, profile)

            variants = build_video2x_benchmark_variants(capabilities, models_dir)

        slugs = [variant.profile.slug for variant in variants]
        self.assertEqual(
            slugs,
            [
                "benchmark-realcugan-models-pro-x2-default",
                "benchmark-realcugan-models-pro-x2-conservative",
                "benchmark-realcugan-models-pro-x2-noise0",
                "benchmark-realcugan-models-se-x2-noise1",
                "benchmark-realcugan-models-nose-x2-default",
                "benchmark-realcugan-models-nose-x2-noise0",
                "benchmark-realesrgan-plus-x4",
            ],
        )
        self.assertTrue(all("anime" not in slug for slug in slugs))

    def test_matrix_returns_empty_when_video2x_capabilities_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            variants = build_video2x_benchmark_variants(None, Path(tmp_dir))

        self.assertEqual(variants, ())


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


def _create_model_files(models_dir: Path, profile) -> None:
    for relative_path in required_model_relative_paths(profile):
        path = models_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model fixture\n", encoding="utf-8")
