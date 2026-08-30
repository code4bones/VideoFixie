from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from videofixie.domain.settings import AppSettings
from videofixie.services.history import default_history_db_path


class VideoFixieSettingsStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_history_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load(self) -> AppSettings:
        with self._connect() as connection:
            rows = connection.execute("select key, value_json from app_settings").fetchall()
        values = {str(row["key"]): json.loads(str(row["value_json"])) for row in rows}
        return AppSettings.from_dict(values)

    def save(self, settings: AppSettings) -> None:
        now = _utc_now()
        with self._connect() as connection:
            for key, value in settings.to_dict().items():
                connection.execute(
                    """
                    insert into app_settings (key, value_json, updated_at)
                    values (?, ?, ?)
                    on conflict(key) do update set
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (key, json.dumps(value), now),
                )

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
            connection.execute(
                """
                create table if not exists app_settings (
                    key text primary key,
                    value_json text not null,
                    updated_at text not null
                )
                """
            )


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
