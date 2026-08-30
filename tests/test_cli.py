import io
import unittest
from unittest.mock import patch

from videofixie.cli import main


class CliTest(unittest.TestCase):
    def test_unknown_preview_profile_returns_usage_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            result = main(["plan-preview", "samples/1.mp4", "--profile", "missing"])

        self.assertEqual(result, 2)
        self.assertIn("Unknown bundled profile", stderr.getvalue())

    def test_unknown_output_preset_returns_usage_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            result = main(["plan-preview", "samples/1.mp4", "--output", "missing"])

        self.assertEqual(result, 2)
        self.assertIn("Unknown bundled output preset", stderr.getvalue())
