from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from videofixie.domain.jobs import TestSegment, TestSegmentKind
from videofixie.domain.output_presets import OutputPreset, preview_output_preset
from videofixie.domain.profiles import ProcessingProfile


@dataclass(frozen=True)
class SavedCut:
    segment: TestSegment
    profile_slug: str | None
    updated_at: str
    output_preset_slug: str | None = None
    id: int | None = None
    source_name: str | None = None
    source_path: Path | None = None
    backend_slug: str | None = None


@dataclass(frozen=True)
class PreviewResult:
    id: int
    source_name: str
    source_path: Path
    output_path: Path
    profile_slug: str
    profile_name: str
    segment_label: str
    segment_kind: TestSegmentKind
    start_seconds: float
    end_seconds: float
    created_at: str
    output_preset_slug: str = "preview"
    output_preset_name: str = "Preview"

    @property
    def output_exists(self) -> bool:
        return self.output_path.exists()

    def segment(self) -> TestSegment:
        return TestSegment(
            label=self.segment_label,
            kind=self.segment_kind,
            start_seconds=self.start_seconds,
            end_seconds=self.end_seconds,
        )


class VideoFixieHistory:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_history_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def save_segment(
        self,
        source_path: str | Path,
        segment: TestSegment,
        profile_slug: str | None = None,
        output_preset_slug: str | None = None,
        backend_slug: str | None = None,
    ) -> SavedCut:
        source = Path(source_path)
        source_absolute = str(source.expanduser().resolve(strict=False))
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into source_saved_cuts (
                    source_name, source_path, label, kind, start_seconds, end_seconds,
                    profile_slug, output_preset_slug, backend_slug, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(source_path, label) do update set
                    kind = excluded.kind,
                    start_seconds = excluded.start_seconds,
                    end_seconds = excluded.end_seconds,
                    profile_slug = excluded.profile_slug,
                    output_preset_slug = excluded.output_preset_slug,
                    backend_slug = excluded.backend_slug,
                    updated_at = excluded.updated_at
                returning id
                """,
                (
                    source.name,
                    source_absolute,
                    segment.label,
                    segment.kind.value,
                    segment.start_seconds,
                    segment.end_seconds,
                    profile_slug,
                    output_preset_slug,
                    backend_slug,
                    now,
                ),
            )
            cut_id = int(cursor.fetchone()["id"])
            connection.execute(
                """
                insert into source_segments (
                    source_name, source_path, label, kind, start_seconds, end_seconds,
                    profile_slug, output_preset_slug, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(source_name, source_path) do update set
                    label = excluded.label,
                    kind = excluded.kind,
                    start_seconds = excluded.start_seconds,
                    end_seconds = excluded.end_seconds,
                    profile_slug = excluded.profile_slug,
                    output_preset_slug = excluded.output_preset_slug,
                    updated_at = excluded.updated_at
                """,
                (
                    source.name,
                    source_absolute,
                    segment.label,
                    segment.kind.value,
                    segment.start_seconds,
                    segment.end_seconds,
                    profile_slug,
                    output_preset_slug,
                    now,
                ),
            )
        return SavedCut(
            id=cut_id,
            source_name=source.name,
            source_path=Path(source_absolute),
            segment=segment,
            profile_slug=profile_slug,
            output_preset_slug=output_preset_slug,
            backend_slug=backend_slug,
            updated_at=now,
        )

    def load_segment(self, source_path: str | Path) -> TestSegment | None:
        cut = self.load_cut(source_path)
        return cut.segment if cut is not None else None

    def load_cut(self, source_path: str | Path) -> SavedCut | None:
        cuts = self.saved_cuts(source_path, limit=1)
        if cuts:
            return cuts[0]
        return self._load_legacy_cut(source_path)

    def saved_cuts(self, source_path: str | Path, limit: int = 100) -> tuple[SavedCut, ...]:
        source = Path(source_path)
        absolute = str(source.expanduser().resolve(strict=False))
        with self._connect() as connection:
            rows = connection.execute(
                """
                select *
                from source_saved_cuts
                where source_path = ? or source_name = ?
                order by updated_at desc, id desc
                limit ?
                """,
                (absolute, source.name, limit),
            ).fetchall()
        if rows:
            return tuple(_cut_from_row(row) for row in rows)
        legacy = self._load_legacy_cut(source_path)
        return (legacy,) if legacy is not None else ()

    def _load_legacy_cut(self, source_path: str | Path) -> SavedCut | None:
        source = Path(source_path)
        absolute = str(source.expanduser().resolve(strict=False))
        with self._connect() as connection:
            row = connection.execute(
                """
                select label, kind, start_seconds, end_seconds, profile_slug, output_preset_slug, updated_at
                from source_segments
                where source_path = ?
                order by updated_at desc
                limit 1
                """,
                (absolute,),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """
                    select label, kind, start_seconds, end_seconds, profile_slug, output_preset_slug, updated_at
                    from source_segments
                    where source_name = ?
                    order by updated_at desc
                    limit 1
                    """,
                    (source.name,),
                ).fetchone()
        return _cut_from_row(row) if row is not None else None

    def add_preview_result(
        self,
        source_path: str | Path,
        output_path: str | Path,
        profile: ProcessingProfile,
        segment: TestSegment,
        output_preset: OutputPreset | None = None,
    ) -> PreviewResult:
        selected_output_preset = output_preset or preview_output_preset()
        source = Path(source_path)
        output = Path(output_path)
        source_absolute = str(source.expanduser().resolve(strict=False))
        output_absolute = str(output.expanduser().resolve(strict=False))
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into preview_results (
                    source_name, source_path, output_path, profile_slug, profile_name,
                    output_preset_slug, output_preset_name,
                    segment_label, segment_kind, start_seconds, end_seconds, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.name,
                    source_absolute,
                    output_absolute,
                    profile.slug,
                    profile.name,
                    selected_output_preset.slug,
                    selected_output_preset.name,
                    segment.label,
                    segment.kind.value,
                    segment.start_seconds,
                    segment.end_seconds,
                    now,
                ),
            )
            result_id = int(cursor.lastrowid)
        return PreviewResult(
            id=result_id,
            source_name=source.name,
            source_path=Path(source_absolute),
            output_path=Path(output_absolute),
            profile_slug=profile.slug,
            profile_name=profile.name,
            segment_label=segment.label,
            segment_kind=segment.kind,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            created_at=now,
            output_preset_slug=selected_output_preset.slug,
            output_preset_name=selected_output_preset.name,
        )

    def preview_results(self, source_path: str | Path, limit: int = 50) -> tuple[PreviewResult, ...]:
        source = Path(source_path)
        absolute = str(source.expanduser().resolve(strict=False))
        with self._connect() as connection:
            rows = connection.execute(
                """
                select *
                from preview_results
                where source_path = ? or source_name = ?
                order by created_at desc, id desc
                limit ?
                """,
                (absolute, source.name, limit),
            ).fetchall()
        return tuple(_preview_result_from_row(row) for row in rows)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("pragma foreign_keys = on")
            connection.executescript(
                """
                create table if not exists source_segments (
                    source_name text not null,
                    source_path text not null,
                    label text not null,
                    kind text not null,
                    start_seconds real not null,
                    end_seconds real not null,
                    profile_slug text,
                    output_preset_slug text,
                    updated_at text not null,
                    primary key (source_name, source_path)
                );

                create table if not exists preview_results (
                    id integer primary key autoincrement,
                    source_name text not null,
                    source_path text not null,
                    output_path text not null,
                    profile_slug text not null,
                    profile_name text not null,
                    output_preset_slug text not null default 'preview',
                    output_preset_name text not null default 'Preview',
                    segment_label text not null,
                    segment_kind text not null,
                    start_seconds real not null,
                    end_seconds real not null,
                    created_at text not null
                );

                create table if not exists source_saved_cuts (
                    id integer primary key autoincrement,
                    source_name text not null,
                    source_path text not null,
                    label text not null,
                    kind text not null,
                    start_seconds real not null,
                    end_seconds real not null,
                    profile_slug text,
                    output_preset_slug text,
                    backend_slug text,
                    updated_at text not null,
                    unique(source_path, label)
                );

                create index if not exists idx_source_segments_name_updated
                    on source_segments(source_name, updated_at desc);

                create index if not exists idx_source_saved_cuts_source_updated
                    on source_saved_cuts(source_path, updated_at desc);

                create index if not exists idx_source_saved_cuts_name_updated
                    on source_saved_cuts(source_name, updated_at desc);

                create index if not exists idx_preview_results_source_updated
                    on preview_results(source_path, created_at desc);

                create index if not exists idx_preview_results_name_updated
                    on preview_results(source_name, created_at desc);
                """
            )
            _ensure_column(connection, "source_segments", "output_preset_slug", "text")
            _ensure_column(connection, "source_saved_cuts", "backend_slug", "text")
            _ensure_column(connection, "preview_results", "output_preset_slug", "text not null default 'preview'")
            _ensure_column(connection, "preview_results", "output_preset_name", "text not null default 'Preview'")


def default_history_db_path() -> Path:
    return Path.cwd() / "videofixie.sqlite3"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _cut_from_row(row: sqlite3.Row) -> SavedCut:
    segment = TestSegment(
        label=str(row["label"]),
        kind=TestSegmentKind(str(row["kind"])),
        start_seconds=float(row["start_seconds"]),
        end_seconds=float(row["end_seconds"]),
    )
    return SavedCut(
        segment=segment,
        profile_slug=row["profile_slug"],
        updated_at=str(row["updated_at"]),
        output_preset_slug=row["output_preset_slug"],
        id=_optional_row_int(row, "id"),
        source_name=_optional_row_str(row, "source_name"),
        source_path=_optional_row_path(row, "source_path"),
        backend_slug=_optional_row_str(row, "backend_slug"),
    )


def _preview_result_from_row(row: sqlite3.Row) -> PreviewResult:
    return PreviewResult(
        id=int(row["id"]),
        source_name=str(row["source_name"]),
        source_path=Path(str(row["source_path"])),
        output_path=Path(str(row["output_path"])),
        profile_slug=str(row["profile_slug"]),
        profile_name=str(row["profile_name"]),
        segment_label=str(row["segment_label"]),
        segment_kind=TestSegmentKind(str(row["segment_kind"])),
        start_seconds=float(row["start_seconds"]),
        end_seconds=float(row["end_seconds"]),
        created_at=str(row["created_at"]),
        output_preset_slug=str(row["output_preset_slug"]),
        output_preset_name=str(row["output_preset_name"]),
    )


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {str(row["name"]) for row in connection.execute(f"pragma table_info({table_name})")}
    if column_name not in columns:
        connection.execute(f"alter table {table_name} add column {column_name} {definition}")


def _optional_row_str(row: sqlite3.Row, column_name: str) -> str | None:
    if column_name not in row.keys():
        return None
    value = row[column_name]
    return str(value) if value is not None else None


def _optional_row_int(row: sqlite3.Row, column_name: str) -> int | None:
    value = _optional_row_str(row, column_name)
    return int(value) if value is not None else None


def _optional_row_path(row: sqlite3.Row, column_name: str) -> Path | None:
    value = _optional_row_str(row, column_name)
    return Path(value) if value is not None else None
