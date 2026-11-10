"""Stream live moneyline moves for one sport.  Usage: python live_stream.py [sport]   (Builder plan or above)"""
import asyncio
import sys

from pinnfeed import PinnFeedStream


async def main(sport: str) -> None:
    async with PinnFeedStream(sports=[sport], markets=["moneyline"], main=True) as stream:
        async for msg in stream:
            if msg["type"] == "welcome":
                print(f"connected: plan={msg['plan']}")
            elif msg["type"] == "snapshot" and msg["final"]:
                print(f"snapshot: {len(stream.book.events)} events, {len(stream.book.markets)} markets")
            elif msg["type"] == "delta":
                for ch in msg["changes"]:
                    if ch["kind"] != "market" or ch["op"] != "upsert":
                        continue
                    m = ch["market"]
                    ev = stream.book.events.get(m["eventId"], {})
                    prices = "  ".join(f"{o['name']} {o.get('decimal')} (fair {o.get('fair', '-')})" for o in m["outcomes"])
                    print(f"{ev.get('home')} v {ev.get('away')}: {prices}")
            elif msg["type"] == "error":
                print(f"error {msg['code']}: {msg['message']}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "soccer"))
