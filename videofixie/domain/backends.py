from __future__ import annotations

from dataclasses import dataclass


VIDEO2X_BACKEND_SLUG = "video2x"
VAPOURSYNTH_BACKEND_SLUG = "vapoursynth"


@dataclass(frozen=True)
class ProcessingBackendDescriptor:
    slug: str
    name: str
    summary: str


def bundled_processing_backends() -> tuple[ProcessingBackendDescriptor, ...]:
    return (
        ProcessingBackendDescriptor(
            slug=VIDEO2X_BACKEND_SLUG,
            name="Video2X",
            summary="Video2X 6.x subprocess backend for RealCUGAN, RealESRGAN, libplacebo and RIFE.",
        ),
        ProcessingBackendDescriptor(
            slug=VAPOURSYNTH_BACKEND_SLUG,
            name="VapourSynth",
            summary="VapourSynth Python/vspipe runtime for future script-based restoration pipelines.",
        ),
    )


def backend_by_slug(slug: str) -> ProcessingBackendDescriptor | None:
    normalized = slug.strip().lower()
    for backend in bundled_processing_backends():
        if backend.slug == normalized:
            return backend
    return None


def normalize_backend_slug(slug: str | None) -> str:
    if slug is None:
        return VIDEO2X_BACKEND_SLUG
    normalized = slug.strip().lower()
    return normalized or VIDEO2X_BACKEND_SLUG
