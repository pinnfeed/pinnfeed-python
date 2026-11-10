import asyncio
import json

import pytest
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from pinnfeed import AuthenticationError, OddsBook, PinnFeedStream, PlanError

EV = {"id": 1, "sportId": 1, "sport": "soccer", "home": "A", "away": "B", "live": False}
MK = {"id": "m1", "eventId": 1, "type": "moneyline", "outcomes": [{"name": "home", "decimal": 2.0}]}


class FakeServer:
    """Minimal fake of wss://pinnfeed.io/v1/stream following src/gateway.js."""

    def __init__(self, script):
        self.script = script  # list of per-connection behaviours
        self.conn = 0
        self.received = []
        self.keys = []

    async def handler(self, ws):
        n = self.conn
        self.conn += 1
        self.keys.append(ws.request.headers.get("x-api-key"))
        await ws.send(json.dumps({"type": "welcome", "version": "v1", "plan": "builder", "limits": {"connections": 3}}))
        sub = json.loads(await ws.recv())
        self.received.append(sub)
        await ws.send(json.dumps({"type": "subscribed", "format": "normalized", "filters": {}}))
        await self.script[min(n, len(self.script) - 1)](ws, self)


async def first_conn(ws, srv):
    await ws.send(json.dumps({"type": "snapshot", "seq": 0, "part": 1, "parts": 1, "final": True, "events": [EV], "markets": [MK]}))
    await ws.send(json.dumps({"type": "ping", "ts": 1}))
    srv.received.append(json.loads(await ws.recv()))  # expect pong
    upd = dict(MK, outcomes=[{"name": "home", "decimal": 1.8}])
    await ws.send(json.dumps({"type": "delta", "seq": 1, "ts": 2, "changes": [{"kind": "market", "op": "upsert", "market": upd}]}))
    await ws.close(4008, "slow_consumer")


async def second_conn(ws, srv):
    await ws.send(json.dumps({"type": "delta", "seq": 2, "ts": 3, "changes": [{"kind": "event", "op": "remove", "id": 1}]}))
    await asyncio.sleep(5)


async def test_stream_snapshot_delta_heartbeat_reconnect():
    srv = FakeServer([first_conn, second_conn])
    async with serve(srv.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        stream = PinnFeedStream("ps_live_test", url=f"ws://127.0.0.1:{port}/v1/stream", sports=["soccer"],
                                markets="moneyline", main=True, initial_backoff=0.01)
        types = []
        async for msg in stream:
            types.append(msg["type"])
            if msg["type"] == "delta" and msg["seq"] == 1:
                assert stream.book.markets["m1"]["outcomes"][0]["decimal"] == 1.8
            if msg["type"] == "delta" and msg["seq"] == 2:
                break
        await stream.close()
    assert types == ["welcome", "subscribed", "snapshot", "delta", "welcome", "subscribed", "delta"]
    assert srv.received[0] == {"type": "subscribe", "sports": ["soccer"], "markets": ["moneyline"], "main": True}
    assert srv.received[1] == {"type": "pong", "ts": 1}
    assert srv.received[2]["type"] == "subscribe"  # resubscribed after reconnect
    assert srv.keys == ["ps_live_test", "ps_live_test"]
    assert stream.reconnects == 1
    assert stream.book.events == {} and stream.book.markets == {}


async def test_plan_lacks_ws_is_fatal():
    def reject(conn, request):
        body = json.dumps({"error": {"code": "plan_lacks_ws", "message": "REST only", "upgrade_url": "https://pinnfeed.io/start/builder"}})
        return Response(403, "plan_lacks_ws", Headers({"Content-Type": "application/json"}), body.encode())

    async with serve(lambda ws: None, "127.0.0.1", 0, process_request=reject) as server:
        port = server.sockets[0].getsockname()[1]
        stream = PinnFeedStream("ps_live_test", url=f"ws://127.0.0.1:{port}/v1/stream")
        with pytest.raises(PlanError) as ei:
            async for _ in stream:
                pass
    assert ei.value.code == "plan_lacks_ws"
    assert ei.value.upgrade_url == "https://pinnfeed.io/start/builder"


async def test_key_revoked_is_fatal():
    async def revoke(ws, srv):
        await ws.close(4001, "key_revoked")

    srv = FakeServer([revoke])
    async with serve(srv.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        stream = PinnFeedStream("ps_live_test", url=f"ws://127.0.0.1:{port}/v1/stream", initial_backoff=0.01)
        with pytest.raises(AuthenticationError):
            async for _ in stream:
                pass


async def test_idle_timeout_reconnects():
    async def silent(ws, srv):
        await asyncio.sleep(5)

    srv = FakeServer([silent])
    async with serve(srv.handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        stream = PinnFeedStream("ps_live_test", url=f"ws://127.0.0.1:{port}/v1/stream", idle_timeout=0.2,
                                initial_backoff=0.01)
        welcomes = 0
        async for msg in stream:
            if msg["type"] == "welcome":
                welcomes += 1
                if welcomes == 2:
                    break
        await stream.close()
    assert srv.conn >= 2


def test_book_multipart_snapshot():
    b = OddsBook()
    b.apply({"type": "snapshot", "seq": 5, "part": 1, "parts": 2, "final": False, "events": [EV], "markets": [MK]})
    assert not b.ready
    b.apply({"type": "snapshot", "seq": 5, "part": 2, "parts": 2, "final": True, "events": [dict(EV, id=2)], "markets": []})
    assert b.ready and set(b.events) == {1, 2} and b.markets_of(1)[0]["id"] == "m1"
