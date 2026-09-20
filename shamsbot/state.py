from __future__ import annotations

import sqlite3
from pathlib import Path


class State:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS delivered_posts (
                post_id TEXT PRIMARY KEY,
                delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS news_decisions (
                post_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                allowed INTEGER NOT NULL,
                reason TEXT NOT NULL,
                news REAL,
                redundant REAL,
                judged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._db.commit()

    def contains(self, post_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM delivered_posts WHERE post_id = ? "
            "UNION ALL SELECT 1 FROM news_decisions WHERE post_id = ? AND allowed = 0",
            (post_id, post_id),
        ).fetchone()
        return row is not None

    def mark_delivered(self, post_id: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO delivered_posts(post_id) VALUES (?)", (post_id,)
        )
        self._db.commit()

    def record_decision(
        self, post_id: str, text: str, allowed: bool, reason: str,
        news: float | None = None, redundant: float | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO news_decisions
                (post_id, text, allowed, reason, news, redundant)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, text, int(allowed), reason, news, redundant),
        )
        self._db.commit()

    def recent_news(self) -> list[str]:
        rows = self._db.execute(
            """
            SELECT n.text FROM news_decisions n
            JOIN delivered_posts d ON d.post_id = n.post_id
            WHERE n.allowed = 1 AND d.delivered_at >= datetime('now', '-2 days')
            ORDER BY d.delivered_at DESC, d.rowid DESC LIMIT 40
            """
        ).fetchall()
        # Bound context while retaining complete tweets, never misleading snippets.
        result: list[str] = []
        size = 0
        for (text,) in rows:
            if size + len(text) > 48000:
                break
            result.append(text)
            size += len(text)
        return result

    def seed(self, post_ids: list[str]) -> None:
        self._db.executemany(
            "INSERT OR IGNORE INTO delivered_posts(post_id) VALUES (?)",
            [(post_id,) for post_id in post_ids],
        )
        self._db.commit()

    def is_initialized(self) -> bool:
        row = self._db.execute(
            "SELECT value FROM metadata WHERE key = 'initialized'"
        ).fetchone()
        return bool(row and row[0] == "1")

    def set_initialized(self) -> None:
        self._db.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('initialized', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

