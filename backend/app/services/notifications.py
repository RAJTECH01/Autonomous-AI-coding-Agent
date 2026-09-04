"""Out-of-band delivery of single-use security tokens.

Password-reset and email-verification tokens must never travel back in the HTTP
response that requested them (finding AUTH-02): possession of the mailbox is the
whole point of the factor. They are handed to a notifier instead.

The default notifier logs that a message was dispatched without the token value.
Tests swap in :class:`RecordingNotifier` and read the token from the outbox, which
is what a mail client would do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Protocol

from app.core.logging import logger


@dataclass
class SecurityMessage:
    kind: str  # password_reset | email_verification
    email: str
    token: str
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SecurityNotifier(Protocol):
    def deliver(self, message: SecurityMessage) -> None: ...


class LoggingNotifier:
    """Production default: records that delivery happened, never the token."""

    def deliver(self, message: SecurityMessage) -> None:
        logger.info(
            "Security token dispatched out of band",
            kind=message.kind,
            recipient_domain=message.email.split("@")[-1] if "@" in message.email else "unknown",
        )


class RecordingNotifier:
    """Test double standing in for a mailbox."""

    def __init__(self) -> None:
        self.outbox: List[SecurityMessage] = []

    def deliver(self, message: SecurityMessage) -> None:
        self.outbox.append(message)

    def latest(self, kind: str | None = None) -> SecurityMessage:
        messages = [m for m in self.outbox if kind is None or m.kind == kind]
        if not messages:
            raise AssertionError(f"no {kind or 'security'} message was delivered")
        return messages[-1]

    def clear(self) -> None:
        self.outbox.clear()


# Module-level notifier so deployments (and tests) can substitute one.
_notifier: SecurityNotifier = LoggingNotifier()


def get_notifier() -> SecurityNotifier:
    return _notifier


def set_notifier(notifier: SecurityNotifier) -> SecurityNotifier:
    global _notifier
    previous = _notifier
    _notifier = notifier
    return previous
