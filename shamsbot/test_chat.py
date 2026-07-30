from __future__ import annotations

import argparse
import logging
import os
import queue
import re
import sys
import threading
from datetime import datetime, timezone
from typing import Any

from .config import load_dotenv
from .sender import XChatSender
from .x_posts import PostStream

USERNAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _sender() -> XChatSender:
    return XChatSender(
        access_token=_required("X_ACCESS_TOKEN"),
        conversation_id=_required("CHAT_CONVERSATION_ID"),
        private_keys_b64=_required("CHAT_PRIVATE_KEYS_B64"),
        signing_key_version=os.environ.get(
            "CHAT_SIGNING_KEY_VERSION", "1"
        ).strip(),
        bot_user_id=os.environ.get("CHAT_BOT_USER_ID") or None,
    )


def send_immediate(sender: XChatSender) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sender.send(f"✅ X Chat bot smoke test — {timestamp}")
    print("Immediate encrypted test message sent.")


def wait_for_post(
    sender: XChatSender,
    *,
    bearer_token: str,
    account: str,
    timeout: float,
) -> None:
    if not USERNAME.fullmatch(account):
        raise ValueError("account must be a valid X username without @")

    tag = f"xchat-smoke-{os.getpid()}"
    stream = PostStream(
        bearer_token,
        f"from:{account} -is:retweet",
        tag,
    )
    results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

    def consume() -> None:
        try:
            post = next(stream.events())
            results.put(("post", post))
        except Exception as error:  # surfaced in the main thread
            results.put(("error", error))

    stream.ensure_rule()
    print(
        f"Waiting up to {timeout:g} seconds for @{account}'s next post. "
        "Press Ctrl-C to cancel."
    )
    worker = threading.Thread(target=consume, daemon=True)
    worker.start()
    try:
        kind, value = results.get(timeout=timeout)
        if kind == "error":
            raise value
        post_id = str(value["id"])
        url = f"https://x.com/{account}/status/{post_id}"
        sender.send(url)
        print(f"End-to-end test succeeded: {url}")
    except queue.Empty as error:
        raise TimeoutError(
            f"@{account} did not post within {timeout:g} seconds; "
            "try again or choose another account with --account"
        ) from error
    finally:
        try:
            stream.remove_rule()
        except Exception:
            logging.getLogger(__name__).exception(
                "temporary stream rule cleanup failed; remove tag=%s manually",
                tag,
            )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Verify encrypted X Chat delivery immediately or end-to-end."
    )
    parser.add_argument(
        "--immediate",
        action="store_true",
        help="send a test message now instead of waiting for a public post",
    )
    parser.add_argument(
        "--account",
        default="AP",
        help="high-frequency public account for the stream test (default: AP)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=900,
        help="seconds to wait for the next post (default: 900)",
    )
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        sender = _sender()
        if args.immediate:
            send_immediate(sender)
        else:
            wait_for_post(
                sender,
                bearer_token=_required("X_BEARER_TOKEN"),
                account=args.account.removeprefix("@"),
                timeout=args.timeout,
            )
    except (ValueError, RuntimeError, TimeoutError) as error:
        print(f"test failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
