import tempfile
import unittest
from pathlib import Path

from videofixie.domain.jobs import TestSegment, TestSegmentKind
from videofixie.domain.profiles import bundled_profiles
from videofixie.services.history import VideoFixieHistory, default_history_db_path


class VideoFixieHistoryTest(unittest.TestCase):
    def test_default_history_db_path_is_current_directory(self) -> None:
        self.assertEqual(default_history_db_path(), Path.cwd() / "videofixie.sqlite3")

    def test_save_and_load_segment_by_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            source = Path(tmp_dir) / "clip.mp4"
            segment = TestSegment("Face", 12.5, 24.0, TestSegmentKind.FACE)

            history.save_segment(source, segment, "natural-realcugan-x2")

            self.assertEqual(history.load_segment(source), segment)
            cut = history.load_cut(source)
            self.assertIsNotNone(cut)
            self.assertEqual(cut.profile_slug, "natural-realcugan-x2")

    def test_load_segment_falls_back_to_source_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            original = Path(tmp_dir) / "old" / "clip.mp4"
            moved = Path(tmp_dir) / "new" / "clip.mp4"
            segment = TestSegment("Motion", 30.0, 40.0, TestSegmentKind.MOTION)

            history.save_segment(original, segment, "balanced-realcugan-x2")

            self.assertEqual(history.load_segment(moved), segment)
            cut = history.load_cut(moved)
            self.assertIsNotNone(cut)
            self.assertEqual(cut.profile_slug, "balanced-realcugan-x2")

    def test_preview_results_store_output_links_and_segment_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            source = Path(tmp_dir) / "clip.mp4"
            output = Path(tmp_dir) / "clip.preview.mp4"
            output.write_bytes(b"preview")
            profile = bundled_profiles()[0]
            segment = TestSegment("Detail", 5.0, 15.0, TestSegmentKind.DETAIL)

            created = history.add_preview_result(source, output, profile, segment)
            results = history.preview_results(source)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], created)
            self.assertTrue(results[0].output_exists)
            self.assertEqual(results[0].segment(), segment)
            self.assertEqual(results[0].profile_slug, profile.slug)


if __name__ == "__main__":
    unittest.main()
