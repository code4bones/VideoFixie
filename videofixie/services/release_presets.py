from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from videofixie.domain.media import MediaInfo
from videofixie.domain.release_presets import ReleasePreset
from videofixie.domain.profiles import ProcessingProfile


@dataclass(frozen=True)
class ReleaseChoice:
    slug: str
    label: str
    explanation: str
    recommended: bool = False

    @property
    def display_label(self) -> str:
        return f"{self.label} (Recommended)" if self.recommended else self.label


def release_goal_choices(media: MediaInfo | None = None) -> tuple[ReleaseChoice, ...]:
    recommended = "balanced"
    if media and media.primary_video and media.primary_video.width <= 720:
        recommended = "high-quality"
    return (
        ReleaseChoice("balanced", "Balanced", "Good default for restored clips: practical size, compatibility and encode speed.", recommended == "balanced"),
        ReleaseChoice("high-quality", "High Quality", "Keeps more restored detail, at the cost of larger files.", recommended == "high-quality"),
        ReleaseChoice("compact", "Compact", "Prioritizes smaller files, usually with slower HEVC encoding and narrower compatibility.", False),
        ReleaseChoice("archive", "Archive", "Keeps a high-quality master for future work; expect large files.", False),
        ReleaseChoice("custom", "Custom", "Start from a preset but review every technical choice manually.", False),
    )


def resolution_policy_choices(media: MediaInfo | None = None) -> tuple[ReleaseChoice, ...]:
    del media
    return (
        ReleaseChoice(
            "preserve-restored-size",
            "Preserve restored size",
            "Uses the processed output dimensions exactly, avoiding another resize pass.",
            True,
        ),
        ReleaseChoice(
            "fit-1080p",
            "Fit within 1080p",
            "Caps large output for broad playback compatibility, sacrificing some restored pixels.",
        ),
        ReleaseChoice(
            "source-multiple",
            "Keep source multiple",
            "Keeps an integer upscale relationship to the source when possible.",
        ),
    )


def container_choices() -> tuple[ReleaseChoice, ...]:
    return (
        ReleaseChoice("mp4", "MP4", "Best compatibility for H.264/H.265 video and common audio tracks.", True),
        ReleaseChoice("mkv", "MKV", "More flexible for subtitles, multiple audio tracks and archival stream preservation."),
    )


def stream_policy_choices(kind: str) -> tuple[ReleaseChoice, ...]:
    if kind == "audio":
        return (
            ReleaseChoice("copy", "Copy original audio", "Fast and lossless when the original audio is compatible.", True),
            ReleaseChoice("aac", "Re-encode to AAC", "Improves MP4 compatibility but changes the original audio."),
        )
    if kind == "subtitles":
        return (
            ReleaseChoice("copy-compatible", "Copy compatible subtitles", "Preserves subtitles when the selected container supports them.", True),
            ReleaseChoice("drop", "Drop subtitles", "Avoids compatibility issues but removes subtitle streams."),
        )
    return (
        ReleaseChoice("copy", "Copy metadata", "Keeps source metadata in the release file where practical.", True),
        ReleaseChoice("minimal", "Minimal metadata", "Writes only essential metadata for cleaner distribution files."),
    )


def output_preset_for_goal(goal_slug: str) -> str:
    return {
        "high-quality": "high-quality",
        "compact": "compact",
        "archive": "archive",
    }.get(goal_slug, "balanced")


def build_release_preset(
    *,
    goal_slug: str,
    resolution_policy: str,
    container: str,
    audio_policy: str,
    subtitle_policy: str,
    metadata_policy: str,
    destination_directory: str,
    naming_template: str,
) -> ReleasePreset:
    output_slug = output_preset_for_goal(goal_slug)
    return ReleasePreset(
        slug=f"{goal_slug}-release",
        name=f"{goal_slug.replace('-', ' ').title()} Release",
        release_goal_slug=goal_slug,
        output_preset_slug=output_slug,
        container=container,
        resolution_policy=resolution_policy,
        audio_policy=audio_policy,
        subtitle_policy=subtitle_policy,
        metadata_policy=metadata_policy,
        destination_directory=destination_directory,
        naming_template=naming_template,
    )


def release_output_path(
    source_path: str | Path,
    project_root: str | Path,
    profile: ProcessingProfile,
    release_preset: ReleasePreset,
) -> Path:
    source = Path(source_path)
    root = Path(project_root)
    destination = Path(release_preset.destination_directory).expanduser()
    if not destination.is_absolute():
        destination = root / destination

    tokens = {
        "source_stem": _filename_token(source.stem),
        "profile": _filename_token(profile.slug),
        "release_goal": _filename_token(release_preset.release_goal_slug),
        "output_preset": _filename_token(release_preset.output_preset_slug),
        "container": _filename_token(release_preset.container),
    }
    try:
        filename = release_preset.naming_template.format(**tokens)
    except KeyError as exc:
        raise ValueError(f"Unknown release naming token: {exc.args[0]}") from exc

    filename = _filename_token(filename)
    suffix = f".{release_preset.container}"
    if not filename.endswith(suffix):
        filename = f"{filename}{suffix}"
    return _non_destructive_path(destination / filename)


def _non_destructive_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 1000):
        candidate = parent / f"{stem}-{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"No non-destructive release filename is available near {path}")


def _filename_token(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return safe or "release"
