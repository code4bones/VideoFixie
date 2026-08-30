from __future__ import annotations

from pathlib import Path

from videofixie.backends.vapoursynth import validate_pipeline_dependencies
from videofixie.backends.video2x import missing_model_files, validate_profile
from videofixie.domain.benchmarks import Video2XBenchmarkVariant
from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG
from videofixie.domain.capabilities import BackendCapabilities
from videofixie.domain.profiles import ProcessingProfile, bundled_profiles


REALCUGAN_LIVE_ACTION_MATRIX: tuple[tuple[str, tuple[int | None, ...]], ...] = (
    ("models-pro", (None, 0, 3)),
    ("models-se", (None, 0, 1)),
)
VAPOURSYNTH_QUALITY_VARIANT_SLUGS = (
    "vapoursynth-natural-x2",
    "vapoursynth-lanczos-x2",
    "vapoursynth-bicubic-x2",
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
                        backend_slug=VIDEO2X_BACKEND_SLUG,
                    )
                )

    realesrgan_profile = _realesrgan_plus_profile(scale=4)
    if _profile_is_runnable(realesrgan_profile, capabilities, models_directory):
        variants.append(
            Video2XBenchmarkVariant(
                profile=realesrgan_profile,
                label="RealESRGAN plus x4",
                parameters="realesrgan / realesrgan-plus / x4 / no interpolation",
                backend_slug=VIDEO2X_BACKEND_SLUG,
            )
        )

    return tuple(variants)


def build_vapoursynth_benchmark_variants(
    available_plugins: tuple[str, ...],
    profiles: tuple[ProcessingProfile, ...] | None = None,
) -> tuple[Video2XBenchmarkVariant, ...]:
    if not available_plugins:
        return ()

    variants: list[Video2XBenchmarkVariant] = []
    profiles_by_slug = {profile.slug: profile for profile in (profiles or bundled_profiles())}
    for slug in VAPOURSYNTH_QUALITY_VARIANT_SLUGS:
        profile = profiles_by_slug.get(slug)
        if profile is None:
            continue
        if not profile.supports_backend(VAPOURSYNTH_BACKEND_SLUG):
            continue
        try:
            validate_pipeline_dependencies(profile, available_plugins)
        except RuntimeError:
            continue
        variants.append(
            Video2XBenchmarkVariant(
                profile=profile,
                label=_vapoursynth_label(profile),
                parameters=_vapoursynth_parameters(profile),
                backend_slug=VAPOURSYNTH_BACKEND_SLUG,
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
    if noise_level == 0:
        return "no denoise"
    return f"denoise {noise_level}"


def _slug_noise(noise_level: int | None) -> str:
    if noise_level is None:
        return "default"
    return f"noise{noise_level}"


def _vapoursynth_label(profile: ProcessingProfile) -> str:
    if profile.model == "restoration-natural-v1":
        return "VapourSynth Natural"
    if profile.model == "builtin-lanczos":
        return "VapourSynth Lanczos baseline"
    if profile.model == "builtin-bicubic":
        return "VapourSynth Bicubic baseline"
    return profile.name


def _vapoursynth_parameters(profile: ProcessingProfile) -> str:
    scale = f"x{profile.scale}" if profile.scale is not None else "native scale"
    if profile.model.startswith("builtin-"):
        return f"vapoursynth / {profile.model} / {scale} / no AI"
    return f"vapoursynth / {profile.model} / {scale} / cleanup + temporal denoise + texture retention"
