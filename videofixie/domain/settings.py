from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AppSettings:
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    video2x_path: str | None = None
    output_directory: str = "outputs"
    cache_directory: str = "cache"
    models_directory: str = "models"
    preferred_gpu_index: int | None = None
    default_profile_slug: str = "natural-realcugan-x2"
    default_output_preset_slug: str = "preview"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AppSettings:
        defaults = cls()
        values = defaults.to_dict()
        for key in values:
            if key in data:
                values[key] = data[key]
        return cls(
            ffmpeg_path=_optional_text(values["ffmpeg_path"]),
            ffprobe_path=_optional_text(values["ffprobe_path"]),
            video2x_path=_optional_text(values["video2x_path"]),
            output_directory=_required_text(values["output_directory"], defaults.output_directory),
            cache_directory=_required_text(values["cache_directory"], defaults.cache_directory),
            models_directory=_required_text(values["models_directory"], defaults.models_directory),
            preferred_gpu_index=_optional_int(values["preferred_gpu_index"]),
            default_profile_slug=_required_text(values["default_profile_slug"], defaults.default_profile_slug),
            default_output_preset_slug=_required_text(
                values["default_output_preset_slug"],
                defaults.default_output_preset_slug,
            ),
        )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: object, fallback: str) -> str:
    text = _optional_text(value)
    return text if text is not None else fallback


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
