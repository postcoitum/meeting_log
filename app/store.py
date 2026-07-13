"""회의 데이터를 로컬 SQLite에 저장하는 모듈."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_ALLOWED_UPDATE = {"title", "summary_md", "memo_md", "transcript", "stats_json"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    audio_path  TEXT NOT NULL,
    transcript  TEXT NOT NULL DEFAULT '',
    summary_md  TEXT NOT NULL DEFAULT '',
    memo_md     TEXT NOT NULL DEFAULT '',
    stats_json  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL: pywebview runs each API call on its own thread; allow a
        # transcription write and an edit write to coexist without locking.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        # 구버전 DB(stats_json 없음) 마이그레이션
        try:
            self._conn.execute(
                "ALTER TABLE meetings ADD COLUMN stats_json TEXT NOT NULL DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass  # 이미 존재
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def create_meeting(self, title, created_at, audio_path, transcript) -> int:
        cur = self._conn.execute(
            "INSERT INTO meetings (title, created_at, audio_path, transcript, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, created_at, audio_path, transcript, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_meetings(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, created_at FROM meetings ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_meeting(self, meeting_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_fields(self, meeting_id: int, **fields) -> None:
        if not fields:
            return
        bad = set(fields) - _ALLOWED_UPDATE
        if bad:
            raise ValueError(f"Unknown field(s): {', '.join(sorted(bad))}")
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [_now(), meeting_id]
        self._conn.execute(
            f"UPDATE meetings SET {cols}, updated_at = ? WHERE id = ?", vals
        )
        self._conn.commit()

    def delete_meeting(self, meeting_id: int) -> None:
        self._conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        self._conn.commit()
