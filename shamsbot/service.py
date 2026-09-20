from __future__ import annotations

import logging
import time

from .news_filter import Decision, NewsFilter
from .sender import Sender
from .state import State
from .x_posts import PostStream, XApiError

logger = logging.getLogger(__name__)


class Bot:
    def __init__(
        self,
        *,
        stream: PostStream,
        sender: Sender,
        state: State,
        source_username: str,
        news_filter: NewsFilter,
    ) -> None:
        self.stream = stream
        self.sender = sender
        self.state = state
        self.source_username = source_username
        self.news_filter = news_filter

    def post_url(self, post_id: str, username: str | None = None) -> str:
        return f"https://x.com/{username or self.source_username}/status/{post_id}"

    def deliver(self, post: dict) -> bool:
        post_id = str(post["id"])
        username = post.get("username") or self.source_username
        if self.state.contains(post_id):
            return False
        if username.lower() == "shamscharania":
            try:
                decision = self.news_filter.judge(post, self.state.recent_news())
            except Exception as error:
                # Never fall back to sending on a timeout, quota error or bad response.
                logger.warning("news_filter_failed post_id=%s error_type=%s", post_id, type(error).__name__)
                decision = Decision(False, "api_error")
            self.state.record_decision(
                post_id, post.get("text") or "", decision.allow, decision.reason,
                decision.news, decision.redundant,
            )
            logger.info(
                "news_filter post_id=%s allow=%s reason=%s news=%s redundant=%s",
                post_id, decision.allow, decision.reason, decision.news, decision.redundant,
            )
            if not decision.allow:
                return False
        url = self.post_url(post_id, username)
        self.sender.send(url)
        self.state.mark_delivered(post_id)
        logger.info("post_delivered post_id=%s url=%s", post_id, url)
        return True

    def recover_recent(self) -> None:
        """Explicitly deliver recent matching posts that are not in local state."""
        posts = self.stream.recent(max_results=10)
        posts.sort(key=lambda post: (post.get("created_at", ""), post["id"]))
        if not self.state.is_initialized():
            self.state.seed([post["id"] for post in posts])
            self.state.set_initialized()
            logger.info("state_initialized existing_posts=%d", len(posts))
            return
        for post in posts:
            self.deliver(post)

    def run(self) -> None:
        self.stream.ensure_rule()
        backoff = 1
        while True:
            try:
                backoff = 1
                for post in self.stream.events():
                    self.deliver(post)
                raise XApiError("filtered stream closed")
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("stream_cycle_failed retry_in_seconds=%d", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
