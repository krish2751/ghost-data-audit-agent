"""Numbers behind every tunable rule left in the solver (cited in data_findings.md).

1. joint compat: (reported_status, account DELETE result) pairs among identifier-linked cases, and the min_share range that gives the same set.
2. window constants (MAD_K, PAD_SHARE): label-free hold-out recall/precision for alternatives (truth = identifier-linked accounts).
3. LATE_OK: retained records whose only pre-audit existence is an inner snapshot time inside a later-captured file.
4. category overrides in data/states.py: how often each fires, and agreement with the treatment implied by sample answers.
5. verify-evidence anchor and the latest-file / worst-reading choice in fallback._decide: how often they matter.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import fallback
import joint
from common import sample_cases
from data import loader
from data.evidence_index import prefix_of
from data.states import category, reading
from fallback import Context, LATE_OK, solve_all
from schema import PREFIX_INFO, TREATMENT

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
by_case = {r["case_id"]: r for r in reqs}
base = solve_all(ctx, reqs, heuristics=False)

print("== 1. (reported_status, account DELETE result) among identifier-linked cases")
pair = Counter()
for c, (res, _) in base.items():
    for d in res["resources"]:
        if d["resource_id"].startswith("account"):
            ev = [a for a in ctx.act_by_res.get(d["resource_id"], []) if a["event_type"] == "DELETE_RECORD"]
            if ev:
                pair[(by_case[c]["reported_status"], ev[0]["reported_result"])] += 1
tot = Counter()
for (st, _), n in pair.items():
    tot[st] += n
for k, n in sorted(pair.items()):
    print(f"   {k[0]:20s} {k[1]:8s} {n:4d}  share {n / tot[k[0]]:.1%}")
shares = sorted(n / tot[k[0]] for k, n in pair.items())
gap = max(range(len(shares) - 1), key=lambda i: shares[i + 1] - shares[i])
print(f"   any min_share in ({shares[gap]:.1%}, {shares[gap + 1]:.1%}] keeps the same compatible set")

print("\n== 2. window constants on the label-free hold-out (5 folds grouped by user)")
del_res = {a["resource_id"] for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"}
truth, uid_of = {}, {}
for r in reqs:
    res = base[r["case_id"]][0]
    if "uid" in res:
        uid_of[r["case_id"]] = res["uid"]
        accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account") and d["resource_id"] in del_res]
        if len(accs) == 1:
            truth[r["case_id"]] = accs[0]
users = sorted({uid_of[c] for c in truth}); fold = {u: i % 5 for i, u in enumerate(users)}
for mk, ps in [(5, 0.1), (10, 0.0), (10, 0.05), (10, 0.1), (10, 0.25), (20, 0.1), (1e9, 0.1)]:
    joint.MAD_K, joint.PAD_SHARE = mk, ps
    c = Counter()
    for k in range(5):
        hide = frozenset(x for x in truth if fold[uid_of[x]] == k)
        out = joint.compute(ctx, hide=hide, base=base, analytics=False)[0]["account"]
        for x in hide:
            g = out.get(x)
            c["unresolved" if g is None else "correct" if g[0] == truth[x] else "wrong"] += 1
    print(f"   MAD_K={mk:<5g} PAD_SHARE={ps:<4} correct {c['correct']:3d} wrong {c['wrong']:2d} unresolved {c['unresolved']:3d}")
joint.MAD_K, joint.PAD_SHARE = 10, 0.1

print("\n== 3. LATE_OK (retained kinds verified from an inner snapshot time inside a later-captured file)")
_, gold = sample_cases()
late_gold = Counter()
for cid, (st, steps) in gold.items():
    a = by_case[cid]["audit_at"]
    for s in steps:
        rid = s["resource_id"]
        if prefix_of(rid) in ("audit_record", "legal_hold", "tombstone", "backup"):
            obs = ctx.ix.by_resource.get(rid, [])
            k = ("pre-audit file" if any(o.captured_at <= a for o in obs) else
                 "only later file, inner time <= audit_at" if any(o.snap_time <= a for o in obs) else "no observation")
            late_gold[(prefix_of(rid), s["operation"], k)] += 1
for k, n in sorted(late_gold.items()):
    print(f"   gold {k[0]:13s} {k[1]:24s} {k[2]:40s} {n}")
full = solve_all(ctx, reqs)
n_late = sum(1 for c, (res, _) in full.items() for d in res["resources"] if prefix_of(d["resource_id"]) in LATE_OK and d["verify_evidence"] and
             not any(o.captured_at <= by_case[c]["audit_at"] for o in ctx.ix.by_resource.get(d["resource_id"], [])))
print(f"   records in the 550 outputs that exist only through LATE_OK: {n_late}")

print("\n== 4. category overrides (no record_type field): observations and agreement with sample answers")
GOLD_T = {"DELETE_RECORD": "DELETE", "VERIFY_RECORD_ABSENT": "DELETE", "REDACT_RECORD": "REDACT", "VERIFY_RECORD_REDACTED": "REDACT",
          "ANONYMIZE_RECORD": "ANONYMIZE", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZE", "VERIFY_RECORD_PRESENT": "RETAIN"}
gold_t = {}
for cid, (st, steps) in gold.items():
    for s in steps:
        if s["operation"] in GOLD_T:
            gold_t[(cid, s["resource_id"])] = GOLD_T[s["operation"]]
fires = Counter(); agree = defaultdict(Counter)
for o in ctx.ix.obs:
    if not o.resource_id or prefix_of(o.resource_id) not in PREFIX_INFO or str(o.attrs.get("record_type") or "").upper() in TREATMENT:
        continue
    cat, dflt = category(o), PREFIX_INFO[prefix_of(o.resource_id)][1]
    if cat != dflt:
        fires[(dflt, cat)] += 1
for cid, (res, _) in full.items():
    if cid not in gold:
        continue
    for d in res["resources"]:
        dflt = PREFIX_INFO[prefix_of(d["resource_id"])][1]
        if d["category"] != dflt and (cid, d["resource_id"]) in gold_t:
            agree[(dflt, d["category"])]["agrees" if TREATMENT[d["category"]] == gold_t[(cid, d["resource_id"])] else "disagrees"] += 1
            agree[(dflt, d["category"])]["default would agree" if TREATMENT[dflt] == gold_t[(cid, d["resource_id"])] else "default would disagree"] += 1
for k, n in sorted(fires.items()):
    print(f"   {k[0]:18s} -> {k[1]:20s} observations {n:4d}   sample resources: {dict(agree.get(k, {}))}")

print("\n== 5. anchor and latest-file choice")
anchor_calls = Counter()
orig = fallback._anchor
def wrapped(ctx_, decisions, audit_at):
    missing = sum(1 for d in decisions if not d["verify_evidence"])
    have = any(d["verify_evidence"] for d in decisions)
    if missing:
        anchor_calls["records needing an anchor"] += missing
        anchor_calls["anchor from the case's own cited files" if have else "anchor = latest pre-audit manifest file"] += 1
    return orig(ctx_, decisions, audit_at)
fallback._anchor = wrapped
full2 = solve_all(ctx, reqs)
fallback._anchor = orig
print("  ", dict(anchor_calls))
multi = Counter()
for c, (res, _) in full2.items():
    a = by_case[c]["audit_at"]
    for d in res["resources"]:
        obs = [o for o in ctx.ix.by_resource.get(d["resource_id"], []) if o.captured_at <= a]
        if not obs:
            continue
        top = max((o.captured_at, o.snap_time) for o in obs)
        grp = {reading(o) for o in obs if (o.captured_at, o.snap_time) == top}
        older = {reading(o) for o in obs if (o.captured_at, o.snap_time) != top}
        multi["latest group has conflicting readings" if len(grp) > 1 else "latest group agrees"] += 1
        if older - grp:
            multi["older observations disagree with the latest"] += 1
print("  ", dict(multi))
