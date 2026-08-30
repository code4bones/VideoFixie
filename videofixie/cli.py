from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from videofixie.backends.ffmpeg import FFmpegAdapter
from videofixie.backends.video2x import Video2XAdapter
from videofixie.domain.jobs import TestSegment, TestSegmentKind
from videofixie.domain.media import MediaInfo
from videofixie.domain.output_presets import OutputPreset, bundled_output_presets
from videofixie.domain.profiles import ProcessingProfile, bundled_profiles
from videofixie.services.environment import MachineEnvironment, discover_environment
from videofixie.services.planner import build_test_segment_job


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args, sys.stdout, sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="videofixie", description="VideoFixie diagnostics and planning tools.")
    parser.add_argument("--project-root", default=".", help="Project root used for local tool discovery.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    env_parser = subparsers.add_parser("env", help="Inspect local FFmpeg and Video2X environment.")
    env_parser.set_defaults(func=_cmd_env)

    probe_parser = subparsers.add_parser("probe", help="Analyze a source video with ffprobe.")
    probe_parser.add_argument("source", help="Source video path.")
    probe_parser.set_defaults(func=_cmd_probe)

    plan_parser = subparsers.add_parser("plan-preview", help="Print a preview processing plan without running it.")
    plan_parser.add_argument("source", help="Source video path.")
    plan_parser.add_argument("--work-dir", default="cache/previews", help="Directory for preview intermediates.")
    plan_parser.add_argument("--profile", default="natural-realcugan-x2", help="Bundled profile slug.")
    plan_parser.add_argument("--output", default="preview", help="Bundled output preset slug.")
    plan_parser.add_argument("--start", type=float, default=0.0, help="Preview start in seconds.")
    plan_parser.add_argument("--duration", type=float, default=15.0, help="Preview duration in seconds.")
    plan_parser.add_argument("--label", default="Preview", help="Test segment label.")
    plan_parser.add_argument("--kind", choices=[kind.value for kind in TestSegmentKind], default=TestSegmentKind.CUSTOM.value)
    plan_parser.add_argument("--device", type=int, default=None, help="Video2X device index. Defaults to discovered preferred GPU.")
    plan_parser.set_defaults(func=_cmd_plan_preview)

    return parser


def _cmd_env(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    del stderr
    env = discover_environment(args.project_root)
    _print_environment(env, stdout)
    return 0 if env.ffmpeg.available and env.ffprobe.available and env.video2x.available else 1


def _cmd_probe(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    del stderr
    media = FFmpegAdapter().probe(args.source)
    _print_media(media, stdout)
    return 0


def _cmd_plan_preview(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    profile = _profile_by_slug(args.profile)
    if profile is None:
        print(f"Unknown bundled profile: {args.profile}", file=stderr)
        return 2
    output_preset = _output_preset_by_slug(args.output)
    if output_preset is None:
        print(f"Unknown bundled output preset: {args.output}", file=stderr)
        return 2

    env = discover_environment(args.project_root)
    if not env.ffmpeg.available or not env.ffmpeg.path:
        print(f"ffmpeg is unavailable: {env.ffmpeg.error}", file=stderr)
        return 1
    if not env.ffprobe.available or not env.ffprobe.path:
        print(f"ffprobe is unavailable: {env.ffprobe.error}", file=stderr)
        return 1
    if not env.video2x.available or not env.video2x.path:
        print(f"Video2X is unavailable: {env.video2x.error}", file=stderr)
        return 1

    device_index = args.device
    if device_index is None:
        if env.preferred_gpu is None:
            print("No Video2X Vulkan device discovered.", file=stderr)
            return 1
        device_index = env.preferred_gpu.index

    segment = TestSegment(
        label=args.label,
        kind=TestSegmentKind(args.kind),
        start_seconds=args.start,
        end_seconds=args.start + args.duration,
    )
    job = build_test_segment_job(
        source_path=args.source,
        work_dir=Path(args.work_dir),
        profile=profile,
        segment=segment,
        device_index=device_index,
        ffmpeg=FFmpegAdapter(ffmpeg_path=env.ffmpeg.path, ffprobe_path=env.ffprobe.path),
        video2x=Video2XAdapter(env.video2x.path),
        capabilities=env.video2x_capabilities,
        output_preset=output_preset,
    )

    print(f"Profile: {profile.name} ({profile.slug})", file=stdout)
    print(
        f"Output preset: {output_preset.name} ({output_preset.slug}) "
        f"{output_preset.codec} CRF {output_preset.crf} preset {output_preset.encoder_preset}",
        file=stdout,
    )
    print(f"Segment: {segment.label} [{segment.kind.value}] {segment.start_seconds:.3f}-{segment.end_seconds:.3f}s", file=stdout)
    print(f"Output: {job.output_path}", file=stdout)
    for index, stage in enumerate(job.stages, start=1):
        print(f"\nStage {index}: {stage.label}", file=stdout)
        print(stage.command.display(), file=stdout)
    return 0


def _print_environment(env: MachineEnvironment, stdout: TextIO) -> None:
    print(f"ffmpeg: {'ok' if env.ffmpeg.available else 'missing'} {env.ffmpeg.path or ''}", file=stdout)
    print(f"ffprobe: {'ok' if env.ffprobe.available else 'missing'} {env.ffprobe.path or ''}", file=stdout)
    print(f"Video2X: {'ok' if env.video2x.available else 'missing'} {env.video2x.version or ''} {env.video2x.path or ''}", file=stdout)

    if env.video2x_capabilities is not None:
        processors = ", ".join(sorted(env.video2x_capabilities.processors))
        print(f"Processors: {processors}", file=stdout)
        print("Vulkan devices:", file=stdout)
        for device in env.video2x_capabilities.devices:
            preferred = " *preferred*" if env.preferred_gpu and env.preferred_gpu.index == device.index else ""
            device_type = f" ({device.type})" if device.type else ""
            print(f"  {device.index}. {device.name}{device_type}{preferred}", file=stdout)


def _print_media(media: MediaInfo, stdout: TextIO) -> None:
    print(f"Source: {media.path}", file=stdout)
    print(f"Duration: {_format_optional(media.duration_seconds)} s", file=stdout)
    print(f"Container: {media.format_name or 'unknown'}", file=stdout)
    print(f"Bitrate: {_format_optional(media.bit_rate)} bps", file=stdout)

    video = media.primary_video
    if video is not None:
        print("Video:", file=stdout)
        print(f"  Resolution: {video.width}x{video.height}", file=stdout)
        print(f"  FPS: {_format_optional(video.fps)}", file=stdout)
        print(f"  Codec: {video.codec_name or 'unknown'}", file=stdout)
        print(f"  Scan: {video.scan_type}", file=stdout)
        print(f"  Pixel format: {video.pix_fmt or 'unknown'}", file=stdout)
        print(f"  Display aspect: {video.display_aspect_ratio or 'unknown'}", file=stdout)
        print(f"  Video bitrate: {_format_optional(video.bit_rate)} bps", file=stdout)

    print(f"Audio streams: {len(media.audio_streams)}", file=stdout)
    for stream in media.audio_streams:
        print(
            f"  #{stream.index}: {stream.codec_name or 'unknown'}, "
            f"{stream.channels or '?'} ch, {stream.sample_rate or '?'} Hz",
            file=stdout,
        )


def _profile_by_slug(slug: str) -> ProcessingProfile | None:
    for profile in bundled_profiles():
        if profile.slug == slug:
            return profile
    return None


def _output_preset_by_slug(slug: str) -> OutputPreset | None:
    for output_preset in bundled_output_presets():
        if output_preset.slug == slug:
            return output_preset
    return None


def _format_optional(value: object) -> str:
    return "unknown" if value is None else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
