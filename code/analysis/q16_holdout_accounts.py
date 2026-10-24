"""Label-free hold-out for account discovery.

Truth = the account an identifier ties to the user (email/hash/user_id inside the account record). For each fold, those
links are hidden and the joint rules must recover them from activity alone (window, exclusivity, learned status/result
compatibility). No sample_output.csv is read. Folds are grouped by user so a user's other requests cannot leak the answer."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joint
from fallback import Context, solve_all
from data import loader

K = 5
ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests()
base = solve_all(ctx, reqs, heuristics=False)
sample_ids = {r["case_id"] for r in loader.requests(sample=True)}
del_res = {a["resource_id"] for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"}
truth, uid_of = {}, {}
for r in reqs:
    res = base[r["case_id"]][0]
    if "uid" not in res:
        continue
    uid_of[r["case_id"]] = res["uid"]
    accs = [d["resource_id"] for d in res["resources"] if d["resource_id"].startswith("account") and d["resource_id"] in del_res]
    if len(accs) == 1:
        truth[r["case_id"]] = accs[0]
users = sorted({uid_of[c] for c in truth})
fold_of = {u: i % K for i, u in enumerate(users)}
print(f"hold-out set: {len(truth)} cases with an identifier-linked account that has a DELETE event "
      f"({len(truth & sample_ids) if False else len(set(truth) & sample_ids)} are sample cases)")

bounds_seen = []

def evaluate(window_min):
    res = Counter(); res_s = Counter()
    for k in range(K):
        hide = frozenset(c for c in truth if fold_of[uid_of[c]] == k)
        got_all, info = joint.compute(ctx, window_min=window_min, hide=hide, base=base, analytics=False)
        out = got_all["account"]
        bounds_seen.append(info["bounds"]["account"])
        for c in hide:
            got = out.get(c)
            kind = "unresolved" if got is None else ("correct" if got[0] == truth[c] else "wrong")
            res[kind] += 1
            if c in sample_ids:
                res_s[kind] += 1
    return res, res_s

print("window_min | correct | wrong | unresolved | precision | recall  || samples only: correct/wrong/unresolved")
for w in (None, 90, 120):
    bounds_seen.clear()
    r, s = evaluate(w)
    n = sum(r.values()); p = r["correct"] / max(1, r["correct"] + r["wrong"])
    print(f"{'learned' if w is None else w:>10} | {r['correct']:7d} | {r['wrong']:5d} | {r['unresolved']:10d} | {p:8.1%} | {r['correct']/n:6.1%} || {s['correct']}/{s['wrong']}/{s['unresolved']}")
    if w is None:
        print("           learned bounds per fold (min, relative to reported_at):", sorted({(round(a, 1), round(b, 1)) for a, b in bounds_seen}))
