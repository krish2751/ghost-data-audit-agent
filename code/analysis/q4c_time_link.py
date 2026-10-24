"""Hypothesis: a subject's deleted account resource can be found from DELETE_RECORD activity near reported_at/requested_at."""
import sys
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
req, out = sample_cases(); act = rows("system_activity.csv")
P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
dels = [a for a in act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
print("case  status  gold_account  act_time  (act - requested)h  (act - reported)h  | #DELETE_account events in [requested,reported+1h]")
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; st, steps = out[cid]
    accs = sorted({s["resource_id"] for s in steps if s["system_id"] == "account_service"})
    for acc in accs:
        ev = [a for a in act if a["resource_id"] == acc and a["event_type"] == "DELETE_RECORD"]
        t = ev[0]["event_time"] if ev else None
        win = [a["resource_id"] for a in dels if r["requested_at"] <= a["event_time"] <= (P(r["reported_at"]).replace(hour=P(r["reported_at"]).hour) .isoformat() + "Z") or False]
        lo, hi = P(r["requested_at"]), P(r["reported_at"])
        n = sum(lo <= P(a["event_time"]) <= hi for a in dels)
        d1 = f"{(P(t)-lo).total_seconds()/3600:6.1f}" if t else "  n/a"
        d2 = f"{(P(t)-hi).total_seconds()/3600:6.1f}" if t else "  n/a"
        print(f"{cid:8} {st[:4]} {acc:13} {t or '-':21} {d1} {d2} | {n} {r['reported_status']}")
