"""REST clients (sync and async) for https://pinnfeed.io/v1."""
from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional, Union, cast

import httpx

from ._version import __version__
from .errors import PinnFeedError, error_for
from .types import (
    Account,
    ClosingDayResponse,
    ClosingEventResponse,
    DropsResponse,
    EventResponse,
    EventsPage,
    Filter,
    SportsResponse,
)

DEFAULT_BASE_URL = "https://pinnfeed.io"
USER_AGENT = f"pinnfeed-python/{__version__}"
Live = Union[bool, str, None]


def resolve_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("PINNFEED_API_KEY")
    if not key:
        raise PinnFeedError("No API key: pass api_key=... or set PINNFEED_API_KEY. Get one at https://pinnfeed.io/signup")
    return key


def _csv(v: Filter) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    return str(v)


def _flag(v: Live) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def filter_params(
    *,
    sport: Filter = None,
    league: Filter = None,
    event: Filter = None,
    market: Filter = None,
    live: Live = None,
    main: Optional[bool] = None,
    specials: Optional[bool] = None,
    q: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    **extra: Any,
) -> Dict[str, str]:
    """Build the shared query filters (lists become comma-separated, bools become "true"/"false")."""
    raw: Dict[str, Optional[str]] = {
        "sport": _csv(sport),
        "league": _csv(league),
        "event": _csv(event),
        "market": _csv(market),
        "live": _flag(live),
        "main": _flag(main),
        "specials": _flag(specials),
        "q": q,
        "limit": None if limit is None else str(limit),
        "offset": None if offset is None else str(offset),
    }
    for k, v in extra.items():
        raw[k] = _flag(v) if isinstance(v, bool) else _csv(v)
    return {k: v for k, v in raw.items() if v is not None}


def _headers(key: str) -> Dict[str, str]:
    return {"x-api-key": key, "accept": "application/json", "user-agent": USER_AGENT}


def _handle(resp: httpx.Response) -> Any:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code >= 400:
        raise error_for(resp.status_code, body, resp.reason_phrase)
    return body


class _Paths:
    @staticmethod
    def drops(minutes: Optional[int], min_pct: Optional[float], limit: Optional[int], filters: Mapping[str, Any]) -> Dict[str, str]:
        p = filter_params(**filters)
        if minutes is not None:
            p["minutes"] = str(minutes)
        if min_pct is not None:
            p["min_pct"] = str(min_pct)
        if limit is not None:
            p["limit"] = str(limit)
        return p


class PinnFeed:
    """Synchronous REST client.

    >>> pf = PinnFeed()              # reads PINNFEED_API_KEY
    >>> pf.odds(sport="soccer", market="moneyline", main=True, limit=10)
    """

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 15.0, http_client: Optional[httpx.Client] = None) -> None:
        self.api_key = resolve_key(api_key)
        self.base_url = base_url.rstrip("/")
        self._http = http_client or httpx.Client(timeout=timeout)
        self.last_headers: Mapping[str, str] = {}

    def _get(self, path: str, params: Optional[Mapping[str, str]] = None) -> Any:
        resp = self._http.get(self.base_url + path, params=params, headers=_headers(self.api_key))
        self.last_headers = resp.headers
        return _handle(resp)

    def account(self) -> Account:
        """Plan, limits and today's usage of this key (``GET /v1/account``)."""
        return cast(Account, self._get("/v1/account"))

    def sports(self) -> SportsResponse:
        """Sports with live/prematch event counts and whether each is in your plan."""
        return cast(SportsResponse, self._get("/v1/sports"))

    def events(self, **filters: Any) -> EventsPage:
        """Events without markets. Filters: sport, league, event, market, live, main, specials, q, limit, offset."""
        return cast(EventsPage, self._get("/v1/events", filter_params(**filters)))

    def odds(self, sport: Filter, *, with_markets: Optional[bool] = None, **filters: Any) -> EventsPage:
        """Events with their markets (``GET /v1/odds``). ``sport`` is required by the API."""
        p = filter_params(sport=sport, **filters)
        if with_markets is not None:
            p["withMarkets"] = _flag(with_markets) or "false"
        return cast(EventsPage, self._get("/v1/odds", p))

    def event(self, event_id: int, **filters: Any) -> EventResponse:
        """One event with its markets (``GET /v1/events/{id}``)."""
        return cast(EventResponse, self._get(f"/v1/events/{int(event_id)}", filter_params(**filters)))

    def drops(self, *, minutes: Optional[int] = None, min_pct: Optional[float] = None,
              limit: Optional[int] = None, **filters: Any) -> DropsResponse:
        """Recent price drops (``GET /v1/drops``). minutes 1-60 (default 15), min_pct default 3, limit max 200."""
        return cast(DropsResponse, self._get("/v1/drops", _Paths.drops(minutes, min_pct, limit, filters)))

    def closing(self, event_id: int) -> ClosingEventResponse:
        """Closing lines captured for one event (Builder and above)."""
        return cast(ClosingEventResponse, self._get(f"/v1/closing/{int(event_id)}"))

    def closing_day(self, date: Optional[str] = None, **filters: Any) -> ClosingDayResponse:
        """Closing lines for a UTC day ``YYYY-MM-DD`` (Builder and above). Filters: sport, main, limit, offset."""
        p = filter_params(**filters)
        if date:
            p["date"] = date
        return cast(ClosingDayResponse, self._get("/v1/closing", p))

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PinnFeed":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncPinnFeed:
    """Asynchronous REST client with the same methods as :class:`PinnFeed`."""

    def __init__(self, api_key: Optional[str] = None, *, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 15.0, http_client: Optional[httpx.AsyncClient] = None) -> None:
        self.api_key = resolve_key(api_key)
        self.base_url = base_url.rstrip("/")
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self.last_headers: Mapping[str, str] = {}

    async def _get(self, path: str, params: Optional[Mapping[str, str]] = None) -> Any:
        resp = await self._http.get(self.base_url + path, params=params, headers=_headers(self.api_key))
        self.last_headers = resp.headers
        return _handle(resp)

    async def account(self) -> Account:
        return cast(Account, await self._get("/v1/account"))

    async def sports(self) -> SportsResponse:
        return cast(SportsResponse, await self._get("/v1/sports"))

    async def events(self, **filters: Any) -> EventsPage:
        return cast(EventsPage, await self._get("/v1/events", filter_params(**filters)))

    async def odds(self, sport: Filter, *, with_markets: Optional[bool] = None, **filters: Any) -> EventsPage:
        p = filter_params(sport=sport, **filters)
        if with_markets is not None:
            p["withMarkets"] = _flag(with_markets) or "false"
        return cast(EventsPage, await self._get("/v1/odds", p))

    async def event(self, event_id: int, **filters: Any) -> EventResponse:
        return cast(EventResponse, await self._get(f"/v1/events/{int(event_id)}", filter_params(**filters)))

    async def drops(self, *, minutes: Optional[int] = None, min_pct: Optional[float] = None,
                    limit: Optional[int] = None, **filters: Any) -> DropsResponse:
        return cast(DropsResponse, await self._get("/v1/drops", _Paths.drops(minutes, min_pct, limit, filters)))

    async def closing(self, event_id: int) -> ClosingEventResponse:
        return cast(ClosingEventResponse, await self._get(f"/v1/closing/{int(event_id)}"))

    async def closing_day(self, date: Optional[str] = None, **filters: Any) -> ClosingDayResponse:
        p = filter_params(**filters)
        if date:
            p["date"] = date
        return cast(ClosingDayResponse, await self._get("/v1/closing", p))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncPinnFeed":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
