"""Builds signed payment webhook requests: valid, tampered, wrongly signed, and expired.

This deliberately re-implements the signing scheme instead of importing it from
the SUT, so the tests act as an independent oracle for the contract:
``X-Signature = hex(HMAC-SHA256(secret, f"{X-Timestamp}.{raw_body}"))``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field

REPLAY_WINDOW_SECONDS = 300


def canonical_event(event_type: str, order_id: int, amount_cents: int) -> bytes:
    return json.dumps(
        {"event_type": event_type, "order_id": order_id, "amount_cents": amount_cents},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def hmac_hex(secret: str, timestamp: str, body: bytes) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class SignedWebhook:
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    def as_request_kwargs(self) -> dict[str, object]:
        return {"content": self.body, "headers": dict(self.headers)}


@dataclass(frozen=True)
class WebhookSigner:
    secret: str

    def _headers(self, timestamp: str, signature: str, idempotency_key: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            "X-Signature": signature,
            "Idempotency-Key": idempotency_key,
        }

    def valid(
        self,
        body: bytes,
        *,
        idempotency_key: str | None = None,
        timestamp: int | None = None,
    ) -> SignedWebhook:
        ts = str(int(time.time()) if timestamp is None else timestamp)
        key = idempotency_key or f"evt_{uuid.uuid4().hex}"
        return SignedWebhook(body=body, headers=self._headers(ts, hmac_hex(self.secret, ts, body), key))

    def event(
        self,
        event_type: str,
        order_id: int,
        amount_cents: int = 1000,
        *,
        idempotency_key: str | None = None,
        timestamp: int | None = None,
    ) -> SignedWebhook:
        return self.valid(
            canonical_event(event_type, order_id, amount_cents),
            idempotency_key=idempotency_key,
            timestamp=timestamp,
        )

    def tampered(
        self, body: bytes, tampered_body: bytes, *, idempotency_key: str | None = None
    ) -> SignedWebhook:
        """Signature is valid for ``body`` but ``tampered_body`` is what gets sent."""
        if body == tampered_body:
            raise ValueError("tampered_body must differ from body")
        original = self.valid(body, idempotency_key=idempotency_key)
        return SignedWebhook(body=tampered_body, headers=original.headers)

    def invalid_signature(
        self, body: bytes, *, idempotency_key: str | None = None
    ) -> SignedWebhook:
        """Correct timestamp and body, but signed with a secret the server does not know."""
        attacker = WebhookSigner(secret=f"{self.secret}-attacker")
        return attacker.valid(body, idempotency_key=idempotency_key)

    def expired(
        self,
        body: bytes,
        *,
        age_seconds: int = REPLAY_WINDOW_SECONDS + 60,
        idempotency_key: str | None = None,
    ) -> SignedWebhook:
        """Correctly signed, but the timestamp is older than the replay window."""
        return self.valid(
            body, idempotency_key=idempotency_key, timestamp=int(time.time()) - age_seconds
        )
