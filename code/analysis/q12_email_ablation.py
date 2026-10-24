"""Ablation: what do historical identifiers add? Link counts and sample score with current-only identifiers."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import loader
from data.identity import IdentityStore
from fallback import Context, _matcher, solve_all
from planner import plan

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests(sample=False)

def linked(tokens_fn, req, uid):
    rx = _matcher(tokens_fn(uid, req["audit_at"]))
    return {o.resource_id for o in ctx.ix.obs if o.resource_id and rx.search(o.text)}

def cur_only(uid, audit_at):
    u = ctx.ids.users[uid]
    return {u["email"].lower(), u["email_hash"], u["phone"].lower(), uid}

gain_cases, gain_total, hist_req = 0, 0, 0
for r in reqs:
    uids = ctx.ids.resolve_email(r["email"])
    if not uids:
        continue
    uid = uids[0]
    full = linked(ctx.ids.tokens, r, uid)
    cur = linked(cur_only, r, uid)
    if r["email"].lower() != ctx.ids.users[uid]["email"].lower():
        hist_req += 1
    if full - cur:
        gain_cases += 1
        gain_total += len(full - cur)
print(f"requests {len(reqs)}; request email is historical: {hist_req}")
print(f"requests where historical identifiers link extra resources: {gain_cases}  (extra resource links: {gain_total})")

# sample score with current-only identifiers
import evaluation.main as ev

# score the samples with current-only identifiers vs full
import csv, subprocess
from validator import dumps
def run(label, patch):
    c = Context(intent_mode="regex", conditions_mode="default")
    if patch:
        c.ids.tokens = lambda uid, audit_at: {t.lower() for t in cur_only(uid, audit_at) if t}
    sr = loader.requests(sample=True)
    solved = solve_all(c, sr, heuristics=True)
    out = Path("/private/tmp/claude-501/-Users-krish-Downloads-HackerRank-Orchestrate-hackerrank-orchestrate-october26/99217d64-45af-4eff-b17c-fbaf13e89775/scratchpad") / f"abl_{label}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"]); w.writeheader()
        for r in sorted(sr, key=lambda r: r["case_id"]):
            res, steps = solved[r["case_id"]]
            w.writerow({"case_id": r["case_id"], "deletion_status": res["status"], "steps_json": dumps(steps)})
    p = subprocess.run([sys.executable, "code/evaluation/main.py", str(out)], capture_output=True, text=True)
    print(f"--- {label}"); print("\n".join(l for l in p.stdout.splitlines() if any(k in l.lower() for k in ("status", "exact", "f1", "precision", "recall"))))
run("full", False)
run("current_only", True)
