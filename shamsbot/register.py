from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import load_dotenv


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


def _save(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def register(confirm: bool) -> None:
    if not confirm:
        raise SystemExit(
            "This creates and registers an X Chat identity. Re-run with --confirm."
        )
    token = os.environ.get("X_ACCESS_TOKEN")
    if not token:
        raise SystemExit("X_ACCESS_TOKEN is required")
    try:
        from chat_xdk import Chat
        from xdk import Client
    except ImportError as error:
        raise SystemExit("install dependencies first: pip install -e .") from error

    state_dir = Path(os.environ.get("CHAT_STATE_DIR", "state"))
    blob_path = state_dir / "private_keys.b64"
    pending_path = state_dir / "pending_registration.json"
    marker_path = state_dir / "registration.json"
    client = Client(access_token=token)
    user_id = os.environ.get("CHAT_BOT_USER_ID") or str(
        client.users.get_me().data.id
    )
    chat = Chat()

    if blob_path.exists() and marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        print("X Chat identity is already registered; reusing it.")
        print(f"CHAT_BOT_USER_ID={marker['user_id']}")
        print(f"CHAT_SIGNING_KEY_VERSION={marker['version']}")
        print(f"CHAT_PRIVATE_KEYS_B64={blob_path.read_text().strip()}")
        return

    if blob_path.exists() and pending_path.exists():
        body = json.loads(pending_path.read_text(encoding="utf-8"))
        chat.import_keys(base64.b64decode(blob_path.read_text().strip()))
    elif blob_path.exists():
        raise SystemExit(
            f"{blob_path} exists without registration state; refusing to overwrite "
            "the private identity. Restore registration.json or move the state "
            "directory aside after verifying it is safe."
        )
    else:
        registration = chat.generate_keypairs()
        version = str(registration.version or "1")
        body = {
            "public_key": {
                "public_key": registration.public_key.public_key,
                "signing_public_key": registration.public_key.signing_public_key,
                "identity_public_key_signature":
                    registration.public_key.identity_public_key_signature,
                "signing_public_key_signature":
                    registration.public_key.signing_public_key_signature,
                "registration_method": registration.public_key.registration_method,
            },
            "version": version,
            "generate_version": bool(registration.generate_version),
        }
        encoded = base64.b64encode(bytes(chat.export_keys())).decode("ascii")
        _save(blob_path, encoded + "\n")
        _save(pending_path, json.dumps(body, indent=2) + "\n")

    public_key = body["public_key"]["public_key"]
    existing_response = client.users.get_public_key(user_id)
    existing_data = existing_response.data or []
    existing = existing_data if isinstance(existing_data, list) else [existing_data]
    found = next(
        (
            _dict(item)
            for item in existing
            if _dict(item).get("public_key") == public_key
        ),
        None,
    )
    version = str((found or {}).get("public_key_version") or body["version"])
    if not found:
        request = urllib.request.Request(
            f"https://api.x.com/2/users/{user_id}/public_keys",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode() or "{}")
                response_data = result.get("data") or {}
                if isinstance(response_data, list):
                    response_data = response_data[0] if response_data else {}
                version = str(
                    response_data.get("public_key_version", version)
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise SystemExit(
                f"registration failed with HTTP {error.code}: {detail}; "
                "the same saved identity will be reused on the next run"
            ) from error

    _save(
        marker_path,
        json.dumps({"registered": True, "user_id": user_id, "version": version}, indent=2)
        + "\n",
    )
    pending_path.unlink(missing_ok=True)
    print("X Chat identity registered.")
    print(f"CHAT_BOT_USER_ID={user_id}")
    print(f"CHAT_SIGNING_KEY_VERSION={version}")
    print(f"CHAT_PRIVATE_KEYS_B64={blob_path.read_text().strip()}")
    print("Keep the private key secret, then add this bot account to the group.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    register(args.confirm)


if __name__ == "__main__":
    main()
