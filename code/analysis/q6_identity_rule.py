"""Apply the settled identity rule to the gold accounts: links from ANY evidence file; safeguard = resource seen in a file/activity <= audit_at."""
import re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from linkage import record_blobs
users, hist = identities(); e2u = email_to_user(hist); man = manifest(); req, out = sample_cases(); act = rows("system_activity.csv")
text = {fid: evidence_text(m["file_path"]) for fid, m in man.items()}
def idents_at(u, audit_at):
    """Identifier values for user u as of audit_at: current snapshot reverted past later audit rows, plus earlier values."""
    cur = users[u]; vals = {"email": {cur["email"].lower()}, "phone": {cur["phone"]}, "hash": {cur["email_hash"]}}
    later_any = 0
    for a in sorted(hist[u]["audit"], key=lambda a: a["event_time"]):
        k = {"email": "email", "phone": "phone", "email_hash": "hash"}[a["field_name"]]
        if a["event_time"] <= audit_at:
            for v in (a["old_value"], a["new_value"]):
                if v: vals[k].add(v.lower() if k == "email" else v)
        else:
            later_any += 1
            vals[k].discard(a["new_value"].lower() if k == "email" else a["new_value"])
            if a["old_value"]: vals[k].add(a["old_value"].lower() if k == "email" else a["old_value"])
    return vals, later_any, {cur["name"]}
tot = 0; stats = {"cited_link": 0, "any_file_link": 0, "safeguard_ok": 0, "still_unlinked": []}; later_cases = 0
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; u = sorted(e2u[r["email"].lower()])[0]; vals, later, names = idents_at(u, r["audit_at"]); later_cases += later > 0
    for acc in sorted({s["resource_id"] for s in out[cid][1] if s["system_id"] == "account_service"}):
        tot += 1; rx = re.compile(r"(?<![\w])" + acc + r"(?![\w])")
        files = [f for f, t in text.items() if rx.search(t)]
        def linked(f):
            b = " ".join(record_blobs(f, acc)).lower()
            return (any(e in b for e in vals["email"]) or re.search(r"(?<![\w])" + u + r"(?![\w])", b) is not None
                    or any(h in b for h in vals["hash"]) or any(p in b for p in vals["phone"]))
        cited = {s["evidence_id"] for s in out[cid][1] if s["evidence_id"]}
        lk_cited = any(linked(f) for f in files if f in cited); lk_any = any(linked(f) for f in files)
        seen_before = any(man[f]["captured_at"] <= r["audit_at"] for f in files) or any(a["resource_id"] == acc and a["event_time"] <= r["audit_at"] for a in act)
        stats["cited_link"] += lk_cited; stats["any_file_link"] += lk_any; stats["safeguard_ok"] += (lk_any and seen_before)
        if not (lk_any and seen_before): stats["still_unlinked"].append((cid, acc, "no-file-link" if not lk_any else "safeguard-fail"))
print(f"gold accounts: {tot}; cases with audit identity changes after audit_at: {later_cases}")
print("linked in cited file only          :", stats["cited_link"])
print("linked in ANY file (new rule)      :", stats["any_file_link"])
print("...and passes seen<=audit_at guard :", stats["safeguard_ok"])
print("still unlinked:", len(stats["still_unlinked"]))
for x in stats["still_unlinked"]: print("  ", x)
