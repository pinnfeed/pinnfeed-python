"""Closing-line value (CLV) of a bet you placed, using Pinnacle's closing line (Builder plan or above).

  python closing_line_value.py <event_id> <market_key> <outcome_name> <your_decimal_price>
Run without the last three arguments to list the captured market keys and outcomes.
"""
import sys

from pinnfeed import PinnFeed


def main() -> None:
    a = sys.argv[1:]
    rows = PinnFeed().closing(int(a[0]))["markets"]
    if len(a) < 4:
        for r in rows:
            print(r["market"]["key"], [o.get("name") for o in r["market"].get("outcomes", [])])
        return
    key, name, price = a[1], a[2], float(a[3])
    for r in rows:
        if r["market"]["key"] != key:
            continue
        for o in r["market"].get("outcomes", []):
            if o.get("name") == name:
                close = o.get("fair") or o.get("decimal")
                print(f"closing {close} (captured {r['capturedAt']}); your price {price}: CLV {(price / close - 1) * 100:+.2f}%")
                return
    print("market/outcome not found")


if __name__ == "__main__":
    main()
