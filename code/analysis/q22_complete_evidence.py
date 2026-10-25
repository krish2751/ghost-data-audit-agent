"""Does every record of a COMPLETE case have a pre-audit observation of its own? (problem statement: a verification
step for a COMPLETE case must cite the evidence that proves the compliant state)

Label-free part: identifier-linked records of cases whose identifier-only solve is COMPLETE vs INCOMPLETE.
Sample part: for each sample answer step, is the cited file one that contains the record?"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import loader
from data.evidence_index import prefix_of
from fallback import Context, solve_all

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
by = {r["case_id"]: r for r in reqs}
base = solve_all(ctx, reqs, heuristics=False)


def own_obs(rid, audit_at):
    return sorted({o.file_id for o in ctx.ix.by_resource.get(rid, []) if o.captured_at <= audit_at})


print("== identifier-linked records by identifier-only status: own observation captured <= audit_at")
c = Counter()
for cid, (res, _) in base.items():
    if res["status"] not in ("COMPLETE", "INCOMPLETE"):
        continue
    for d in res["resources"]:
        kind = "account" if prefix_of(d["resource_id"]) == "account" else "other"
        c[(res["status"], kind, bool(own_obs(d["resource_id"], by[cid]["audit_at"])) or d["verify_evidence"] is None and False)] += 1
for k in sorted(c):
    print(" ", k, c[k])

print("\n== sample answers: does the cited file contain the record?")
gold = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(open(loader.DS / "sample_output.csv"))}
g = Counter()
for cid, (st, steps) in gold.items():
    for s in steps:
        if not s["evidence_id"] or s["evidence_id"] not in ctx.man:
            continue
        inside = s["evidence_id"] in {o.file_id for o in ctx.ix.by_resource.get(s["resource_id"], [])}
        g[(st, s["phase"], inside)] += 1
        if not inside:
            print(f"  not in cited file: {cid} {st} {s['operation']} {s['resource_id']} cites {s['evidence_id']}")
for k in sorted(g):
    print(" ", k, g[k])
print("\n== sample answer accounts with no observation at all, by status")
for cid, (st, steps) in sorted(gold.items()):
    for s in steps:
        if prefix_of(s["resource_id"]) == "account" and s["phase"] == "VERIFICATION" and not ctx.ix.by_resource.get(s["resource_id"]):
            print(f"  {cid} {st} {s['resource_id']} evidence_id={s['evidence_id']!r}")
