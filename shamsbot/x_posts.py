from __future__ import annotations

import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)
API_BASE = "https://api.x.com/2"


class XApiError(RuntimeError):
    pass


class PostStream:
    def __init__(self, bearer_token: str, rule: str, tag: str) -> None:
        self.bearer_token = bearer_token
        self.rule = rule
        self.tag = tag

    def _request_json(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            API_BASE + path,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
                "User-Agent": "shams-x-chat-bot/0.1",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise XApiError(f"X API {method} {path}: HTTP {error.code}: {detail}") from error

    def ensure_rule(self) -> None:
        rules = self._request_json("GET", "/tweets/search/stream/rules").get("data") or []
        if any(
            item.get("value") == self.rule and item.get("tag") == self.tag
            for item in rules
        ):
            return
        stale_ids = [
            item["id"]
            for item in rules
            if item.get("tag") == self.tag and item.get("id")
        ]
        if stale_ids:
            self._request_json(
                "POST",
                "/tweets/search/stream/rules",
                {"delete": {"ids": stale_ids}},
            )
        self._request_json(
            "POST",
            "/tweets/search/stream/rules",
            {"add": [{"value": self.rule, "tag": self.tag}]},
        )
        logger.info("stream_rule_added rule=%r tag=%s", self.rule, self.tag)

    def remove_rule(self) -> None:
        """Remove only rules carrying this stream instance's exact tag."""
        rules = self._request_json("GET", "/tweets/search/stream/rules").get("data") or []
        rule_ids = [
            item["id"]
            for item in rules
            if item.get("tag") == self.tag and item.get("id")
        ]
        if rule_ids:
            self._request_json(
                "POST",
                "/tweets/search/stream/rules",
                {"delete": {"ids": rule_ids}},
            )
            logger.info("stream_rule_removed tag=%s", self.tag)

    @staticmethod
    def _with_usernames(result: dict[str, Any]) -> list[dict[str, Any]]:
        usernames = {
            str(user["id"]): user["username"]
            for user in (result.get("includes") or {}).get("users") or []
            if user.get("id") and user.get("username")
        }
        raw_posts = result.get("data") or []
        # Search responses contain a list, while filtered-stream events contain
        # one Post object. Normalize both shapes before adding usernames.
        if isinstance(raw_posts, dict):
            raw_posts = [raw_posts]
        posts = []
        for post in raw_posts:
            item = dict(post)
            username = usernames.get(str(item.get("author_id", "")))
            if username:
                item["username"] = username
            posts.append(item)
        return posts

    def recent(self, max_results: int = 10) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "query": self.rule,
                "max_results": max(10, min(max_results, 100)),
                "tweet.fields": "author_id,created_at",
                "expansions": "author_id",
                "user.fields": "username",
            }
        )
        result = self._request_json("GET", f"/tweets/search/recent?{query}")
        return self._with_usernames(result)

    def events(self) -> Iterator[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "tweet.fields": "author_id,created_at",
                "expansions": "author_id",
                "user.fields": "username",
            }
        )
        request = urllib.request.Request(
            f"{API_BASE}/tweets/search/stream?{query}",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": "shams-x-chat-bot/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                logger.info("stream_connected")
                for raw_line in response:
                    line = raw_line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    matching = event.get("matching_rules") or []
                    if matching and not any(
                        rule.get("tag") == self.tag for rule in matching
                    ):
                        continue
                    if event.get("data", {}).get("id"):
                        posts = self._with_usernames(event)
                        if posts:
                            yield posts[0]
        except (urllib.error.URLError, socket.timeout, json.JSONDecodeError) as error:
            raise XApiError(f"filtered stream disconnected: {error}") from error
