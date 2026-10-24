"""How well does an activity time-cluster around reported_at (minus resources claimed by other users) recover unlinked gold resources?"""
import re, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, "code"); sys.path.insert(0, "code/analysis")
from fallback import Context, solve, P
from common import sample_cases
ctx = Context(); req, out = sample_cases(); claims = ctx.claims()
TREAT = {"DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "RETAIN_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "CHECK_DATA_FLOW", "CHECK_RESTORE_ACCESS"}
LO, HI = -80, 130
tot = found = uniq = 0; rows = []
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; res = solve(ctx, dict(r, case_id=cid), heuristics=False); uid = res.get("uid")
    have = {d["resource_id"] for d in res["resources"]}
    gold = {s["resource_id"] for s in out[cid][1]}
    rep = P(r["reported_at"])
    pool = {}
    for a in ctx.act:
        if a["event_type"] in TREAT and a["event_time"] <= r["audit_at"]:
            dt = (P(a["event_time"]) - rep).total_seconds() / 60
            if LO <= dt <= HI and not (claims.get(a["resource_id"], set()) - {uid}):
                pool.setdefault(a["resource_id"], []).append(a["event_type"])
    pre = Counter(re.sub(r"_\d+$", "", x) for x in pool)
    for g in sorted(gold - have):
        pg = re.sub(r"_\d+$", "", g); tot += 1; inpool = g in pool
        found += inpool; uniq += inpool and pre[pg] == 1
        rows.append((cid, g, inpool, pre[pg]))
print(f"unlinked-by-identifier gold resources: {tot}; in cluster pool: {found}; and sole candidate of its type: {uniq}")
for x in rows: print("  ", x)
