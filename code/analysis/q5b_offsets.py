"""Offsets (minutes) of each gold resource's activity events relative to requested_at / reported_at, per case."""
import sys
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
req, out = sample_cases(); act = rows("system_activity.csv"); by = {}
for a in act: by.setdefault(a["resource_id"], []).append(a)
P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
NOISE = {"INDEX_RECORD", "UPDATE_RECORD", "SEND_EMAIL", "REFRESH_CACHE", "CREATE_EXPORT"}
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; rep = P(r["reported_at"]); rq = P(r["requested_at"])
    print(f"\n{cid} {out[cid][0][:4]} requested={r['requested_at'][5:16]} reported={r['reported_at'][5:16]} ({r['reported_status'][:4]}) audit={r['audit_at'][5:16]}")
    for rid in sorted({s["resource_id"] for s in out[cid][1]}):
        evs = [a for a in by.get(rid, []) if a["event_type"] not in NOISE]
        txt = "; ".join(f"{a['activity_id'][9:]} {a['event_type'][:7]}/{a['reported_result'][:4]} rep{(P(a['event_time'])-rep).total_seconds()/60:+.0f}m rq{(P(a['event_time'])-rq).total_seconds()/3600:+.1f}h" for a in sorted(evs, key=lambda a: a['event_time']))
        print(f"   {rid:16} {txt}")
