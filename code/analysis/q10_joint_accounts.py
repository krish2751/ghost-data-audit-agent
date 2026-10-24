"""Joint assignment of account DELETE events to cases (each case has exactly one account; each account belongs to one case).
Constraint propagation over all 550 requests; evaluation-only comparison with the sample gold."""
import csv, json, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, "code")
from datetime import datetime
from fallback import Context, solve_all, P
from data import loader
from readers.intent_reader import prefetch_intents
ctx = Context(); sample = loader.requests(sample=True); evalr = loader.requests(); reqs = sample + evalr
prefetch_intents(ctx, reqs)
res = solve_all(ctx, reqs, heuristics=False)
W = int(sys.argv[1]) if len(sys.argv) > 1 else 120
gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"]) if s["resource_id"].startswith("account")} for r in csv.DictReader(open(loader.DS / "sample_output.csv"))}
dels = [a for a in ctx.act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
claims = ctx.claims()
assigned = {}   # case -> account
need = {}
for r in reqs:
    cid = r["case_id"]; rr, _ = res[cid]
    if rr["status"] == "NOT_APPLICABLE" or "uid" not in rr: continue
    accs = [d["resource_id"] for d in rr["resources"] if d["resource_id"].startswith("account")]
    if accs: assigned[cid] = accs[0]
    else: need[cid] = r
taken = set(assigned.values())
# learn which (reported_status, DELETE result) pairs occur among identifier-linked cases (no labels involved)
reqd = {r["case_id"]: r for r in reqs}
pair = Counter()
for cid, acc in assigned.items():
    ev = [a for a in ctx.act_by_res.get(acc, []) if a["event_type"] == "DELETE_RECORD"]
    if ev: pair[(reqd[cid]["reported_status"], ev[0]["reported_result"])] += 1
tot = Counter()
for (st, rs), n in pair.items(): tot[st] += n
COMPAT = {k for k, n in pair.items() if n / tot[k[0]] >= 0.05}
print("learned compatible (status, result) pairs:", sorted(COMPAT))
def cands(r):
    rep = P(r["reported_at"]); uid = res[r["case_id"]][0]["uid"]
    out = []
    for a in dels:
        if a["event_time"] <= r["audit_at"] and abs((P(a["event_time"]) - rep).total_seconds()) <= W * 60:
            if (r["reported_status"], a["reported_result"]) in COMPAT and not (claims.get(a["resource_id"], set()) - {uid}) and a["resource_id"] not in taken:
                out.append(a["resource_id"])
    return sorted(set(out))
print(f"cases: {len(reqs)}; account already linked by identifier: {len(assigned)}; need account: {len(need)}")
rounds = 0; unique = {}
while True:
    changed = False
    for cid, r in need.items():
        if cid in unique: continue
        c = [x for x in cands(r) if x not in taken]
        if len(c) == 1:
            unique[cid] = c[0]; taken.add(c[0]); changed = True
    rounds += 1
    if not changed: break
amb = {cid: cands(r) for cid, r in need.items() if cid not in unique}
print(f"propagation rounds {rounds}: uniquely assigned {len(unique)}; ambiguous {sum(1 for c in amb.values() if len(c)>1)}; no candidate {sum(1 for c in amb.values() if not c)}")
print("ambiguity sizes:", dict(Counter(len(c) for c in amb.values())))
ok = bad = 0; wrong = []
for cid, acc in unique.items():
    if cid in gold:
        if acc in gold[cid]: ok += 1
        else: bad += 1; wrong.append((cid, acc, gold[cid]))
print(f"sample cases uniquely assigned: correct {ok}, wrong {bad}", wrong)
samp_need = [c for c in need if c in gold]
print("sample cases still needing an account:", len(samp_need), "| resolved uniquely:", sum(1 for c in samp_need if c in unique), "| ambiguous:", [(c, amb[c]) for c in samp_need if c in amb][:12])
