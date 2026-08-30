from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which

from videofixie.backends.vapoursynth import VapourSynthAdapter
from videofixie.backends.video2x import Video2XAdapter
from videofixie.domain.capabilities import BackendCapabilities, GpuDevice


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None
    available: bool
    version: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class MachineEnvironment:
    ffmpeg: ToolStatus
    ffprobe: ToolStatus
    video2x: ToolStatus
    video2x_capabilities: BackendCapabilities | None
    preferred_gpu: GpuDevice | None
    vapoursynth: ToolStatus = field(
        default_factory=lambda: ToolStatus(
            name="vapoursynth",
            path=None,
            available=False,
            error="Not checked",
        )
    )
    vspipe: ToolStatus = field(
        default_factory=lambda: ToolStatus(
            name="vspipe",
            path=None,
            available=False,
            error="Not checked",
        )
    )


def discover_environment(
    project_root: str | Path = ".",
    video2x_candidates: tuple[str | Path, ...] = (),
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    video2x_path: str | Path | None = None,
    preferred_gpu_index: int | None = None,
    vapoursynth_python_path: str | Path | None = None,
    vspipe_path: str | Path | None = None,
) -> MachineEnvironment:
    root = Path(project_root)
    ffmpeg_status = _probe_tool("ffmpeg", ("-version",), configured_path=ffmpeg_path)
    ffprobe_status = _probe_tool("ffprobe", ("-version",), configured_path=ffprobe_path)
    selected_video2x_path = str(video2x_path) if video2x_path else find_video2x_executable(root, video2x_candidates)
    video2x_status = _probe_video2x(selected_video2x_path)
    vapoursynth_status = _probe_vapoursynth_python(vapoursynth_python_path)
    selected_vspipe_path = _default_vspipe_path(vspipe_path, vapoursynth_python_path)
    vspipe_status = _probe_tool("vspipe", ("--version",), configured_path=selected_vspipe_path)

    capabilities: BackendCapabilities | None = None
    preferred_gpu: GpuDevice | None = None
    if video2x_status.available and video2x_status.path:
        try:
            capabilities = Video2XAdapter(video2x_status.path).capabilities()
            preferred_gpu = choose_preferred_gpu(capabilities.devices, preferred_gpu_index=preferred_gpu_index)
        except (OSError, subprocess.SubprocessError) as exc:
            video2x_status = ToolStatus(
                name="video2x",
                path=video2x_status.path,
                available=False,
                version=video2x_status.version,
                error=str(exc),
            )

    return MachineEnvironment(
        ffmpeg=ffmpeg_status,
        ffprobe=ffprobe_status,
        video2x=video2x_status,
        video2x_capabilities=capabilities,
        preferred_gpu=preferred_gpu,
        vapoursynth=vapoursynth_status,
        vspipe=vspipe_status,
    )


def find_video2x_executable(project_root: str | Path = ".", candidates: tuple[str | Path, ...] = ()) -> str | None:
    root = Path(project_root)
    paths = [
        *(Path(candidate) for candidate in candidates),
        root / "bin" / "Video2X-x86_64.AppImage",
    ]

    for path in paths:
        if path.exists():
            return str(path)

    return which("video2x")


def choose_preferred_gpu(devices: tuple[GpuDevice, ...], preferred_gpu_index: int | None = None) -> GpuDevice | None:
    if not devices:
        return None

    if preferred_gpu_index is not None:
        for device in devices:
            if device.index == preferred_gpu_index:
                return device

    for device in devices:
        device_text = f"{device.name} {device.type or ''}".lower()
        if "nvidia" in device_text and "llvmpipe" not in device_text:
            return device

    for device in devices:
        device_text = f"{device.name} {device.type or ''}".lower()
        if "discrete" in device_text and "llvmpipe" not in device_text:
            return device

    for device in devices:
        if "llvmpipe" not in device.name.lower():
            return device

    return devices[0]


def _probe_tool(name: str, version_args: tuple[str, ...], configured_path: str | Path | None = None) -> ToolStatus:
    path = str(configured_path) if configured_path else which(name)
    if path is None:
        return ToolStatus(name=name, path=None, available=False, error="Executable not found")

    try:
        result = subprocess.run(
            [path, *version_args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolStatus(name=name, path=path, available=False, error=str(exc))

    return ToolStatus(name=name, path=path, available=True, version=_first_line(result.stdout))


def _probe_video2x(path: str | None) -> ToolStatus:
    if path is None:
        return ToolStatus(name="video2x", path=None, available=False, error="Executable not found")

    try:
        version = Video2XAdapter(path).version()
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolStatus(name="video2x", path=path, available=False, error=str(exc))

    return ToolStatus(name="video2x", path=path, available=True, version=version)


def _probe_vapoursynth_python(python_path: str | Path | None = None) -> ToolStatus:
    path = str(python_path) if python_path else sys.executable
    try:
        version = VapourSynthAdapter(path).version()
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolStatus(name="vapoursynth", path=path, available=False, error=_subprocess_error_text(exc))

    return ToolStatus(name="vapoursynth", path=path, available=True, version=version)


def _default_vspipe_path(vspipe_path: str | Path | None, python_path: str | Path | None) -> str | Path | None:
    if vspipe_path is not None:
        return vspipe_path
    candidate = Path(python_path or sys.executable).parent / "vspipe"
    if candidate.exists():
        return candidate
    return None


def _subprocess_error_text(error: BaseException) -> str:
    stderr = getattr(error, "stderr", None)
    if stderr:
        return str(stderr).strip()
    return str(error)


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None
