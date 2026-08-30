import importlib.util
import unittest


@unittest.skipIf(importlib.util.find_spec("PySide6") is None, "PySide6 is not installed")
class TimecodeTest(unittest.TestCase):
    def test_parse_seconds_minutes_and_hours(self) -> None:
        from videofixie.ui.timecode import parse_timecode

        self.assertEqual(parse_timecode("12.5"), 12.5)
        self.assertEqual(parse_timecode("1:02.500"), 62.5)
        self.assertEqual(parse_timecode("01:02:03.250"), 3723.25)
        self.assertEqual(parse_timecode("1:02,500"), 62.5)

    def test_parse_rejects_empty_and_negative_values(self) -> None:
        from videofixie.ui.timecode import parse_timecode

        with self.assertRaises(ValueError):
            parse_timecode("")
        with self.assertRaises(ValueError):
            parse_timecode("-1")

    def test_format_timecode(self) -> None:
        from videofixie.ui.timecode import format_timecode

        self.assertEqual(format_timecode(0), "0:00.000")
        self.assertEqual(format_timecode(62.5), "1:02.500")
        self.assertEqual(format_timecode(3723.25), "1:02:03.250")


if __name__ == "__main__":
    unittest.main()
