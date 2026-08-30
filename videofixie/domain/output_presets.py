from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputPreset:
    slug: str
    name: str
    summary: str
    codec: str
    crf: int
    encoder_preset: str
    preserve_audio: bool = True
    preserve_subtitles: bool = True
    preserve_metadata: bool = True
    preview_safe: bool = False

    def encoder_options(self) -> tuple[str, ...]:
        return (
            f"crf={self.crf}",
            f"preset={self.encoder_preset}",
        )


def bundled_output_presets() -> tuple[OutputPreset, ...]:
    return (
        OutputPreset(
            slug="preview",
            name="Preview",
            summary="High-fidelity preview/intermediate encode for visual comparison.",
            codec="libx264",
            crf=16,
            encoder_preset="slow",
            preview_safe=True,
        ),
        OutputPreset(
            slug="high-quality",
            name="High Quality",
            summary="High-quality final H.264 output with moderate file size.",
            codec="libx264",
            crf=19,
            encoder_preset="slow",
        ),
        OutputPreset(
            slug="balanced",
            name="Balanced",
            summary="Practical H.264 output for day-to-day restored clips.",
            codec="libx264",
            crf=22,
            encoder_preset="medium",
        ),
        OutputPreset(
            slug="compact",
            name="Compact",
            summary="Smaller HEVC/x265 output when encode time is acceptable.",
            codec="libx265",
            crf=24,
            encoder_preset="medium",
        ),
        OutputPreset(
            slug="archive",
            name="Archive",
            summary="Very high-quality archival H.264 output, larger files expected.",
            codec="libx264",
            crf=17,
            encoder_preset="slow",
        ),
    )


def preview_output_preset() -> OutputPreset:
    return bundled_output_presets()[0]
