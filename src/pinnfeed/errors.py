from __future__ import annotations

from typing import Any, Dict, Optional


class PinnFeedError(Exception):
    """Raised for non-2xx REST responses and rejected WebSocket upgrades.

    The API returns ``{"error": {"code", "message", ...}}``; see https://pinnfeed.io/docs/errors.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        retry_after_ms: Optional[int] = None,
        upgrade_url: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(f"[{status} {code}] {message}" if status or code else message)
        self.message = message
        self.status = status
        self.code = code
        self.retry_after_ms = retry_after_ms
        self.upgrade_url = upgrade_url
        self.body = body or {}

    @classmethod
    def from_body(cls, status: int, body: Any, fallback: str = "") -> "PinnFeedError":
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict):
            return cls(fallback or f"HTTP {status}", status=status, body=body if isinstance(body, dict) else None)
        return cls(
            str(err.get("message", fallback or f"HTTP {status}")),
            status=status,
            code=err.get("code"),
            retry_after_ms=err.get("retryAfterMs"),
            upgrade_url=err.get("upgrade_url"),
            body=body,
        )


class AuthenticationError(PinnFeedError):
    """401: missing_key / invalid_key."""


class PlanError(PinnFeedError):
    """403: the plan does not include this (e.g. plan_lacks_ws, plan_lacks_history, sport_not_in_plan)."""


class RateLimitError(PinnFeedError):
    """429: rate_limited, daily_quota or connection_limit."""


class NotFoundError(PinnFeedError):
    """404: not_found."""


def error_for(status: int, body: Any, fallback: str = "") -> PinnFeedError:
    base = PinnFeedError.from_body(status, body, fallback)
    klass = {401: AuthenticationError, 403: PlanError, 404: NotFoundError, 429: RateLimitError}.get(status, PinnFeedError)
    return klass(base.message, status=base.status, code=base.code, retry_after_ms=base.retry_after_ms,
                 upgrade_url=base.upgrade_url, body=base.body)
