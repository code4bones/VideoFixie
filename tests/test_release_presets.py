import unittest

from videofixie.domain.media import MediaInfo
from videofixie.domain.release_presets import ReleasePreset, default_release_preset
from videofixie.services.release_presets import build_release_preset, output_preset_for_goal, release_goal_choices


class ReleasePresetTest(unittest.TestCase):
    def test_release_preset_serializes_round_trip(self) -> None:
        preset = default_release_preset()

        self.assertEqual(ReleasePreset.from_dict(preset.to_dict()), preset)

    def test_release_goal_maps_to_existing_output_preset_slug(self) -> None:
        self.assertEqual(output_preset_for_goal("high-quality"), "high-quality")
        self.assertEqual(output_preset_for_goal("compact"), "compact")
        self.assertEqual(output_preset_for_goal("custom"), "balanced")

    def test_recommendation_prefers_high_quality_for_low_resolution_source(self) -> None:
        media = MediaInfo.from_ffprobe_json(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 500,
                        "height": 360,
                    },
                ],
                "format": {"format_name": "mp4", "duration": "60"},
            },
            "clip.mp4",
        )

        recommended = [choice.slug for choice in release_goal_choices(media) if choice.recommended]

        self.assertEqual(recommended, ["high-quality"])

    def test_build_release_preset_keeps_human_and_technical_summary(self) -> None:
        preset = build_release_preset(
            goal_slug="archive",
            resolution_policy="preserve-restored-size",
            container="mkv",
            audio_policy="copy",
            subtitle_policy="copy-compatible",
            metadata_policy="copy",
            destination_directory="outputs",
            naming_template="{source_stem}.{release_goal}.{container}",
        )

        self.assertEqual(preset.output_preset_slug, "archive")
        self.assertIn("Archive Release", preset.human_summary_lines()[0])
        self.assertIn("container=mkv", preset.technical_summary_lines())
