import unittest

from videofixie.domain.jobs import TestSegment, TestSegmentKind


class TestSegmentTest(unittest.TestCase):
    def test_segment_exposes_duration_and_preview_range(self) -> None:
        segment = TestSegment("Motion", 10, 25, TestSegmentKind.MOTION)

        self.assertEqual(segment.duration_seconds, 15)
        preview_range = segment.as_preview_range()
        self.assertEqual(preview_range.start_seconds, 10)
        self.assertEqual(preview_range.duration_seconds, 15)

    def test_segment_requires_end_after_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than start"):
            TestSegment("Bad", 10, 10)
