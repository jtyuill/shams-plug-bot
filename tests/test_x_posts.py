from __future__ import annotations

import unittest

from shamsbot.x_posts import PostStream


class PostStreamTests(unittest.TestCase):
    def test_adds_username_to_single_stream_event(self) -> None:
        event = {
            "data": {"id": "123", "author_id": "42"},
            "includes": {"users": [{"id": "42", "username": "ShamsCharania"}]},
        }

        self.assertEqual(
            PostStream._with_usernames(event),
            [{"id": "123", "author_id": "42", "username": "ShamsCharania"}],
        )

    def test_adds_usernames_to_recent_search_list(self) -> None:
        result = {
            "data": [{"id": "123", "author_id": "42"}],
            "includes": {"users": [{"id": "42", "username": "ShamsCharania"}]},
        }

        self.assertEqual(
            PostStream._with_usernames(result),
            [{"id": "123", "author_id": "42", "username": "ShamsCharania"}],
        )


if __name__ == "__main__":
    unittest.main()
