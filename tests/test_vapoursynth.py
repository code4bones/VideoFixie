import unittest
from pathlib import Path

from videofixie.backends.vapoursynth import (
    VapourSynthAdapter,
    build_preview_script,
    parse_progress_line,
    parse_vapoursynth_version,
    parse_vspipe_version,
)
from videofixie.domain.profiles import bundled_profiles


class VapourSynthTest(unittest.TestCase):
    def test_parse_vapoursynth_version_uses_first_non_empty_line(self) -> None:
        self.assertEqual(parse_vapoursynth_version("\nVapourSynth Video Processing Library R79\nextra"), "VapourSynth Video Processing Library R79")

    def test_parse_vspipe_version_uses_first_non_empty_line(self) -> None:
        self.assertEqual(parse_vspipe_version("vspipe R79\n"), "vspipe R79")

    def test_build_preview_script_uses_bestsource_and_builtin_resize(self) -> None:
        profile = _profile("vapoursynth-lanczos-x2")

        script = build_preview_script("cache/previews/source.mp4", profile)

        self.assertIn("core.bs.VideoSource('cache/previews/source.mp4')", script)
        self.assertIn("clip.width * 2", script)
        self.assertIn("core.resize.Lanczos", script)
        self.assertIn("clip.set_output()", script)

    def test_build_render_plan_is_inspectable(self) -> None:
        profile = _profile("vapoursynth-bicubic-x2")
        adapter = VapourSynthAdapter("/venv/bin/python", "/venv/bin/vspipe")

        plan = adapter.build_render_plan(
            source_path="cache/source.mp4",
            script_path=Path("cache/render.vpy"),
            y4m_path=Path("cache/render.y4m"),
            profile=profile,
        )

        self.assertEqual(plan.script.path, Path("cache/render.vpy"))
        self.assertIn("core.resize.Bicubic", plan.script.content)
        self.assertEqual(plan.command.argv(), ["/venv/bin/vspipe", "--progress", "-c", "y4m", "cache/render.vpy", "cache/render.y4m"])

    def test_parse_vspipe_progress_line(self) -> None:
        progress = parse_progress_line("Frame: 17/100")

        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.current_frame, 17)
        self.assertEqual(progress.total_frames, 100)
        self.assertEqual(progress.percent, 17.0)


def _profile(slug: str):
    for profile in bundled_profiles():
        if profile.slug == slug:
            return profile
    raise AssertionError(f"Profile not found: {slug}")
