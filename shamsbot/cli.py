from __future__ import annotations

import logging
import sys

from .config import Config, load_dotenv
from .sender import DryRunSender, XChatSender
from .service import Bot
from .state import State
from .x_posts import PostStream


def main() -> None:
    load_dotenv()
    try:
        config = Config.from_env()
    except ValueError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sender = (
        DryRunSender()
        if config.dry_run
        else XChatSender(
            access_token=config.access_token or "",
            conversation_id=config.conversation_id or "",
            private_keys_b64=config.private_keys_b64 or "",
            signing_key_version=config.signing_key_version,
            bot_user_id=config.bot_user_id,
        )
    )
    state = State(config.state_db)
    bot = Bot(
        stream=PostStream(
            config.bearer_token, config.stream_rule, config.stream_rule_tag
        ),
        sender=sender,
        state=state,
        source_username=config.source_username,
        post_latest_on_start=config.post_latest_on_start,
    )
    try:
        bot.run()
    finally:
        state.close()


if __name__ == "__main__":
    main()

