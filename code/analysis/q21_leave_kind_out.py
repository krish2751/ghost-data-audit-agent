"""Label-free check of joint.assign_unlinked: for each record kind, hide its identifier links, learn the outcome model
from the other kinds only, and recover the hidden records from activity. Truth = the hidden identifier links."""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joint
from data import loader
from data.evidence_index import prefix_of
from fallback import Context, solve_all

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
by = {r["case_id"]: r for r in reqs}
base = solve_all(ctx, reqs, heuristics=False)
uid_of = {c: res["uid"] for c, (res, _) in base.items() if "uid" in res and res["status"] != "NOT_APPLICABLE"}
KINDS = [("backup", "BLOCK_RESTORE"), ("data_flow", "DISABLE_DATA_FLOW"), ("tombstone", "REDACT_RECORD"), ("support", "REDACT_RECORD"),
         ("search", "DELETE_RECORD"), ("export", "DELETE_RECORD"), ("analytics", "ANONYMIZE_RECORD")]
total = Counter()
for kind, et in KINDS:
    truth, known = {}, []
    for c, (res, _) in base.items():
        for d in res["resources"]:
            rid = d["resource_id"]
            if prefix_of(rid) == kind and any(a["event_type"] == et for a in ctx.act_by_res.get(rid, [])):
                truth.setdefault(c, {})[rid] = "violation" if d["violation"] else "clean"
            elif prefix_of(rid) != kind:
                known.append((c, rid))
    claims = {k: set(v) for k, v in ctx.claims().items()}
    for c, rs in truth.items():
        for rid in rs:
            claims.get(rid, set()).discard(uid_of.get(c))
    model = joint.outcome_model(ctx, base, by, 0.05, skip_kind=kind)
    got = joint.assign_unlinked(ctx, reqs, uid_of, known, kind, et, model, claims)
    res = Counter()
    for c, rs in truth.items():
        g = got.get(c)
        k = "unresolved" if g is None else "correct" if g[0] in rs else "wrong"
        res[(k, sorted(set(rs.values()))[0] if len(set(rs.values())) == 1 else "mixed")] += 1
    extra = sum(1 for c in got if c not in truth)
    for k, n in res.items():
        total[k[0]] += n
    print(f"{kind:10s} {et:18s} hidden cases {len(truth):4d}  " + "  ".join(f"{k[0]}/{k[1]} {n}" for k, n in sorted(res.items())) + f"  assigned to cases with no hidden record: {extra}")
    total["assigned to cases with no hidden record"] += extra
print("total:", dict(total))
