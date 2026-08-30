from __future__ import annotations

import re
import subprocess
from pathlib import Path

from videofixie.domain.capabilities import BackendCapabilities, GpuDevice, ProcessorCapability
from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import JobProgress
from videofixie.domain.output_presets import OutputPreset
from videofixie.domain.profiles import ProcessingProfile


PROCESSOR_RE = re.compile(r"Processor to use\s+\((?P<items>[^)]+)\)")
REALESRGAN_RE = re.compile(r"Name of the RealESRGAN model to use\s+\((?P<items>[^)]+)\)")
REALCUGAN_RE = re.compile(r"Name of the RealCUGAN model to use\s+\((?P<items>[^)]+)\)")
RIFE_RE = re.compile(r"Name of the RIFE model to use\s+\((?P<items>[^)]+)\)")
VERSION_RE = re.compile(r"Video2X version (?P<version>\S+)")
DEVICE_RE = re.compile(r"^(?P<index>\d+)\.\s+(?P<name>.+)$")
PROGRESS_RE = re.compile(
    r"frame\s*=\s*(?P<current>\d+)\s*/\s*(?P<total>\d+)"
    r".*?fps\s*=\s*(?P<fps>\d+(?:\.\d+)?)"
    r"(?:.*?elapsed\s*=\s*(?P<elapsed>[^;,\s]+))?"
    r"(?:.*?remaining\s*=\s*(?P<remaining>[^;,\s]+))?",
    re.IGNORECASE,
)
FATAL_RUNTIME_MESSAGES = (
    ("vkQueueSubmit failed", "Vulkan queue submission failed; output may be corrupt"),
    ("device lost", "Vulkan device lost; output may be corrupt"),
)
VIDEO2X_PROCESSING_LABEL = "Run Video2X AI processing"


class Video2XAdapter:
    def __init__(self, executable_path: str | Path = "video2x") -> None:
        self.executable_path = str(executable_path)

    def build_version_command(self) -> PlannedCommand:
        return PlannedCommand(self.executable_path, ("--version",), "Detect Video2X version")

    def build_help_command(self) -> PlannedCommand:
        return PlannedCommand(self.executable_path, ("--help",), "Detect Video2X capabilities")

    def build_list_devices_command(self) -> PlannedCommand:
        return PlannedCommand(self.executable_path, ("--list-devices",), "List Vulkan devices")

    def version(self, timeout_seconds: float = 10.0) -> str | None:
        result = subprocess.run(
            self.build_version_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_version(result.stdout)

    def list_devices(self, timeout_seconds: float = 10.0) -> tuple[GpuDevice, ...]:
        result = subprocess.run(
            self.build_list_devices_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_devices(result.stdout)

    def capabilities(self, timeout_seconds: float = 10.0) -> BackendCapabilities:
        help_result = subprocess.run(
            self.build_help_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        version_result = subprocess.run(
            self.build_version_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        devices_result = subprocess.run(
            self.build_list_devices_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_capabilities(
            help_text=help_result.stdout,
            version_text=version_result.stdout,
            devices_text=devices_result.stdout,
        )

    def build_upscale_command(
        self,
        source_path: str | Path,
        output_path: str | Path,
        profile: ProcessingProfile,
        output_preset: OutputPreset,
        device_index: int,
        capabilities: BackendCapabilities | None = None,
    ) -> PlannedCommand:
        validate_cli_profile(profile)
        if capabilities is not None:
            validate_profile(capabilities, profile)

        args: list[str] = [
            "-i",
            str(source_path),
            "-o",
            str(output_path),
            "-p",
            profile.processor,
            "-d",
            str(device_index),
            "-c",
            output_preset.codec,
        ]
        for encoder_option in output_preset.encoder_options():
            args.extend(("-e", encoder_option))

        if profile.scale is not None:
            args.extend(("-s", str(profile.scale)))
        if profile.noise_level is not None:
            args.extend(("-n", str(profile.noise_level)))

        if profile.processor == "realcugan":
            args.extend(("--realcugan-model", profile.model))
        elif profile.processor == "realesrgan":
            args.extend(("--realesrgan-model", profile.model))
        elif profile.processor == "rife":
            args.extend(("--rife-model", profile.model))

        if not (output_preset.preserve_audio or output_preset.preserve_subtitles):
            args.append("--no-copy-streams")

        return PlannedCommand(
            program=self.executable_path,
            args=tuple(args),
            label=VIDEO2X_PROCESSING_LABEL,
        )


def validate_model_files(profile: ProcessingProfile, models_directory: str | Path) -> None:
    missing = missing_model_files(profile, models_directory)
    if not missing:
        return

    missing_text = ", ".join(str(path) for path in missing)
    raise FileNotFoundError(
        f"Video2X model files are missing for profile {profile.slug}: {missing_text}. "
        f"Models directory: {Path(models_directory)}"
    )


def missing_model_files(profile: ProcessingProfile, models_directory: str | Path) -> tuple[Path, ...]:
    models_root = Path(models_directory)
    return tuple(path for path in required_model_files(profile, models_root) if not path.exists())


def required_model_files(profile: ProcessingProfile, models_directory: str | Path) -> tuple[Path, ...]:
    models_root = Path(models_directory)
    relative_paths = required_model_relative_paths(profile)
    return tuple(models_root / path for path in relative_paths)


def required_model_relative_paths(profile: ProcessingProfile) -> tuple[Path, ...]:
    if profile.processor == "realcugan":
        if profile.scale is None:
            raise ValueError(f"RealCUGAN profile {profile.slug} must define a scale")
        stem = f"up{profile.scale}x-{_realcugan_noise_suffix(profile.noise_level)}"
        return (
            Path("realcugan") / profile.model / f"{stem}.param",
            Path("realcugan") / profile.model / f"{stem}.bin",
        )

    if profile.processor == "realesrgan":
        if profile.scale is None:
            raise ValueError(f"RealESRGAN profile {profile.slug} must define a scale")
        stem = f"{profile.model}-x{profile.scale}"
        return (
            Path("realesrgan") / f"{stem}.param",
            Path("realesrgan") / f"{stem}.bin",
        )

    if profile.processor == "libplacebo":
        return (Path("libplacebo") / f"{profile.model}.glsl",)

    return ()


def validate_profile(capabilities: BackendCapabilities, profile: ProcessingProfile) -> None:
    validate_cli_profile(profile)

    processor = capabilities.processors.get(profile.processor)
    if processor is None:
        raise ValueError(f"Video2X processor is not available: {profile.processor}")

    if processor.models and profile.model not in processor.models:
        raise ValueError(f"Model {profile.model} is not available for processor {profile.processor}")

    if profile.scale is not None and not processor.supports_scaling_factor:
        raise ValueError(f"Processor {profile.processor} does not support scaling factor")

    if profile.noise_level is not None and not processor.supports_noise_level:
        raise ValueError(f"Processor {profile.processor} does not support noise level")


def validate_cli_profile(profile: ProcessingProfile) -> None:
    if profile.processor != "realcugan" or profile.noise_level is None:
        return
    if profile.noise_level in (0, 1, 2, 3):
        return
    raise ValueError(
        f"Video2X RealCUGAN noise level is not supported by the current CLI: {profile.noise_level}"
    )


def _realcugan_noise_suffix(noise_level: int | None) -> str:
    if noise_level is None or noise_level == 0:
        return "no-denoise"
    if noise_level == -1:
        return "conservative"
    if noise_level in (1, 2, 3):
        return f"denoise{noise_level}x"
    raise ValueError(f"Unsupported RealCUGAN noise level: {noise_level}")


def parse_csv_items(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def parse_version(text: str) -> str | None:
    match = VERSION_RE.search(text)
    return match.group("version") if match else None


def detect_runtime_error(stdout: tuple[str, ...] = (), stderr: tuple[str, ...] = ()) -> str | None:
    for line in (*stdout, *stderr):
        normalized = line.lower()
        for marker, message in FATAL_RUNTIME_MESSAGES:
            if marker.lower() in normalized:
                return message
    return None


def parse_capabilities(help_text: str, version_text: str = "", devices_text: str = "") -> BackendCapabilities:
    processors: dict[str, ProcessorCapability] = {}

    processor_match = PROCESSOR_RE.search(help_text)
    processor_names = parse_csv_items(processor_match.group("items")) if processor_match else ()

    realesrgan_models = _models_from_match(REALESRGAN_RE.search(help_text))
    realcugan_models = _models_from_match(REALCUGAN_RE.search(help_text))
    rife_models = _models_from_match(RIFE_RE.search(help_text))

    for name in processor_names:
        if name == "realesrgan":
            processors[name] = ProcessorCapability(name=name, models=realesrgan_models)
        elif name == "realcugan":
            processors[name] = ProcessorCapability(name=name, models=realcugan_models, supports_noise_level=True)
        elif name == "rife":
            processors[name] = ProcessorCapability(
                name=name,
                models=rife_models,
                supports_scaling_factor=False,
                supports_target_size=False,
            )
        else:
            processors[name] = ProcessorCapability(name=name)

    return BackendCapabilities(
        name="Video2X",
        version=parse_version(version_text),
        processors=processors,
        devices=parse_devices(devices_text),
    )


def parse_devices(text: str) -> tuple[GpuDevice, ...]:
    devices: list[GpuDevice] = []
    current: dict[str, str | int] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        device_match = DEVICE_RE.match(line)
        if device_match:
            if current is not None:
                devices.append(_device_from_dict(current))
            current = {
                "index": int(device_match.group("index")),
                "name": device_match.group("name").strip(),
            }
            continue

        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        current[normalized] = value.strip()

    if current is not None:
        devices.append(_device_from_dict(current))

    return tuple(devices)


def parse_progress_line(line: str) -> JobProgress | None:
    match = PROGRESS_RE.search(line)
    if not match:
        return None

    current = int(match.group("current"))
    total = int(match.group("total"))
    fps = float(match.group("fps"))
    percent = (current / total * 100.0) if total else None

    return JobProgress(
        current_frame=current,
        total_frames=total,
        percent=percent,
        fps=fps,
        elapsed=match.group("elapsed"),
        remaining=match.group("remaining"),
    )


def _models_from_match(match: re.Match[str] | None) -> tuple[str, ...]:
    return parse_csv_items(match.group("items")) if match else ()


def _device_from_dict(data: dict[str, str | int]) -> GpuDevice:
    return GpuDevice(
        index=int(data["index"]),
        name=str(data["name"]),
        type=_optional_str(data.get("type")),
        vulkan_api_version=_optional_str(data.get("vulkan_api_version")),
        driver_version=_optional_str(data.get("driver_version")),
        device_id=_optional_str(data.get("device_id")),
    )


def _optional_str(value: str | int | None) -> str | None:
    if value is None:
        return None
    return str(value)
