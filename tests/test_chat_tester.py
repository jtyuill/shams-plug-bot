from __future__ import annotations

import unittest

from shamsbot.test_chat import USERNAME


class ChatTesterTests(unittest.TestCase):
    def test_accepts_normal_x_usernames(self) -> None:
        self.assertIsNotNone(USERNAME.fullmatch("AP"))
        self.assertIsNotNone(USERNAME.fullmatch("ShamsCharania"))

    def test_rejects_injected_or_prefixed_rules(self) -> None:
        self.assertIsNone(USERNAME.fullmatch("@AP"))
        self.assertIsNone(USERNAME.fullmatch("AP -is:reply"))


if __name__ == "__main__":
    unittest.main()

