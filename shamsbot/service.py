from __future__ import annotations

import logging
import time

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
        post_latest_on_start: bool = False,
    ) -> None:
        self.stream = stream
        self.sender = sender
        self.state = state
        self.source_username = source_username
        self.post_latest_on_start = post_latest_on_start

    def post_url(self, post_id: str, username: str | None = None) -> str:
        return f"https://x.com/{username or self.source_username}/status/{post_id}"

    def deliver(self, post_id: str, username: str | None = None) -> bool:
        if self.state.contains(post_id):
            return False
        url = self.post_url(post_id, username)
        self.sender.send(url)
        self.state.mark_delivered(post_id)
        logger.info("post_delivered post_id=%s url=%s", post_id, url)
        return True

    def recover(self) -> None:
        posts = self.stream.recent(max_results=10)
        posts.sort(key=lambda post: (post.get("created_at", ""), post["id"]))
        if not self.state.is_initialized():
            if self.post_latest_on_start and posts:
                self.state.seed([post["id"] for post in posts[:-1]])
                self.deliver(posts[-1]["id"], posts[-1].get("username"))
            else:
                self.state.seed([post["id"] for post in posts])
            self.state.set_initialized()
            logger.info("state_initialized existing_posts=%d", len(posts))
            return
        for post in posts:
            self.deliver(post["id"], post.get("username"))

    def run(self) -> None:
        self.stream.ensure_rule()
        backoff = 1
        while True:
            try:
                self.recover()
                backoff = 1
                for post in self.stream.events():
                    self.deliver(str(post["id"]), post.get("username"))
                raise XApiError("filtered stream closed")
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("stream_cycle_failed retry_in_seconds=%d", backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
