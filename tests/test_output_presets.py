import unittest

from videofixie.domain.output_presets import bundled_output_presets, preview_output_preset


class OutputPresetTest(unittest.TestCase):
    def test_bundled_output_presets_include_required_intents(self) -> None:
        presets = bundled_output_presets()

        self.assertEqual(
            {preset.slug for preset in presets},
            {"preview", "high-quality", "balanced", "compact", "archive"},
        )
        self.assertTrue(preview_output_preset().preview_safe)

    def test_output_preset_compiles_to_encoder_options(self) -> None:
        preset = preview_output_preset()

        self.assertEqual(preset.encoder_options(), ("crf=16", "preset=slow"))
