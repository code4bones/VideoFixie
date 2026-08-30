from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingProfile:
    slug: str
    name: str
    summary: str
    processor: str
    model: str
    scale: int | None
    noise_level: int | None
    experimental: bool = False


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
            model="models-pro",
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
    )
