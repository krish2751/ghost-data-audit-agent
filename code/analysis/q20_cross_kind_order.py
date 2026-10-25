"""Label-free test: within a group of cases that share reported_at, do the cases keep the same relative order in every
event-kind block? Uses only identifier-linked records (no sample answers).

For every pair of cases (A, B) in a group and every two (kind, event_type) blocks where both cases have an identifier-linked
event, compare the order of A and B in the two blocks (by event_time, then activity id). Chance agreement is 50%."""
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import loader
from fallback import Context, solve_all

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
base = solve_all(ctx, reqs, heuristics=False)
ACT_N = {a["activity_id"]: i for i, a in enumerate(ctx.act)}
groups = defaultdict(list)
for r in reqs:
    groups[r["reported_at"]].append(r["case_id"])
pos = defaultdict(dict)  # case -> {(kind, event_type): activity index}
owners = Counter()
for c, (res, _) in base.items():
    for d in res["resources"]:
        owners[d["resource_id"]] += 1
for c, (res, _) in base.items():
    for d in res["resources"]:
        rid = d["resource_id"]
        if owners[rid] != 1:
            continue
        for a in ctx.act_by_res.get(rid, []):
            if a["event_type"] in ("DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE",
                                   "CHECK_DATA_FLOW", "CHECK_RESTORE_ACCESS", "RETAIN_RECORD"):
                pos[c].setdefault((rid.rsplit("_", 1)[0], a["event_type"]), ACT_N[a["activity_id"]])
agree = Counter()
by_pair = Counter()
for ra, cs in groups.items():
    for a, b in combinations(sorted(cs), 2):
        common = sorted(set(pos[a]) & set(pos[b]))
        for k1, k2 in combinations(common, 2):
            same = (pos[a][k1] < pos[b][k1]) == (pos[a][k2] < pos[b][k2])
            agree["agree" if same else "disagree"] += 1
            by_pair[(k1, k2, same)] += 1
n = sum(agree.values())
print(f"cross-kind order comparisons: {n}; agree {agree['agree']} ({agree['agree'] / max(1, n):.1%}), disagree {agree['disagree']}")
kinds = sorted({(k1, k2) for k1, k2, _ in by_pair})
for k1, k2 in kinds:
    y, no = by_pair[(k1, k2, True)], by_pair[(k1, k2, False)]
    if y + no >= 5:
        print(f"   {k1[0]}/{k1[1]:20s} vs {k2[0]}/{k2[1]:20s} agree {y:4d} disagree {no:4d}")
