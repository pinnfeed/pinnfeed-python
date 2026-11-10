"""Alert when Pinnacle prices drop sharply.

  python dropping_odds_alert.py rest    # polls GET /v1/drops (works on every plan)
  python dropping_odds_alert.py ws      # detects drops yourself on the WebSocket (Builder+)
"""
import asyncio
import sys
import time
from typing import Dict, Tuple

from pinnfeed import PinnFeed, PinnFeedStream

MIN_PCT = 5.0


def rest_loop() -> None:
    pf = PinnFeed()
    seen = set()
    while True:
        res = pf.drops(minutes=10, min_pct=MIN_PCT, limit=50)
        for d in res["drops"]:
            key = (d["marketId"], d["outcome"], d["movedAt"])
            if key in seen:
                continue
            seen.add(key)
            print(f"{d['home']} v {d['away']} [{d['market']}] {d['outcome']}: {d['from']} -> {d['to']} (-{d['dropPct']:.1f}%)")
        time.sleep(30)


async def ws_loop() -> None:
    last: Dict[Tuple[str, str], float] = {}
    async with PinnFeedStream(markets=["moneyline", "total", "spread"], main=True) as stream:
        async for msg in stream:
            if msg["type"] == "snapshot":
                for m in msg["markets"]:
                    for o in m["outcomes"]:
                        if o.get("decimal"):
                            last[(m["id"], o["name"])] = o["decimal"]
            elif msg["type"] == "delta":
                for ch in msg["changes"]:
                    if ch["kind"] != "market" or ch["op"] != "upsert":
                        continue
                    m = ch["market"]
                    for o in m["outcomes"]:
                        new, k = o.get("decimal"), (m["id"], o["name"])
                        old = last.get(k)
                        if new and old and new < old:
                            pct = (old - new) / old * 100
                            if pct >= MIN_PCT:
                                ev = stream.book.events.get(m["eventId"], {})
                                print(f"{ev.get('home')} v {ev.get('away')} [{m['type']}] {o['name']}: {old} -> {new} (-{pct:.1f}%)")
                        if new:
                            last[k] = new


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ws":
        asyncio.run(ws_loop())
    else:
        rest_loop()
