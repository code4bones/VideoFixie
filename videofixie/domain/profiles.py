from __future__ import annotations

from dataclasses import dataclass

from videofixie.domain.backends import VAPOURSYNTH_BACKEND_SLUG, VIDEO2X_BACKEND_SLUG


@dataclass(frozen=True)
class ProcessingProfile:
    slug: str
    name: str
    summary: str
    processor: str
    model: str
    scale: int | None
    noise_level: int | None
    compatible_backend_slugs: tuple[str, ...] = (VIDEO2X_BACKEND_SLUG,)
    experimental: bool = False

    def supports_backend(self, backend_slug: str) -> bool:
        return backend_slug in self.compatible_backend_slugs


def bundled_profiles() -> tuple[ProcessingProfile, ...]:
    return (
        ProcessingProfile(
            slug="natural-realcugan-x2",
            name="Natural",
            summary="RealCUGAN x2 with conservative cleanup and texture retention.",
            processor="realcugan",
            model="models-se",
            scale=2,
            noise_level=None,
        ),
        ProcessingProfile(
            slug="balanced-realcugan-x2",
            name="Balanced",
            summary="RealCUGAN x2 with mild noise processing.",
            processor="realcugan",
            model="models-se",
            scale=2,
            noise_level=1,
        ),
        ProcessingProfile(
            slug="experimental-realesrgan-x4",
            name="Experimental RealESRGAN",
            summary="RealESRGAN x4 for comparison only until stability is verified on the selected device.",
            processor="realesrgan",
            model="realesrgan-plus",
            scale=4,
            noise_level=None,
            experimental=True,
        ),
        ProcessingProfile(
            slug="vapoursynth-lanczos-x2",
            name="VapourSynth Lanczos",
            summary="BestSource decode with built-in Lanczos x2 resize. No AI model or denoise is applied.",
            processor="vapoursynth-resize",
            model="builtin-lanczos",
            scale=2,
            noise_level=None,
            compatible_backend_slugs=(VAPOURSYNTH_BACKEND_SLUG,),
        ),
        ProcessingProfile(
            slug="vapoursynth-bicubic-x2",
            name="VapourSynth Bicubic",
            summary="BestSource decode with built-in Bicubic x2 resize for a softer baseline comparison.",
            processor="vapoursynth-resize",
            model="builtin-bicubic",
            scale=2,
            noise_level=None,
            compatible_backend_slugs=(VAPOURSYNTH_BACKEND_SLUG,),
        ),
    )
