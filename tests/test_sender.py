from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shamsbot.sender import POST_URL, XChatSender


class FakeChat:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def encrypt_message(
        self, conversation_id: str, text: str, *, attachments: object
    ) -> SimpleNamespace:
        self.calls.append((conversation_id, text, attachments))
        return SimpleNamespace(
            message_id="message-id",
            encrypted_content="encrypted",
            encoded_event_signature="signature",
        )


class FakeChatClient:
    def send_message(self, conversation_id: str, body: object) -> None:
        pass


class SenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sender = XChatSender.__new__(XChatSender)
        self.sender.conversation_id = "g123"
        self.sender.chat = FakeChat()
        self.sender.client = SimpleNamespace(chat=FakeChatClient())

    def test_sends_post_as_attachment(self) -> None:
        url = "https://x.com/ShamsCharania/status/123"

        with patch("shamsbot.sender.load_oauth_access_token", return_value=None):
            self.sender.send(url)

        self.assertEqual(
            self.sender.chat.calls,
            [
                (
                    "g123",
                    "",
                    [
                        {
                            "attachment_type": "post",
                            "rest_id": "123",
                            "post_url": url,
                        }
                    ],
                )
            ],
        )

    def test_sends_regular_text_without_attachment(self) -> None:
        with patch("shamsbot.sender.load_oauth_access_token", return_value=None):
            self.sender.send("smoke test")

        self.assertEqual(self.sender.chat.calls, [("g123", "smoke test", None)])


class PostUrlTests(unittest.TestCase):
    def test_matches_canonical_x_post_url(self) -> None:
        match = POST_URL.fullmatch("https://x.com/ShamsCharania/status/123")

        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "123")

    def test_does_not_match_other_links(self) -> None:
        self.assertIsNone(POST_URL.fullmatch("https://example.com/status/123"))


if __name__ == "__main__":
    unittest.main()
