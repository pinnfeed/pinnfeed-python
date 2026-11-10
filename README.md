# pinnfeed-python

[![CI](https://github.com/pinnfeed/pinnfeed-python/actions/workflows/ci.yml/badge.svg)](https://github.com/pinnfeed/pinnfeed-python/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Official Python client for **[PinnFeed](https://pinnfeed.io)**: real-time Pinnacle odds over REST and WebSocket, with normalized markets, no-vig fair prices, price drops and closing-line history.

- Typed REST client (sync `PinnFeed` and async `AsyncPinnFeed`) for every `/v1` endpoint
- Async WebSocket client (`PinnFeedStream`) with automatic reconnect, exponential backoff with jitter, heartbeat (answers server pings, detects dead connections) and re-subscribe
- `OddsBook`: an in-memory book kept up to date from `snapshot` + `delta` frames
- Typed `TypedDict` models (`py.typed`), Python 3.9+

## Install

The package is not on PyPI yet. Install it from GitHub:

```bash
pip install git+https://github.com/pinnfeed/pinnfeed-python
```

## Get an API key

Create a key at **[pinnfeed.io/signup](https://pinnfeed.io/signup)** and export it:

```bash
export PINNFEED_API_KEY=ps_live_...
```

The Free plan is REST only with a 30-second delay; the WebSocket starts at Builder. Plans and limits: [pinnfeed.io/pricing](https://pinnfeed.io/pricing). As of 9 Nov 2026, PinnFeed Builder (€99/mo or €990/yr, VAT incl.) was the lowest published live + prematch Pinnacle WebSocket on monthly or annual billing ([details and sources](https://pinnfeed.io/cheapest-pinnacle-odds-websocket)).

## REST quickstart

```python
from pinnfeed import PinnFeed

pf = PinnFeed()  # reads PINNFEED_API_KEY

print(pf.account()["plan"])
for s in pf.sports()["sports"]:
    print(s["slug"], s["live"], s["prematch"], "in plan" if s["inPlan"] else "")

page = pf.odds("soccer", market="moneyline", main=True, limit=5)
for ev in page["events"]:
    for m in ev.get("markets", []):
        print(ev["home"], "v", ev["away"], [(o["name"], o.get("decimal"), o.get("fair")) for o in m["outcomes"]])
```

| Method | Endpoint | Notes |
| --- | --- | --- |
| `account()` | `GET /v1/account` | plan, limits, today's usage |
| `sports()` | `GET /v1/sports` | live/prematch counts, `inPlan` |
| `events(**filters)` | `GET /v1/events` | events without markets |
| `odds(sport, with_markets=None, **filters)` | `GET /v1/odds` | events with markets; `sport` required |
| `event(id, **filters)` | `GET /v1/events/{id}` | one event with markets |
| `drops(minutes=, min_pct=, limit=, **filters)` | `GET /v1/drops` | recent price drops (window 1–60 min) |
| `closing(event_id)` | `GET /v1/closing/{eventId}` | closing lines, Builder+ |
| `closing_day(date, **filters)` | `GET /v1/closing` | closing lines for a UTC day, Builder+ |

Filters (all optional, lists or comma-separated strings): `sport`, `league`, `event`, `market` (`moneyline`, `spread`, `total`, `team_total`), `live` (`True`/`False`/`"live"`/`"prematch"`), `main`, `specials`, `q`, `limit`, `offset`. The response headers of the last call are on `pf.last_headers` (e.g. `X-Plan`, `X-Data-Delay-Seconds`).

`AsyncPinnFeed` has the same methods as coroutines.

## WebSocket quickstart

```python
import asyncio
from pinnfeed import PinnFeedStream

async def main():
    async with PinnFeedStream(sports=["soccer", "tennis"], markets=["moneyline"], main=True) as stream:
        async for msg in stream:
            if msg["type"] == "snapshot" and msg["final"]:
                print("book ready:", len(stream.book.events), "events")
            elif msg["type"] == "delta":
                for ch in msg["changes"]:
                    if ch["kind"] == "market" and ch["op"] == "upsert":
                        m = ch["market"]
                        print(m["eventId"], m["type"], [(o["name"], o.get("decimal")) for o in m["outcomes"]])
            elif msg["type"] == "error":
                print("server error:", msg["code"], msg["message"])

asyncio.run(main())
```

What the client handles for you (protocol: [pinnfeed.io/docs/websocket](https://pinnfeed.io/docs/websocket)):

- Sends your `subscribe` right after connecting (the server closes with `4002` if none arrives within 30 s).
- Replies `pong` to every server `ping` (sent every 20 s; the server drops clients silent for 60 s) and reconnects if nothing arrives for `idle_timeout` seconds (default 60).
- Reconnects with exponential backoff + jitter (`initial_backoff`, `max_backoff`, `max_retries`) on network errors, `4008 slow_consumer` and `429 connection_limit`, then re-subscribes and receives a fresh snapshot.
- Raises `AuthenticationError` on `401` or close code `4001 key_revoked`, and `PlanError` on `403 plan_lacks_ws` (Free/Hobby keys), with `upgrade_url` set.

Change filters on the fly with `await stream.subscribe(sports=["basketball"])`. Pass `format="raw"` for upstream frames (Pro and Enterprise).

## Errors

All errors subclass `PinnFeedError` and carry `status`, `code`, `message`, `retry_after_ms` and `upgrade_url` from the API's `{"error": {...}}` body: `AuthenticationError` (401), `PlanError` (403), `NotFoundError` (404), `RateLimitError` (429). Codes are listed at [pinnfeed.io/docs/errors](https://pinnfeed.io/docs/errors).

## Examples

- [`examples/live_stream.py`](examples/live_stream.py): stream moneyline moves for a sport
- [`examples/dropping_odds_alert.py`](examples/dropping_odds_alert.py): alert on drops via REST `/v1/drops` (any plan) or detect them yourself on the WebSocket
- [`examples/value_vs_fair.py`](examples/value_vs_fair.py): compare another bookmaker's price with Pinnacle's no-vig fair price
- [`examples/closing_line_value.py`](examples/closing_line_value.py): closing-line value of a bet you placed (Builder+)

PinnFeed carries one bookmaker (Pinnacle), so there is no cross-bookmaker arbitrage example; `value_vs_fair.py` shows the supported use: comparing your own book's prices with Pinnacle's no-vig line.

## Development

```bash
pip install -e ".[dev]"
mypy && pytest -q
```

Tests run against a local fake server; no API key needed.

## Links

[Docs](https://pinnfeed.io/docs) · [OpenAPI](https://pinnfeed.io/openapi.json) · [Pricing](https://pinnfeed.io/pricing) · [Node/TypeScript SDK](https://github.com/pinnfeed/pinnfeed-node) · support@pinnfeed.io

MIT licensed. PinnFeed is not affiliated with Pinnacle.
