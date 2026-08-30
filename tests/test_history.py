import tempfile
import unittest
import sqlite3
from contextlib import closing
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

    def test_source_can_have_multiple_saved_cuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            source = Path(tmp_dir) / "clip.mp4"
            face = TestSegment("Face", 10.0, 15.0, TestSegmentKind.FACE)
            motion = TestSegment("Motion", 30.0, 42.0, TestSegmentKind.MOTION)

            first = history.save_segment(source, face, "natural-realcugan-x2", "preview", "video2x")
            second = history.save_segment(source, motion, "balanced-realcugan-x2", "balanced", "video2x")
            cuts = history.saved_cuts(source)

            self.assertEqual(len(cuts), 2)
            self.assertEqual(cuts[0].id, second.id)
            self.assertEqual(cuts[0].segment, motion)
            self.assertEqual(cuts[1].id, first.id)
            self.assertEqual(cuts[1].segment, face)
            self.assertEqual(cuts[0].backend_slug, "video2x")

    def test_saving_same_cut_label_replaces_only_that_cut(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            history = VideoFixieHistory(Path(tmp_dir) / "history.sqlite3")
            source = Path(tmp_dir) / "clip.mp4"
            history.save_segment(source, TestSegment("Face", 10.0, 15.0, TestSegmentKind.FACE), "natural-realcugan-x2")
            history.save_segment(source, TestSegment("Motion", 30.0, 42.0, TestSegmentKind.MOTION), "balanced-realcugan-x2")

            updated = history.save_segment(source, TestSegment("Face", 12.0, 18.0, TestSegmentKind.FACE), "balanced-realcugan-x2")
            cuts_by_label = {cut.segment.label: cut for cut in history.saved_cuts(source)}

            self.assertEqual(len(cuts_by_label), 2)
            self.assertEqual(cuts_by_label["Face"].id, updated.id)
            self.assertEqual(cuts_by_label["Face"].segment.start_seconds, 12.0)
            self.assertEqual(cuts_by_label["Motion"].segment.start_seconds, 30.0)

    def test_legacy_single_cut_remains_loadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "history.sqlite3"
            history = VideoFixieHistory(db_path)
            source = Path(tmp_dir) / "clip.mp4"
            absolute = str(source.resolve(strict=False))
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    insert into source_segments (
                        source_name, source_path, label, kind, start_seconds, end_seconds,
                        profile_slug, output_preset_slug, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("clip.mp4", absolute, "Legacy", "DETAIL", 5.0, 9.0, "natural-realcugan-x2", "preview", "2026-08-30T13:00:00+00:00"),
                )
                connection.commit()

            cuts = history.saved_cuts(source)

            self.assertEqual(len(cuts), 1)
            self.assertEqual(cuts[0].id, None)
            self.assertEqual(cuts[0].segment.label, "Legacy")

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
