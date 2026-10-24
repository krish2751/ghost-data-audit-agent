"""Where does the 120-minute window come from? Offsets of the account DELETE_RECORD event vs reported_at / requested_at,
measured only on requests whose account is tied to the user by an identifier (no timing involved in the link)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime
from statistics import median
from fallback import Context, _matcher, P
from data import loader
from data.evidence_index import prefix_of

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests(sample=False)
del_by_res = {}
for a in ctx.act:
    if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service":
        del_by_res.setdefault(a["resource_id"], []).append(a)
claims = ctx.claims()
off_rep, off_req, n = [], [], 0
for r in reqs:
    uids = ctx.ids.resolve_email(r["email"])
    if not uids: continue
    uid = uids[0]
    mine = [rid for rid, us in claims.items() if us == {uid} and prefix_of(rid) == "account" and rid in del_by_res]
    for rid in mine:
        n += 1
        for a in del_by_res[rid]:
            t = P(a["event_time"])
            off_rep.append((t - P(r["reported_at"])).total_seconds() / 60)
            off_req.append((t - P(r["requested_at"])).total_seconds() / 3600)
off_rep.sort(); off_req.sort()
q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
print(f"identifier-linked (request, account) pairs with a DELETE_RECORD: {n}; events {len(off_rep)}")
print("event_time - reported_at, minutes: min %.1f  p05 %.1f  median %.1f  p95 %.1f  max %.1f" % (off_rep[0], q(off_rep, .05), median(off_rep), q(off_rep, .95), off_rep[-1]))
print("event_time - requested_at, hours : min %.1f  p05 %.1f  median %.1f  p95 %.1f  max %.1f" % (off_req[0], q(off_req, .05), median(off_req), q(off_req, .95), off_req[-1]))
bins = [(-1e9, -240), (-240, -120), (-120, -60), (-60, 0), (0, 60), (60, 120), (120, 240), (240, 1e9)]
for lo, hi in bins:
    print(f"   {lo:>8.0f} .. {hi:<8.0f} min: {sum(lo <= x < hi for x in off_rep)}")

inl = [x for x in off_rep if abs(x) < 1000]
print(f"\ninliers (|offset| < 1000 min): {len(inl)}; range {min(inl):.1f} .. {max(inl):.1f}; abs p98 {sorted(abs(x) for x in inl)[int(.98*len(inl))]:.1f}")
print("outliers (minutes):", [round(x) for x in off_rep if abs(x) >= 1000])
