import unittest

from videofixie.backends.vapoursynth import parse_vapoursynth_version, parse_vspipe_version


class VapourSynthTest(unittest.TestCase):
    def test_parse_vapoursynth_version_uses_first_non_empty_line(self) -> None:
        self.assertEqual(parse_vapoursynth_version("\nVapourSynth Video Processing Library R79\nextra"), "VapourSynth Video Processing Library R79")

    def test_parse_vspipe_version_uses_first_non_empty_line(self) -> None:
        self.assertEqual(parse_vspipe_version("vspipe R79\n"), "vspipe R79")
