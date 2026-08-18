from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load a deliberately small, unquoted KEY=VALUE .env file."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_oauth_access_token() -> str | None:
    """Load the saved user token, refreshing and persisting it when needed."""
    state_dir = Path(os.environ.get("CHAT_STATE_DIR", "state"))
    token_path = state_dir / "oauth_token.json"
    if not token_path.exists():
        return os.environ.get("X_ACCESS_TOKEN") or None

    token = json.loads(token_path.read_text(encoding="utf-8"))
    access_token = token.get("access_token")
    if access_token and float(token.get("expires_at") or 0) > time.time() + 300:
        os.environ["X_ACCESS_TOKEN"] = access_token
        return access_token

    client_id = os.environ.get("X_OAUTH_CLIENT_ID") or os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("X_OAUTH_CLIENT_SECRET") or os.environ.get(
        "CLIENT_SECRET"
    )
    refresh_token = token.get("refresh_token")
    if not client_id or not client_secret or not refresh_token:
        raise ValueError(
            "OAuth token expired and refresh requires CLIENT_ID, CLIENT_SECRET, "
            "and state/oauth_token.json"
        )

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode("utf-8")
    ).decode("ascii")
    request = urllib.request.Request(
        "https://api.x.com/2/oauth2/token",
        data=urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}
        ).encode("ascii"),
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        refreshed = json.loads(response.read().decode("utf-8"))

    refreshed.setdefault("refresh_token", refresh_token)
    refreshed["expires_at"] = time.time() + float(refreshed.get("expires_in") or 0)
    token_path.write_text(json.dumps(refreshed, indent=2) + "\n", encoding="utf-8")
    token_path.chmod(0o600)
    os.environ["X_ACCESS_TOKEN"] = refreshed["access_token"]
    return refreshed["access_token"]


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    bearer_token: str
    stream_rule: str = "from:ShamsCharania -is:retweet"
    stream_rule_tag: str = "shams-x-chat"
    source_username: str = "ShamsCharania"
    dry_run: bool = True
    access_token: str | None = None
    conversation_id: str | None = None
    bot_user_id: str | None = None
    private_keys_b64: str | None = None
    signing_key_version: str = "1"
    state_db: Path = Path("state/bot.sqlite3")
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        bearer_token = os.environ.get("X_BEARER_TOKEN", "").strip()
        if not bearer_token:
            raise ValueError("X_BEARER_TOKEN is required")
        config = cls(
            bearer_token=bearer_token,
            stream_rule=os.environ.get(
                "X_STREAM_RULE", "from:ShamsCharania -is:retweet"
            ).strip(),
            stream_rule_tag=os.environ.get(
                "X_STREAM_RULE_TAG", "shams-x-chat"
            ).strip(),
            source_username=os.environ.get(
                "X_SOURCE_USERNAME", "ShamsCharania"
            ).strip(),
            dry_run=_bool("CHAT_DRY_RUN", True),
            access_token=os.environ.get("X_ACCESS_TOKEN") or None,
            conversation_id=os.environ.get("CHAT_CONVERSATION_ID") or None,
            bot_user_id=os.environ.get("CHAT_BOT_USER_ID") or None,
            private_keys_b64=os.environ.get("CHAT_PRIVATE_KEYS_B64") or None,
            signing_key_version=os.environ.get(
                "CHAT_SIGNING_KEY_VERSION", "1"
            ).strip(),
            state_db=Path(os.environ.get("STATE_DB", "state/bot.sqlite3")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )
        if not config.stream_rule or not config.stream_rule_tag:
            raise ValueError("X_STREAM_RULE and X_STREAM_RULE_TAG cannot be empty")
        if not config.dry_run:
            missing = [
                name
                for name, value in {
                    "X_ACCESS_TOKEN": config.access_token,
                    "CHAT_CONVERSATION_ID": config.conversation_id,
                    "CHAT_PRIVATE_KEYS_B64": config.private_keys_b64,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "live X Chat mode requires " + ", ".join(missing)
                )
        return config
