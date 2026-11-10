import json

import httpx
import pytest

from pinnfeed import AsyncPinnFeed, PinnFeed, PlanError, RateLimitError, filter_params
from pinnfeed.errors import AuthenticationError, PinnFeedError

EVENT = {"id": 1, "sportId": 1, "sport": "soccer", "home": "A", "away": "B", "live": False, "markets": [
    {"id": "1:ml:0", "eventId": 1, "type": "moneyline", "period": 0, "main": True, "live": False,
     "outcomes": [{"name": "home", "decimal": 2.1, "fair": 2.16, "fairProb": 0.463}]}]}


def make(handler):
    seen = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    return PinnFeed("ps_live_test", http_client=httpx.Client(transport=httpx.MockTransport(wrapped))), seen


def test_requires_key(monkeypatch):
    monkeypatch.delenv("PINNFEED_API_KEY", raising=False)
    with pytest.raises(PinnFeedError):
        PinnFeed()


def test_env_key(monkeypatch):
    monkeypatch.setenv("PINNFEED_API_KEY", "ps_live_env")
    assert PinnFeed().api_key == "ps_live_env"


def test_filter_params():
    p = filter_params(sport=["soccer", 3], market="moneyline,total", live=True, main=False, limit=5, q=None)
    assert p == {"sport": "soccer,3", "market": "moneyline,total", "live": "true", "main": "false", "limit": "5"}


def test_odds_sends_key_and_filters():
    pf, seen = make(lambda r: httpx.Response(200, json={"count": 1, "offset": 0, "limit": 200, "events": [EVENT]},
                                              headers={"X-Plan": "builder"}))
    res = pf.odds("soccer", market=["moneyline"], main=True, with_markets=True)
    req = seen[0]
    assert req.url.path == "/v1/odds"
    assert req.headers["x-api-key"] == "ps_live_test"
    assert dict(req.url.params) == {"sport": "soccer", "market": "moneyline", "main": "true", "withMarkets": "true"}
    assert res["events"][0]["markets"][0]["outcomes"][0]["fair"] == 2.16
    assert pf.last_headers["x-plan"] == "builder"


@pytest.mark.parametrize("call,path,params", [
    (lambda pf: pf.account(), "/v1/account", {}),
    (lambda pf: pf.sports(), "/v1/sports", {}),
    (lambda pf: pf.events(sport="tennis", live="prematch", offset=10), "/v1/events", {"sport": "tennis", "live": "prematch", "offset": "10"}),
    (lambda pf: pf.event(42, market="total"), "/v1/events/42", {"market": "total"}),
    (lambda pf: pf.drops(minutes=5, min_pct=4.5, limit=20, sport="soccer"), "/v1/drops", {"minutes": "5", "min_pct": "4.5", "limit": "20", "sport": "soccer"}),
    (lambda pf: pf.closing(7), "/v1/closing/7", {}),
    (lambda pf: pf.closing_day("2026-11-09", sport="soccer", main=True), "/v1/closing", {"date": "2026-11-09", "sport": "soccer", "main": "true"}),
])
def test_paths(call, path, params):
    pf, seen = make(lambda r: httpx.Response(200, json={}))
    call(pf)
    assert seen[0].url.path == path
    assert dict(seen[0].url.params) == params


@pytest.mark.parametrize("status,code,klass", [
    (401, "invalid_key", AuthenticationError),
    (403, "plan_lacks_history", PlanError),
    (429, "rate_limited", RateLimitError),
])
def test_errors(status, code, klass):
    body = {"error": {"code": code, "message": "nope", "retryAfterMs": 500, "upgrade_url": "https://pinnfeed.io/start/builder"}}
    pf, _ = make(lambda r: httpx.Response(status, json=body))
    with pytest.raises(klass) as ei:
        pf.closing(1)
    assert ei.value.code == code and ei.value.status == status
    assert ei.value.upgrade_url == "https://pinnfeed.io/start/builder"
    if status == 429:
        assert ei.value.retry_after_ms == 500


async def test_async_client():
    async def handler(req):
        return httpx.Response(200, json={"sports": [{"id": 1, "slug": "soccer", "inPlan": True, "live": 3, "prematch": 9}]})
    pf = AsyncPinnFeed("ps_live_test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    res = await pf.sports()
    assert res["sports"][0]["slug"] == "soccer"
    await pf.aclose()
