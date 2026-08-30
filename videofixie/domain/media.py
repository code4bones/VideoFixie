from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


def parse_fraction(value: str | None) -> Fraction | None:
    if not value or value == "0/0":
        return None
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None


def parse_float(value: Any) -> float | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> int | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class VideoStreamInfo:
    index: int
    codec_name: str | None
    width: int
    height: int
    avg_frame_rate: Fraction | None
    r_frame_rate: Fraction | None
    duration_seconds: float | None
    bit_rate: int | None
    pix_fmt: str | None
    field_order: str | None
    display_aspect_ratio: str | None
    nb_frames: int | None

    @property
    def fps(self) -> float | None:
        rate = self.avg_frame_rate or self.r_frame_rate
        if rate is None:
            return None
        return float(rate)

    @property
    def scan_type(self) -> str:
        if not self.field_order:
            return "unknown"
        if self.field_order == "progressive":
            return "progressive"
        return "interlaced"


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec_name: str | None
    channels: int | None
    channel_layout: str | None
    sample_rate: int | None
    duration_seconds: float | None
    bit_rate: int | None
    language: str | None


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str | None
    duration_seconds: float | None
    bit_rate: int | None
    size_bytes: int | None
    video_streams: tuple[VideoStreamInfo, ...]
    audio_streams: tuple[AudioStreamInfo, ...]

    @property
    def primary_video(self) -> VideoStreamInfo | None:
        return self.video_streams[0] if self.video_streams else None

    @classmethod
    def from_ffprobe_json(cls, data: dict[str, Any], path: str | Path) -> "MediaInfo":
        streams = data.get("streams", [])
        video_streams: list[VideoStreamInfo] = []
        audio_streams: list[AudioStreamInfo] = []

        for stream in streams:
            stream_type = stream.get("codec_type")
            if stream_type == "video":
                video_streams.append(
                    VideoStreamInfo(
                        index=int(stream["index"]),
                        codec_name=stream.get("codec_name"),
                        width=int(stream.get("width") or 0),
                        height=int(stream.get("height") or 0),
                        avg_frame_rate=parse_fraction(stream.get("avg_frame_rate")),
                        r_frame_rate=parse_fraction(stream.get("r_frame_rate")),
                        duration_seconds=parse_float(stream.get("duration")),
                        bit_rate=parse_int(stream.get("bit_rate")),
                        pix_fmt=stream.get("pix_fmt"),
                        field_order=stream.get("field_order"),
                        display_aspect_ratio=stream.get("display_aspect_ratio"),
                        nb_frames=parse_int(stream.get("nb_frames")),
                    )
                )
            elif stream_type == "audio":
                tags = stream.get("tags") or {}
                audio_streams.append(
                    AudioStreamInfo(
                        index=int(stream["index"]),
                        codec_name=stream.get("codec_name"),
                        channels=parse_int(stream.get("channels")),
                        channel_layout=stream.get("channel_layout"),
                        sample_rate=parse_int(stream.get("sample_rate")),
                        duration_seconds=parse_float(stream.get("duration")),
                        bit_rate=parse_int(stream.get("bit_rate")),
                        language=tags.get("language"),
                    )
                )

        format_info = data.get("format") or {}
        return cls(
            path=Path(path),
            format_name=format_info.get("format_name"),
            duration_seconds=parse_float(format_info.get("duration")),
            bit_rate=parse_int(format_info.get("bit_rate")),
            size_bytes=parse_int(format_info.get("size")),
            video_streams=tuple(video_streams),
            audio_streams=tuple(audio_streams),
        )
