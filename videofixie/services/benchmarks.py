from __future__ import annotations

from pathlib import Path

from videofixie.backends.video2x import missing_model_files, validate_profile
from videofixie.domain.benchmarks import Video2XBenchmarkVariant
from videofixie.domain.capabilities import BackendCapabilities
from videofixie.domain.profiles import ProcessingProfile


REALCUGAN_LIVE_ACTION_MATRIX: tuple[tuple[str, tuple[int | None, ...]], ...] = (
    ("models-pro", (None, -1, 0, 3)),
    ("models-se", (None, -1, 0, 1, 2)),
    ("models-nose", (None, 0)),
)


def build_video2x_benchmark_variants(
    capabilities: BackendCapabilities | None,
    models_directory: str | Path,
) -> tuple[Video2XBenchmarkVariant, ...]:
    if capabilities is None:
        return ()

    variants: list[Video2XBenchmarkVariant] = []
    for model, noise_levels in REALCUGAN_LIVE_ACTION_MATRIX:
        for noise_level in noise_levels:
            profile = _realcugan_profile(model, noise_level)
            if _profile_is_runnable(profile, capabilities, models_directory):
                variants.append(
                    Video2XBenchmarkVariant(
                        profile=profile,
                        label=f"RealCUGAN {model} {_noise_label(noise_level)}",
                        parameters=f"realcugan / {model} / x2 / {_noise_label(noise_level)}",
                    )
                )

    realesrgan_profile = _realesrgan_plus_profile(scale=4)
    if _profile_is_runnable(realesrgan_profile, capabilities, models_directory):
        variants.append(
            Video2XBenchmarkVariant(
                profile=realesrgan_profile,
                label="RealESRGAN plus x4",
                parameters="realesrgan / realesrgan-plus / x4 / no interpolation",
            )
        )

    return tuple(variants)


def _profile_is_runnable(
    profile: ProcessingProfile,
    capabilities: BackendCapabilities,
    models_directory: str | Path,
) -> bool:
    try:
        validate_profile(capabilities, profile)
        return not missing_model_files(profile, models_directory)
    except (FileNotFoundError, ValueError):
        return False


def _realcugan_profile(model: str, noise_level: int | None) -> ProcessingProfile:
    suffix = _slug_noise(noise_level)
    return ProcessingProfile(
        slug=f"benchmark-realcugan-{model}-x2-{suffix}",
        name=f"Benchmark RealCUGAN {model} {suffix}",
        summary=f"Video2X benchmark variant: RealCUGAN {model}, x2, {_noise_label(noise_level)}.",
        processor="realcugan",
        model=model,
        scale=2,
        noise_level=noise_level,
    )


def _realesrgan_plus_profile(scale: int) -> ProcessingProfile:
    return ProcessingProfile(
        slug=f"benchmark-realesrgan-plus-x{scale}",
        name=f"Benchmark RealESRGAN plus x{scale}",
        summary=f"Video2X benchmark variant: RealESRGAN realesrgan-plus, x{scale}.",
        processor="realesrgan",
        model="realesrgan-plus",
        scale=scale,
        noise_level=None,
        experimental=True,
    )


def _noise_label(noise_level: int | None) -> str:
    if noise_level is None:
        return "default/no denoise"
    if noise_level == -1:
        return "conservative"
    if noise_level == 0:
        return "no denoise"
    return f"denoise {noise_level}"


def _slug_noise(noise_level: int | None) -> str:
    if noise_level is None:
        return "default"
    if noise_level == -1:
        return "conservative"
    return f"noise{noise_level}"
