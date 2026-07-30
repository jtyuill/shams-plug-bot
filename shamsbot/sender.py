from __future__ import annotations

import base64
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class Sender(Protocol):
    def send(self, text: str) -> None: ...


class DryRunSender:
    def send(self, text: str) -> None:
        logger.info("dry_run_chat_message text=%s", text)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return dict(value)


class XChatSender:
    """Encrypted X Chat sender backed by X's official Chat XDK."""

    def __init__(
        self,
        *,
        access_token: str,
        conversation_id: str,
        private_keys_b64: str,
        signing_key_version: str,
        bot_user_id: str | None = None,
    ) -> None:
        try:
            from chat_xdk import Chat
            from xdk import Client
        except ImportError as error:
            raise RuntimeError(
                "live mode requires the chatxdk and xdk packages; run `pip install -e .`"
            ) from error

        self.conversation_id = conversation_id
        self.client = Client(access_token=access_token)
        self.chat = Chat()
        self.chat.import_keys(
            base64.b64decode(private_keys_b64), version=signing_key_version
        )
        self.bot_user_id = bot_user_id or str(self.client.users.get_me().data.id)
        self.chat.set_identity(self.bot_user_id, signing_key_version)
        self.chat.set_cache_keys(True)
        self._bootstrap_conversation_key()

    def _public_keys(self, user_id: str) -> list[dict[str, Any]]:
        response = self.client.users.get_public_key(user_id)
        data = response.data or []
        values = data if isinstance(data, list) else [data]
        return [_as_dict(value) for value in values]

    @staticmethod
    def _event_blobs(page: dict[str, Any]) -> list[str]:
        blobs = [
            item["encoded_event"]
            for item in page.get("data") or []
            if item.get("encoded_event")
        ]
        for item in (page.get("meta") or {}).get("conversation_key_events") or []:
            if isinstance(item, str):
                blobs.append(item)
            elif item.get("encoded_event"):
                blobs.append(item["encoded_event"])
        return list(dict.fromkeys(blobs))

    def _bootstrap_conversation_key(self) -> None:
        response = self.client.chat.get_conversation_events(
            self.conversation_id.replace(":", "-"), max_results=100
        )
        page = _as_dict(response)
        raw_events = page.get("data") or []
        sender_ids = {
            str(event["sender_id"])
            for event in raw_events
            if event.get("sender_id")
        }
        signing_keys: list[dict[str, str]] = []
        for sender_id in sender_ids:
            for key in self._public_keys(sender_id):
                signing_keys.append(
                    {
                        "user_id": sender_id,
                        "public_key_version": str(
                            key.get("public_key_version") or ""
                        ),
                        "public_key": key.get("signing_public_key") or "",
                        "identity_public_key": key.get("public_key") or "",
                        "identity_public_key_signature": key.get(
                            "identity_public_key_signature"
                        )
                        or "",
                    }
                )
        if signing_keys:
            self.chat.set_signing_keys(signing_keys)
        blobs = self._event_blobs(page)
        if not blobs:
            raise RuntimeError(
                "the group has no readable X Chat events; register the bot keys, "
                "then add the bot account to the group"
            )
        result = self.chat.decrypt_events(blobs)
        conversation_keys = result.get("conversation_keys") or {}
        if not conversation_keys.get("keys"):
            errors = result.get("errors") or {}
            raise RuntimeError(
                "could not recover the group's conversation key; ensure the bot "
                f"was added after its public key was registered (errors={errors})"
            )
        logger.info(
            "xchat_key_loaded conversation=%s version=%s",
            self.conversation_id,
            conversation_keys.get("latest_version"),
        )

    def send(self, text: str) -> None:
        from xdk.chat.models import SendMessageRequest

        payload = self.chat.encrypt_message(self.conversation_id, text)
        body = {
            "message_id": payload.message_id,
            "encoded_message_create_event": payload.encrypted_content,
            "encoded_message_event_signature": payload.encoded_event_signature,
        }
        request = SendMessageRequest.model_validate(body)
        self.client.chat.send_message(
            self.conversation_id.replace(":", "-"), request
        )
        logger.info("xchat_message_sent conversation=%s", self.conversation_id)

