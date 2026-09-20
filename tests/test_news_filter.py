from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from shamsbot.news_filter import NewsFilter


class NewsFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filter = NewsFilter("test-key")

    def test_uncertain_news_and_repeats_are_suppressed(self) -> None:
        for news, redundant, expected in [(0.95, 0.03, True), (0.84, 0.03, False), (0.96, 0.9, False), (0.9, 0.21, False)]:
            with self.subTest(news=news, redundant=redundant):
                response = io.BytesIO(json.dumps({"answers": {
                    "news": {"noul": news}, "redundant": {"noul": redundant},
                }}).encode())
                with patch("shamsbot.news_filter.urllib.request.urlopen", return_value=response):
                    decision = self.filter.judge({"text": "A signing"}, [])
                self.assertEqual(decision.allow, expected)

    def test_malformed_api_probabilities_cannot_authorize_delivery(self) -> None:
        for value in [True, "0.99", None, -1, 1.1, float("nan"), float("inf")]:
            with self.subTest(value=value):
                response = io.BytesIO(json.dumps({"answers": {
                    "news": {"noul": value}, "redundant": {"noul": 0.01},
                }}).encode())
                with patch("shamsbot.news_filter.urllib.request.urlopen", return_value=response):
                    with self.assertRaises(ValueError):
                        self.filter.judge({"text": "A signing"}, [])

    def test_missing_or_oversized_text_is_not_guessed(self) -> None:
        with patch("shamsbot.news_filter.urllib.request.urlopen", side_effect=AssertionError("Must not request")):
            for post in [{}, {"text": " "}, {"text": "a" * 12001}]:
                self.assertFalse(self.filter.judge(post, []).allow)


if __name__ == "__main__":
    unittest.main()
