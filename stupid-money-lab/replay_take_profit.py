"""Replay independent take-profit overlays on recorded paper paths."""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json

def replay(state, paths):
    trades = {t["id"]: t for t in state["studies"]
              if t["study"] == "github-portfolio-v3" and t.get("signalClass") == "fresh"}
    quotes = defaultdict(list)
    for path in paths:
        with open(path) as archive:
            for line in archive:
                row = json.loads(line)
                if row["scenario"] in trades:
                    quotes[row["scenario"]].append(row)

    for key, trade in trades.items():
        opened = datetime.fromisoformat(trade["openedAt"])
        closed = datetime.fromisoformat(trade["closedAt"]) if trade.get("closedAt") else None
        deadline = opened + timedelta(hours=1)
        legs = [(datetime.fromisoformat(leg["observedAt"]), leg["price"] * leg["quantity"])
                for leg in trade["legs"]]
        leverage = trade["leverage"]
        hits = {}
        timestamps = []
        for quote in sorted(quotes[key], key=lambda row: row["observedAt"]):
            at = datetime.fromisoformat(quote["observedAt"])
            if at < opened or (closed and at > closed):
                continue
            notional = sum(value for time, value in legs if time < at)
            if notional <= 0:
                continue
            timestamps.append(at)
            net = quote["netBeforeFunding"]
            for basis, denominator in (("notional", notional), ("margin", notional / leverage)):
                for target in (5, 10):
                    if net >= denominator * target / 100:
                        hits.setdefault(f"{basis}-{target}", dict(at=quote["observedAt"],
                            net=net, bookHash=quote["bookHash"], denominator=denominator,
                            withinHour=at <= deadline))
        yield dict(id=key, tier=trade.get("tier"), symbol=trade["symbol"],
                   quoteCount=len(timestamps), closed=bool(closed), hits=hits,
                   baseline=trade["netPnl"], stored=trade.get("milestones", {}),
                   candles=trade.get("candleAudit"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state")
    parser.add_argument("quotes", nargs="+")
    args = parser.parse_args()
    with open(args.state) as source:
        print(json.dumps(list(replay(json.load(source), args.quotes)), indent=2))
