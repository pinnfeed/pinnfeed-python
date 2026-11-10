"""Compare another bookmaker's price with Pinnacle's no-vig fair price.

PinnFeed gives you Pinnacle's prices plus the no-vig `fair` decimal and `fairProb`.
Feed in the price your own bookmaker offers and get the expected value per unit staked.

  python value_vs_fair.py <event_id> <outcome_name> <your_decimal_price> [market_type]
  e.g. python value_vs_fair.py 1612345678 home 2.25 moneyline
"""
import sys

from pinnfeed import PinnFeed


def main(event_id: int, outcome: str, price: float, market_type: str = "moneyline") -> None:
    ev = PinnFeed().event(event_id, market=market_type, main=True)["event"]
    for m in ev.get("markets", []):
        for o in m["outcomes"]:
            if o["name"] != outcome:
                continue
            prob = o.get("fairProb")
            if prob is None:
                print("No fair price computable for this market right now.")
                return
            ev_pct = (price * prob - 1) * 100
            print(f"{ev.get('home')} v {ev.get('away')} {m['type']} {outcome}")
            print(f"  Pinnacle {o.get('decimal')}  fair {o.get('fair')}  ({prob:.1%})")
            print(f"  your price {price}: EV {ev_pct:+.2f}% per unit")
            return
    print("Outcome not found; names in this market:", [o["name"] for m in ev.get("markets", []) for o in m["outcomes"]])


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]), a[1], float(a[2]), a[3] if len(a) > 3 else "moneyline")
