"""Async WebSocket client for wss://pinnfeed.io/v1/stream with reconnect, backoff and heartbeat.

Protocol (https://pinnfeed.io/docs/websocket):
  server -> welcome | subscribed | unsubscribed | snapshot | delta | ping | pong | error
  client -> subscribe | unsubscribe | ping | pong
The server pings every 20 s and drops clients that have not answered with a pong for 60 s;
you must send a subscribe within 30 s of connecting. This client does both for you.
WebSocket access starts at the Builder plan; Free/Hobby keys get HTTP 403 plan_lacks_ws.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import websockets
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .client import resolve_key
from .errors import AuthenticationError, PinnFeedError, error_for
from .types import Event, Filter, Market, StreamMessage
from ._version import __version__

log = logging.getLogger("pinnfeed.stream")

DEFAULT_WS_URL = "wss://pinnfeed.io/v1/stream"
# Close codes sent by the server.
CLOSE_KEY_REVOKED = 4001
CLOSE_NO_SUBSCRIPTION = 4002
CLOSE_SLOW_CONSUMER = 4008
_FATAL_STATUS = {401, 403}


class OddsBook:
    """In-memory book of events and markets built from ``snapshot`` and ``delta`` frames."""

    def __init__(self) -> None:
        self.events: Dict[int, Event] = {}
        self.markets: Dict[str, Market] = {}
        self.seq: Optional[int] = None
        self.ready = False

    def apply(self, msg: StreamMessage) -> None:
        t = msg.get("type")
        if t == "snapshot":
            if msg.get("part", 1) == 1:
                self.events.clear()
                self.markets.clear()
                self.ready = False
            for ev in msg.get("events", []):
                self.events[ev["id"]] = ev
            for m in msg.get("markets", []):
                self.markets[m["id"]] = m
            if msg.get("final", True):
                self.ready = True
            self.seq = msg.get("seq", self.seq)
        elif t == "delta":
            for ch in msg.get("changes", []):
                if ch.get("kind") == "event":
                    if ch.get("op") == "remove":
                        self.events.pop(ch["id"], None)
                        for mid in [k for k, m in self.markets.items() if m.get("eventId") == ch["id"]]:
                            del self.markets[mid]
                    else:
                        ev = ch["event"]
                        self.events[ev["id"]] = ev
                elif ch.get("kind") == "market":
                    if ch.get("op") == "remove":
                        self.markets.pop(ch["id"], None)
                    else:
                        m = ch["market"]
                        self.markets[m["id"]] = m
            self.seq = msg.get("seq", self.seq)

    def markets_of(self, event_id: int) -> List[Market]:
        return [m for m in self.markets.values() if m.get("eventId") == event_id]


class PinnFeedStream:
    """Reconnecting WebSocket stream.

    >>> async with PinnFeedStream(sports=["soccer"], markets=["moneyline"]) as stream:
    ...     async for msg in stream:
    ...         if msg["type"] == "delta":
    ...             print(msg["changes"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        url: str = DEFAULT_WS_URL,
        sports: Filter = None,
        leagues: Filter = None,
        events: Filter = None,
        markets: Filter = None,
        live: Union[bool, str, None] = None,
        main: Optional[bool] = None,
        specials: Optional[bool] = None,
        snapshot: bool = True,
        format: str = "normalized",
        reconnect: bool = True,
        initial_backoff: float = 0.5,
        max_backoff: float = 30.0,
        idle_timeout: float = 60.0,
        max_retries: Optional[int] = None,
        yield_heartbeats: bool = False,
    ) -> None:
        self.api_key = resolve_key(api_key)
        self.url = url
        self.subscription: Dict[str, Any] = {}
        self._set_subscription(sports=sports, leagues=leagues, events=events, markets=markets, live=live,
                               main=main, specials=specials, snapshot=snapshot, format=format)
        self.reconnect = reconnect
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.idle_timeout = idle_timeout
        self.max_retries = max_retries
        self.yield_heartbeats = yield_heartbeats
        self.book = OddsBook()
        self.welcome: Optional[StreamMessage] = None
        self.reconnects = 0
        self._ws: Optional[ClientConnection] = None
        self._closed = False

    def _set_subscription(self, **kw: Any) -> None:
        sub: Dict[str, Any] = {"type": "subscribe"}
        for k, v in kw.items():
            if v is None:
                continue
            if k in ("sports", "leagues", "events", "markets") and isinstance(v, (str, int)):
                v = [x.strip() if isinstance(x, str) else x for x in str(v).split(",")] if isinstance(v, str) else [v]
            sub[k] = list(v) if isinstance(v, tuple) else v
        if sub.get("format") == "normalized":
            del sub["format"]
        if sub.get("snapshot") is True:
            del sub["snapshot"]
        self.subscription = sub

    async def subscribe(self, **kw: Any) -> None:
        """Replace the subscription (same keyword args as the constructor) and send it now."""
        self._set_subscription(**kw)
        if self._ws is not None:
            await self._send(self.subscription)

    async def unsubscribe(self) -> None:
        await self._send({"type": "unsubscribe"})

    async def _send(self, obj: Dict[str, Any]) -> None:
        if self._ws is None:
            raise PinnFeedError("Not connected")
        await self._ws.send(json.dumps(obj))

    async def _connect(self) -> ClientConnection:
        headers = {"x-api-key": self.api_key}
        try:
            ws = await connect(self.url, additional_headers=headers, user_agent_header=f"pinnfeed-python/{__version__}",
                               max_size=None, open_timeout=15)
        except InvalidStatus as e:
            status = e.response.status_code
            try:
                body = json.loads(bytes(e.response.body or b"").decode() or "null")
            except ValueError:
                body = None
            raise error_for(status, body, f"WebSocket upgrade rejected ({status})") from None
        await ws.send(json.dumps(self.subscription))
        return ws

    def _backoff(self, attempt: int) -> float:
        base = min(self.max_backoff, self.initial_backoff * (2 ** attempt))
        return float(base / 2 + random.uniform(0, base / 2))

    async def __aiter__(self) -> AsyncIterator[StreamMessage]:
        attempt = 0
        while not self._closed:
            try:
                self._ws = await self._connect()
                if attempt:
                    self.reconnects += 1
                attempt = 0
                while True:
                    raw = await asyncio.wait_for(self._ws.recv(), timeout=self.idle_timeout)
                    msg: StreamMessage = json.loads(raw)
                    t = msg.get("type")
                    if t == "ping":
                        await self._send({"type": "pong", "ts": msg.get("ts")})
                        if not self.yield_heartbeats:
                            continue
                    elif t == "pong" and not self.yield_heartbeats:
                        continue
                    elif t == "welcome":
                        self.welcome = msg
                    self.book.apply(msg)
                    yield msg
            except PinnFeedError as e:
                if e.status in _FATAL_STATUS or not self.reconnect:
                    raise
                log.warning("pinnfeed: %s; reconnecting", e)
            except ConnectionClosed as e:
                code = e.rcvd.code if e.rcvd else None
                if self._closed:
                    return
                if code == CLOSE_KEY_REVOKED:
                    raise AuthenticationError("API key revoked", status=401, code="key_revoked") from None
                if not self.reconnect:
                    raise
                log.warning("pinnfeed: connection closed (%s); reconnecting", code)
            except (asyncio.TimeoutError, OSError, websockets.exceptions.InvalidHandshake) as e:
                if not self.reconnect:
                    raise
                log.warning("pinnfeed: %s; reconnecting", type(e).__name__)
            finally:
                if self._ws is not None:
                    await self._ws.close()
                    self._ws = None
            if self._closed:
                return
            if self.max_retries is not None and attempt >= self.max_retries:
                raise PinnFeedError(f"Gave up after {attempt} reconnect attempts")
            await asyncio.sleep(self._backoff(attempt))
            attempt += 1

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            await self._ws.close()

    async def __aenter__(self) -> "PinnFeedStream":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
