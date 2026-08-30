from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from videofixie.domain.commands import PlannedCommand
from videofixie.domain.jobs import GeneratedFile, JobProgress
from videofixie.domain.profiles import ProcessingProfile


VAPOURSYNTH_IMPORT_PROBE = (
    "from vapoursynth import core\n"
    "text = str(core).strip().splitlines()\n"
    "print(text[0] if text else 'VapourSynth import ok')\n"
)
VAPOURSYNTH_PLUGIN_PROBE = (
    "import vapoursynth as vs\n"
    "for plugin in vs.core.plugins():\n"
    "    print(f'{plugin.namespace}\\t{plugin.name}\\t{plugin.identifier}')\n"
)
PROGRESS_RE = re.compile(r"Frame:\s*(?P<current>\d+)\s*/\s*(?P<total>\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class VapourSynthPluginRequirement:
    namespace: str
    purpose: str


@dataclass(frozen=True)
class VapourSynthPipelinePreset:
    slug: str
    name: str
    summary: str
    required_plugins: tuple[VapourSynthPluginRequirement, ...]
    scale: int = 2
    work_format: str = "YUV444P16"
    output_format: str = "YUV420P8"
    resize_filter: str = "Spline36"
    deblock_weight: float = 0.16
    chroma_cleanup_weight: float = 0.28
    temporal_weights: tuple[float, ...] = (1.0, 2.0, 1.0)
    temporal_scenechange: int = 25
    sharpen_weight: float = 0.16
    texture_weight: float = 0.20


@dataclass(frozen=True)
class VapourSynthRenderPlan:
    script: GeneratedFile
    y4m_path: Path
    command: PlannedCommand


class VapourSynthAdapter:
    def __init__(self, python_path: str | Path, vspipe_path: str | Path = "vspipe") -> None:
        self.python_path = str(python_path)
        self.vspipe_path = str(vspipe_path)

    def build_import_probe_command(self) -> PlannedCommand:
        return PlannedCommand(
            self.python_path,
            ("-c", VAPOURSYNTH_IMPORT_PROBE),
            "Detect VapourSynth Python runtime",
        )

    def build_plugin_probe_command(self) -> PlannedCommand:
        return PlannedCommand(
            self.python_path,
            ("-c", VAPOURSYNTH_PLUGIN_PROBE),
            "Detect VapourSynth plugins",
        )

    def version(self, timeout_seconds: float = 10.0) -> str | None:
        result = subprocess.run(
            self.build_import_probe_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_vapoursynth_version(result.stdout)

    def plugin_namespaces(self, timeout_seconds: float = 10.0) -> tuple[str, ...]:
        result = subprocess.run(
            self.build_plugin_probe_command().argv(),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return parse_plugin_namespaces(result.stdout)

    def build_render_plan(
        self,
        source_path: str | Path,
        script_path: str | Path,
        y4m_path: str | Path,
        profile: ProcessingProfile,
        available_plugins: tuple[str, ...] = (),
    ) -> VapourSynthRenderPlan:
        validate_pipeline_dependencies(profile, available_plugins)
        script = GeneratedFile(
            path=Path(script_path),
            content=build_preview_script(source_path, profile),
            description="VapourSynth script",
        )
        command = PlannedCommand(
            self.vspipe_path,
            ("--progress", "-c", "y4m", str(script.path), str(y4m_path)),
            "Run VapourSynth script",
        )
        return VapourSynthRenderPlan(script=script, y4m_path=Path(y4m_path), command=command)


def build_preview_script(source_path: str | Path, profile: ProcessingProfile) -> str:
    preset = pipeline_preset_for_profile(profile)
    if preset.slug in {"builtin-lanczos", "builtin-bicubic"}:
        return _build_resize_baseline_script(source_path, profile, preset)
    return _build_restoration_script(source_path, preset)


def pipeline_preset_for_profile(profile: ProcessingProfile) -> VapourSynthPipelinePreset:
    try:
        return VAPOURSYNTH_PIPELINE_PRESETS[profile.model]
    except KeyError as exc:
        raise ValueError(f"Unsupported VapourSynth profile model: {profile.model}") from exc


def required_plugin_requirements(profile: ProcessingProfile) -> tuple[VapourSynthPluginRequirement, ...]:
    return pipeline_preset_for_profile(profile).required_plugins


def validate_pipeline_dependencies(profile: ProcessingProfile, available_plugins: tuple[str, ...]) -> None:
    if not available_plugins:
        return

    available = set(available_plugins)
    missing = [requirement for requirement in required_plugin_requirements(profile) if requirement.namespace not in available]
    if not missing:
        return

    details = "; ".join(f"{requirement.namespace} ({requirement.purpose})" for requirement in missing)
    raise RuntimeError(f"Missing VapourSynth plugin dependency for profile {profile.slug}: {details}")


def parse_plugin_namespaces(text: str) -> tuple[str, ...]:
    namespaces: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        namespace = line.split("\t", 1)[0].strip()
        if namespace and namespace not in namespaces:
            namespaces.append(namespace)
    return tuple(namespaces)


def _build_resize_baseline_script(
    source_path: str | Path,
    profile: ProcessingProfile,
    preset: VapourSynthPipelinePreset,
) -> str:
    scale = profile.scale or preset.scale
    source_literal = repr(str(Path(source_path).expanduser().resolve(strict=False)))
    return "\n".join(
        (
            "import vapoursynth as vs",
            "core = vs.core",
            _dependency_check_snippet(preset),
            f"clip = core.bs.VideoSource({source_literal})",
            f"width = clip.width * {scale}",
            f"height = clip.height * {scale}",
            f"clip = core.resize.{preset.resize_filter}(clip, width=width, height=height, format=vs.YUV420P8)",
            "clip.set_output()",
            "",
        )
    )


def _build_restoration_script(source_path: str | Path, preset: VapourSynthPipelinePreset) -> str:
    source_literal = repr(str(Path(source_path).expanduser().resolve(strict=False)))
    temporal_weights = _python_float_tuple(preset.temporal_weights)
    temporal_scale = sum(preset.temporal_weights)
    work_format = f"vs.{preset.work_format}"
    output_format = f"vs.{preset.output_format}"
    texture_expr = f"x 32768 - {preset.texture_weight:.3f} * 32768 +"
    return "\n".join(
        (
            "import vapoursynth as vs",
            "core = vs.core",
            _dependency_check_snippet(preset),
            "",
            f"# Pipeline: {preset.name}",
            f"# {preset.summary}",
            f"source = core.bs.VideoSource({source_literal})",
            "",
            "# Stage 1: source decode and high-bit-depth working format.",
            f"work = core.resize.Bicubic(source, format={work_format})",
            "",
            "# Stage 2: mild deblock/compression cleanup using median and chroma blur.",
            "luma_median = core.std.Median(work, planes=[0])",
            "chroma_blur = core.std.BoxBlur(work, planes=[1, 2], hradius=1, hpasses=1, vradius=1, vpasses=1)",
            f"clip = core.std.Merge(work, luma_median, weight=[{preset.deblock_weight:.3f}, 0.0, 0.0])",
            f"clip = core.std.Merge(clip, chroma_blur, weight=[0.0, {preset.chroma_cleanup_weight:.3f}, {preset.chroma_cleanup_weight:.3f}])",
            "",
            "# Stage 3: conservative temporal denoise; frame count and FPS are preserved.",
            "clip = core.std.AverageFrames(",
            f"    clip, weights={temporal_weights}, scale={temporal_scale:.3f},",
            f"    scenechange={preset.temporal_scenechange}, planes=[0, 1, 2]",
            ")",
            "",
            "# Stage 4: upscale with an edge-stable built-in resize filter.",
            f"width = source.width * {preset.scale}",
            f"height = source.height * {preset.scale}",
            f"clip = core.resize.{preset.resize_filter}(clip, width=width, height=height, format={work_format})",
            "",
            "# Stage 5: optional mild luma sharpen blended back conservatively.",
            "sharpened = core.std.Convolution(",
            "    clip, matrix=[0, -1, 0, -1, 5, -1, 0, -1, 0],",
            "    divisor=1.0, saturate=1, planes=[0]",
            ")",
            f"clip = core.std.Merge(clip, sharpened, weight=[{preset.sharpen_weight:.3f}, 0.0, 0.0])",
            "",
            "# Stage 6: subtle source texture reintroduction to avoid a synthetic smooth look.",
            f"texture_source = core.resize.{preset.resize_filter}(work, width=width, height=height, format={work_format})",
            "texture_blur = core.std.BoxBlur(texture_source, planes=[0], hradius=1, hpasses=1, vradius=1, vpasses=1)",
            "texture = core.std.MakeDiff(texture_source, texture_blur, planes=[0])",
            f"texture = core.std.Expr([texture], expr=[{texture_expr!r}, 'x', 'x'])",
            "clip = core.std.MergeDiff(clip, texture, planes=[0])",
            "clip = core.std.Limiter(clip, planes=[0, 1, 2])",
            "",
            "# Stage 7: final preview handoff. No frame interpolation is performed.",
            f"clip = core.resize.Bicubic(clip, format={output_format}, dither_type='error_diffusion')",
            "clip = core.std.CopyFrameProps(clip, source)",
            "clip.set_output()",
            "",
        )
    )


def parse_progress_line(line: str) -> JobProgress | None:
    match = PROGRESS_RE.search(line)
    if not match:
        return None

    current = int(match.group("current"))
    total = int(match.group("total"))
    return JobProgress(
        current_frame=current,
        total_frames=total,
        percent=(current / total * 100.0) if total else None,
    )


def parse_vapoursynth_version(text: str) -> str | None:
    return _first_line(text)


def parse_vspipe_version(text: str) -> str | None:
    return _first_line(text)


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return None


def _dependency_check_snippet(preset: VapourSynthPipelinePreset) -> str:
    checks = [
        "def _require_plugin(namespace, purpose):",
        "    if not hasattr(core, namespace):",
        "        raise RuntimeError(f'Missing VapourSynth plugin: {namespace} ({purpose})')",
    ]
    for requirement in preset.required_plugins:
        checks.append(f"_require_plugin({requirement.namespace!r}, {requirement.purpose!r})")
    return "\n".join(checks)


def _python_float_tuple(values: tuple[float, ...]) -> str:
    return "[" + ", ".join(f"{value:.3f}" for value in values) + "]"


VAPOURSYNTH_PIPELINE_PRESETS = {
    "restoration-natural-v1": VapourSynthPipelinePreset(
        slug="restoration-natural-v1",
        name="Natural restoration v1",
        summary="Mild compression cleanup, temporal denoise, x2 upscale, restrained sharpen and source texture return.",
        required_plugins=(VapourSynthPluginRequirement("bs", "BestSource source decode"),),
    ),
    "builtin-lanczos": VapourSynthPipelinePreset(
        slug="builtin-lanczos",
        name="Lanczos x2 baseline",
        summary="BestSource decode and built-in Lanczos x2 resize.",
        required_plugins=(VapourSynthPluginRequirement("bs", "BestSource source decode"),),
        resize_filter="Lanczos",
    ),
    "builtin-bicubic": VapourSynthPipelinePreset(
        slug="builtin-bicubic",
        name="Bicubic x2 baseline",
        summary="BestSource decode and built-in Bicubic x2 resize.",
        required_plugins=(VapourSynthPluginRequirement("bs", "BestSource source decode"),),
        resize_filter="Bicubic",
    ),
}
