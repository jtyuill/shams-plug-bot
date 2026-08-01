from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import urllib.parse
from pathlib import Path

from .config import load_dotenv

SCOPES = "dm.read dm.write tweet.read users.read offline.access"
REDIRECT_PATH = "/callback"
CALLBACK_TIMEOUT_SECONDS = 300.0

_CALLBACK: dict[str, str] = {}
_READY = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        _CALLBACK.update({k: v[0] for k, v in query.items()})
        _READY.set()
        body = b"<html><body>You can close this window and return to the terminal.</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def _update_env(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{key}="
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def login(client_id: str, client_secret: str | None, port: int, env_file: str) -> None:
    redirect_uri = f"http://localhost:{port}{REDIRECT_PATH}"
    try:
        from xdk import Client
    except ImportError as error:
        raise SystemExit("install dependencies first: pip install -e .") from error

    client = Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
    )

    server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        auth_url = client.get_authorization_url()
    except Exception as error:
        server.shutdown()
        raise SystemExit(f"could not build the authorization URL: {error}") from error

    def _out(text: str = "") -> None:
        print(text, flush=True)

    _out("1. Open this URL in a browser logged in as the BOT account:")
    _out(f"\n   {auth_url}\n")
    _out("2. Approve the requested scopes (dm.read, dm.write, tweet.read,")
    _out("   users.read, offline.access).")
    _out("3. X redirects to the local callback; the script exchanges the code.")
    _out(
        f"\nWaiting for the callback on {redirect_uri} "
        f"(timeout {CALLBACK_TIMEOUT_SECONDS:g}s)..."
    )

    if not _READY.wait(timeout=CALLBACK_TIMEOUT_SECONDS):
        server.shutdown()
        raise SystemExit(
            "timed out waiting for authorization. Re-run and complete the browser flow."
        )
    server.shutdown()

    if "error" in _CALLBACK:
        raise SystemExit(f"authorization failed: {_CALLBACK['error']}")
    code = _CALLBACK.get("code")
    if not code:
        raise SystemExit("callback had no authorization code; try again.")

    token = client.exchange_code(code)
    access_token = token.get("access_token")
    if not access_token:
        raise SystemExit("token exchange returned no access_token; check the Client ID/secret.")

    env_path = Path(env_file)
    _update_env(env_path, "X_ACCESS_TOKEN", access_token)
    env_path.chmod(0o600)
    print(f"X_ACCESS_TOKEN written to {env_path}")

    state_dir = Path(os.environ.get("CHAT_STATE_DIR", "state"))
    state_dir.mkdir(parents=True, exist_ok=True)
    token_path = state_dir / "oauth_token.json"
    token_path.write_text(json.dumps(token, indent=2) + "\n", encoding="utf-8")
    token_path.chmod(0o600)
    print(f"Full token (refresh_token, expiry) saved to {token_path}")

    print("\nNext: set the Client ID in the portal, then run:")
    print("  shams-register-chat --confirm")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Log the bot account in via OAuth 2.0 (PKCE) and store the "
        "user access token in .env."
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("X_OAUTH_CLIENT_ID", "")
        or os.environ.get("CLIENT_ID", "")
        or None,
        help="OAuth 2.0 Client ID from the X Developer Portal (default: "
        "X_OAUTH_CLIENT_ID or CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("X_OAUTH_CLIENT_SECRET", "")
        or os.environ.get("CLIENT_SECRET", "")
        or None,
        help="OAuth 2.0 Client Secret, required only for confidential apps "
        "(default: X_OAUTH_CLIENT_SECRET or CLIENT_SECRET)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("X_OAUTH_REDIRECT_PORT", "8080")),
        help="local callback port (default: 8080)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help=".env file to write X_ACCESS_TOKEN into (default: .env)",
    )
    args = parser.parse_args()
    if not args.client_id:
        parser.error(
            "--client-id is required (or set X_OAUTH_CLIENT_ID / CLIENT_ID); copy "
            "the OAuth 2.0 Client ID from the Developer Portal app's User "
            "authentication settings"
        )
    if args.port < 1 or args.port > 65535:
        parser.error("--port must be a valid TCP port")
    login(args.client_id, args.client_secret, args.port, args.env_file)


if __name__ == "__main__":
    main()
