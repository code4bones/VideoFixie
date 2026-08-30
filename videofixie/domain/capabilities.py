from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GpuDevice:
    index: int
    name: str
    type: str | None = None
    vulkan_api_version: str | None = None
    driver_version: str | None = None
    device_id: str | None = None


@dataclass(frozen=True)
class ProcessorCapability:
    name: str
    models: tuple[str, ...] = ()
    supports_scaling_factor: bool = True
    supports_target_size: bool = True
    supports_noise_level: bool = False


@dataclass(frozen=True)
class BackendCapabilities:
    name: str
    version: str | None
    processors: dict[str, ProcessorCapability] = field(default_factory=dict)
    devices: tuple[GpuDevice, ...] = ()
