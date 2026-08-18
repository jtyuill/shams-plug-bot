from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shamsbot.service import Bot
from shamsbot.state import State


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)


class FakeStream:
    def __init__(self, posts: list[dict] | None = None) -> None:
        self.posts = posts or []
        self.recent_calls = 0
        self.rule_ensured = False

    def recent(self, max_results: int = 10) -> list[dict]:
        self.recent_calls += 1
        return list(self.posts)

    def ensure_rule(self) -> None:
        self.rule_ensured = True

    def events(self) -> list[dict]:
        raise KeyboardInterrupt


class BotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.state = State(Path(self.temp.name) / "state.sqlite3")
        self.sender = FakeSender()
        self.stream = FakeStream()
        self.bot = Bot(
            stream=self.stream,  # type: ignore[arg-type]
            sender=self.sender,
            state=self.state,
            source_username="ShamsCharania",
        )

    def tearDown(self) -> None:
        self.state.close()
        self.temp.cleanup()

    def test_delivers_canonical_link_only_once(self) -> None:
        self.assertTrue(self.bot.deliver("123"))
        self.assertFalse(self.bot.deliver("123"))
        self.assertEqual(
            self.sender.messages,
            ["https://x.com/ShamsCharania/status/123"],
        )

    def test_delivers_using_event_author(self) -> None:
        self.assertTrue(self.bot.deliver("456", "memgrizz"))

        self.assertEqual(
            self.sender.messages,
            ["https://x.com/memgrizz/status/456"],
        )

    def test_run_does_not_fetch_or_send_recent_posts_on_startup(self) -> None:
        self.stream.posts = [
            {"id": "old", "created_at": "2026-01-01T00:00:00Z"},
        ]

        with self.assertRaises(KeyboardInterrupt):
            self.bot.run()

        self.assertTrue(self.stream.rule_ensured)
        self.assertEqual(self.stream.recent_calls, 0)
        self.assertEqual(self.sender.messages, [])

    def test_first_start_seeds_history_without_spam(self) -> None:
        self.stream.posts = [
            {"id": "1", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "2", "created_at": "2026-01-02T00:00:00Z"},
        ]
        self.bot.recover_recent()
        self.assertEqual(self.sender.messages, [])
        self.assertTrue(self.state.contains("1"))
        self.assertTrue(self.state.contains("2"))

    def test_manual_recovery_delivers_missed_posts_oldest_first(self) -> None:
        self.state.set_initialized()
        self.stream.posts = [
            {"id": "2", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "1", "created_at": "2026-01-01T00:00:00Z"},
        ]
        self.bot.recover_recent()
        self.assertEqual(
            self.sender.messages,
            [
                "https://x.com/ShamsCharania/status/1",
                "https://x.com/ShamsCharania/status/2",
            ],
        )

if __name__ == "__main__":
    unittest.main()
