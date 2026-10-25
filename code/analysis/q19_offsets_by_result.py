"""Offsets (event_time - reported_at, minutes) of identifier-linked records' events, split by event kind and reported_result.

Shows the selection bias in learning one window per kind: records still linkable by an identifier are mostly the ones whose
anonymize/delete did not succeed, so their events need not follow the same timing as successful ones."""
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import loader
from fallback import Context, P, solve_all

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
by = {r["case_id"]: r for r in reqs}
base = solve_all(ctx, reqs, heuristics=False)
off = defaultdict(list)
for c, (res, _) in base.items():
    for d in res["resources"]:
        rid = d["resource_id"]
        kind = rid.rsplit("_", 1)[0]
        for a in ctx.act_by_res.get(rid, []):
            if a["event_type"] in ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "CHECK_DATA_FLOW", "CHECK_RESTORE_ACCESS"):
                m = (P(a["event_time"]) - P(by[c]["reported_at"])).total_seconds() / 60
                if abs(m) < 1000:
                    off[(kind, a["event_type"], a["reported_result"])].append(m)
print(f"{'kind':12s} {'event':22s} {'result':8s} {'n':>4s} {'min':>7s} {'median':>7s} {'max':>7s}")
for k in sorted(off):
    xs = off[k]
    print(f"{k[0]:12s} {k[1]:22s} {k[2]:8s} {len(xs):4d} {min(xs):7.0f} {median(xs):7.0f} {max(xs):7.0f}")

print("\nBy outcome at audit_at (the solver's own reading of the evidence, identifier-linked records only):")
out = defaultdict(list)
for c, (res, _) in base.items():
    for d in res["resources"]:
        rid = d["resource_id"]
        kind = rid.rsplit("_", 1)[0]
        for a in ctx.act_by_res.get(rid, []):
            if a["event_type"] in ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE"):
                m = (P(a["event_time"]) - P(by[c]["reported_at"])).total_seconds() / 60
                if abs(m) < 1000:
                    out[(kind, "clean" if not d["violation"] else "violation")].append(m)
print(f"{'kind':12s} {'outcome':10s} {'n':>4s} {'min':>7s} {'median':>7s} {'max':>7s}  before report")
for k in sorted(out):
    xs = out[k]
    print(f"{k[0]:12s} {k[1]:10s} {len(xs):4d} {min(xs):7.0f} {median(xs):7.0f} {max(xs):7.0f}  {sum(x < 0 for x in xs)}/{len(xs)}")
