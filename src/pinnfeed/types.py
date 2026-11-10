"""Typed shapes of PinnFeed API objects (mirrors https://pinnfeed.io/openapi.json)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

MarketType = Literal["moneyline", "spread", "total", "team_total"]


class League(TypedDict, total=False):
    id: Optional[int]
    name: Optional[str]
    group: Optional[str]


class Outcome(TypedDict, total=False):
    name: str
    american: Optional[int]
    decimal: Optional[float]
    points: float
    participantId: int
    fair: float
    """No-vig decimal price, when computable."""
    fairProb: float
    """No-vig probability, when computable."""


class Market(TypedDict, total=False):
    id: str
    eventId: int
    key: str
    type: MarketType
    period: int
    side: Optional[str]
    line: Optional[float]
    alternate: bool
    main: bool
    live: bool
    maxStake: Optional[float]
    cutoffAt: Optional[str]
    margin: Optional[float]
    outcomes: List[Outcome]


class Score(TypedDict, total=False):
    home: Optional[float]
    away: Optional[float]


class Special(TypedDict, total=False):
    category: Optional[str]
    description: Optional[str]


class Participant(TypedDict, total=False):
    id: Optional[int]
    name: str


class Event(TypedDict, total=False):
    id: int
    sportId: int
    sport: str
    league: Optional[League]
    home: Optional[str]
    away: Optional[str]
    startTime: Optional[str]
    status: Optional[str]
    live: bool
    parentId: Optional[int]
    units: str
    special: Optional[Special]
    participants: List[Participant]
    score: Optional[Score]
    clock: Optional[int]
    markets: List[Market]
    """Included on /v1/odds and /v1/events/{id}."""


class Drop(TypedDict, total=False):
    eventId: int
    sport: str
    league: Optional[str]
    home: Optional[str]
    away: Optional[str]
    startTime: Optional[str]
    live: bool
    marketId: str
    market: str
    period: int
    line: Optional[float]
    outcome: str
    points: Optional[float]
    to: float
    dropPct: float
    movedAt: str
    # "from" is a Python keyword: read it as drop["from"].


class ClosingMarket(TypedDict, total=False):
    key: str
    type: str
    period: int
    line: Optional[float]
    main: bool
    margin: Optional[float]
    maxStake: Optional[float]
    outcomes: List[Dict[str, Any]]


class ClosingRecord(TypedDict, total=False):
    eventId: int
    sportId: int
    league: League
    home: Optional[str]
    away: Optional[str]
    startTime: str
    capturedAt: str
    market: ClosingMarket


class AccountLimits(TypedDict, total=False):
    ratePerSec: float
    perDay: Optional[int]
    wsConnections: int
    sports: List[int]
    delayedSeconds: int
    mainMarketsOnly: bool
    history: bool


class Account(TypedDict, total=False):
    plan: str
    key: Dict[str, Any]
    limits: AccountLimits
    usage: Dict[str, int]


class Sport(TypedDict, total=False):
    id: int
    slug: str
    inPlan: bool
    live: int
    prematch: int


class SportsResponse(TypedDict):
    sports: List[Sport]


class EventsPage(TypedDict, total=False):
    count: int
    offset: int
    limit: int
    events: List[Event]


class EventResponse(TypedDict):
    event: Event


class DropsResponse(TypedDict, total=False):
    minutes: int
    minPct: float
    count: int
    drops: List[Drop]


class ClosingEventResponse(TypedDict, total=False):
    eventId: int
    markets: List[ClosingRecord]


class ClosingDayResponse(TypedDict, total=False):
    date: str
    offset: int
    limit: int
    count: int
    closing: List[ClosingRecord]


Filter = Union[str, int, List[Union[str, int]], None]
"""A filter value: a single value, a list, or a comma-separated string."""

class RawFrame(TypedDict, total=False):
    """Pro/Enterprise ``format="raw"``: Pinnacle's own records, un-normalized, in a PinnFeed envelope.

    See https://pinnfeed.io/answers/pinnacle-odds-websocket-raw-frames
    """

    type: Literal["raw"]
    seq: int
    ts: int  # when PinnFeed sent the frame (ms since epoch)
    sportId: Optional[int]
    sport: Optional[str]
    channel: Literal["live", "prematch"]
    kind: Literal["matchup", "matchups", "markets", "snapshot"]
    action: Literal["upsert", "remove", "replace"]
    eventId: int
    part: int  # only on large ``markets`` lists sent in parts
    final: bool  # apply the list once the part with final=True arrives
    data: Any  # Pinnacle record(s), un-normalized


StreamMessage = Dict[str, Any]
"""A decoded WebSocket frame: welcome, subscribed, unsubscribed, snapshot, delta, ping, pong, error,
or (Pro, ``format="raw"``) a :class:`RawFrame`."""
