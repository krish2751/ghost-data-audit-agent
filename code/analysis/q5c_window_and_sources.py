"""(1) How unique is the 'account delete near reported_at' window? (2) Do logs/ledgers/audit/tombstone rows link gold accounts to the subject?"""
import json, re, sys
from datetime import datetime, timedelta
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from linkage import *
users, hist = identities(); e2u = email_to_user(hist); man = manifest(); req, out = sample_cases(); act = rows("system_activity.csv")
P = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
dels = [a for a in act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"]
print("(1) account DELETE_RECORD candidates inside offset window of reported_at")
res = {"unique_right": 0, "multi_has_gold": 0, "miss": 0}
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; rep = P(r["reported_at"]); gold = {s["resource_id"] for s in out[cid][1] if s["system_id"] == "account_service"}
    low = all(len(g.split("_")[1]) == 3 for g in gold)
    lo, hi = (-5, 10) if low else (-75, -40)
    cand = [a["resource_id"] for a in dels if lo <= (P(a["event_time"]) - rep).total_seconds() / 60 <= hi]
    ok = bool(gold & set(cand)); k = "unique_right" if ok and len(cand) == 1 else "multi_has_gold" if ok else "miss"; res[k] += 1
    print(f"  {cid} window=[{lo},{hi}]m cands={len(cand)} gold_in={ok} {cand if len(cand) > 1 else ''}")
print(" ", res)

print("\n(2) sources that tie each gold account to the subject")
text = {fid: evidence_text(m["file_path"]) for fid, m in man.items()}
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    u = sorted(e2u[req[cid]["email"].lower()])[0]; h = hist[u]
    for acc in sorted({s["resource_id"] for s in out[cid][1] if s["system_id"] == "account_service"}):
        rx = re.compile(r"(?<![\w])" + acc + r"(?![\w])"); links = []
        for fid, t in text.items():
            if not rx.search(t): continue
            if fid.startswith("x"): continue
            bl = " ".join(record_blobs(fid, acc)); f = identifier_hits(bl, u, hist, users)
            links.append((fid, man[fid]["captured_at"] <= req[cid]["audit_at"], sorted(f) or ["no-id"]))
        print(f"  {cid} {acc:13} {links if links else 'not in any text evidence'}")
