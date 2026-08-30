from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReleasePreset:
    slug: str
    name: str
    release_goal_slug: str
    output_preset_slug: str
    container: str
    resolution_policy: str
    audio_policy: str
    subtitle_policy: str
    metadata_policy: str
    destination_directory: str
    naming_template: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ReleasePreset:
        defaults = default_release_preset()
        values = defaults.to_dict()
        for key in values:
            if key in data:
                values[key] = str(data[key])
        return cls(**values)

    def human_summary_lines(self) -> tuple[str, ...]:
        return (
            f"Release preset: {self.name}",
            f"Goal: {self.release_goal_slug}",
            f"Output preset: {self.output_preset_slug}",
            f"Container: {self.container}",
            f"Resolution: {self.resolution_policy}",
            f"Audio: {self.audio_policy}",
            f"Subtitles: {self.subtitle_policy}",
            f"Metadata: {self.metadata_policy}",
            f"Destination: {self.destination_directory}",
            f"Naming: {self.naming_template}",
        )

    def technical_summary_lines(self) -> tuple[str, ...]:
        return (
            f"release_goal={self.release_goal_slug}",
            f"output_preset={self.output_preset_slug}",
            f"container={self.container}",
            f"resolution_policy={self.resolution_policy}",
            f"audio_policy={self.audio_policy}",
            f"subtitle_policy={self.subtitle_policy}",
            f"metadata_policy={self.metadata_policy}",
            f"destination_directory={self.destination_directory}",
            f"naming_template={self.naming_template}",
        )


def default_release_preset() -> ReleasePreset:
    return ReleasePreset(
        slug="balanced-release",
        name="Balanced Release",
        release_goal_slug="balanced",
        output_preset_slug="balanced",
        container="mp4",
        resolution_policy="preserve-restored-size",
        audio_policy="copy",
        subtitle_policy="copy-compatible",
        metadata_policy="copy",
        destination_directory="outputs",
        naming_template="{source_stem}.{profile}.{release_goal}.{container}",
    )
