from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import which

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import OutputPreset


class FFmpegAdapter:
    def __init__(self, ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = ffprobe_path or which("ffprobe") or "ffprobe"

    def build_probe_command(self, source_path: str | Path) -> PlannedCommand:
        return PlannedCommand(
            program=self.ffprobe_path,
            args=(
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(source_path),
            ),
            label="Probe source",
        )

    def probe(self, source_path: str | Path, timeout_seconds: float = 30.0) -> MediaInfo:
        command = self.build_probe_command(source_path)
        result = subprocess.run(
            command.argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return MediaInfo.from_ffprobe_json(json.loads(result.stdout), source_path)

    def build_preview_cut_command(
        self,
        source_path: str | Path,
        output_path: str | Path,
        start_seconds: float,
        duration_seconds: float,
        crf: int = 15,
        preset: str = "veryfast",
    ) -> PlannedCommand:
        return PlannedCommand(
            program=self.ffmpeg_path,
            args=(
                "-y",
                "-ss",
                f"{start_seconds:.3f}",
                "-i",
                str(source_path),
                "-t",
                f"{duration_seconds:.3f}",
                "-map",
                "0",
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "copy",
                "-c:s",
                "copy",
                "-map_metadata",
                "0",
                str(output_path),
            ),
            label="Create preview source",
        )

    def build_encode_mux_command(
        self,
        video_source_path: str | Path,
        stream_source_path: str | Path,
        output_path: str | Path,
        output_preset: OutputPreset,
    ) -> PlannedCommand:
        args: list[str] = [
            "-y",
            "-i",
            str(video_source_path),
            "-i",
            str(stream_source_path),
            "-map",
            "0:v:0",
        ]
        if output_preset.preserve_audio:
            args.extend(("-map", "1:a?"))
        if output_preset.preserve_subtitles:
            args.extend(("-map", "1:s?"))
        args.extend(("-c:v", output_preset.codec))
        for encoder_option in output_preset.encoder_options():
            key, value = encoder_option.split("=", 1)
            args.extend((f"-{key}", value))
        if output_preset.preserve_audio:
            args.extend(("-c:a", "copy"))
        if output_preset.preserve_subtitles:
            args.extend(("-c:s", "copy"))
        if output_preset.preserve_metadata:
            args.extend(("-map_metadata", "1"))
        args.extend(("-shortest", str(output_path)))
        return PlannedCommand(
            program=self.ffmpeg_path,
            args=tuple(args),
            label="Encode and mux preview",
        )
