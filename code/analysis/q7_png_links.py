"""Do the extracted PNG records resolve the previously unlinked gold accounts (and other gold resources)?"""
import json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent)); sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from common import *
import screenshots
users, hist = identities(); e2u = email_to_user(hist); req, out = sample_cases(); man = manifest()
png = {}
for row in screenshots.png_files():
    d, _ = screenshots.extract(row); png[row["file_id"]] = d
byres = {}
for fid, d in png.items():
    for rec in d["records"]:
        if rec.get("resource_id"): byres.setdefault(rec["resource_id"], []).append((fid, rec))
print("PNG records:", sum(len(d['records']) for d in png.values()), "distinct resource ids:", len(byres))
tot = hit = 0; lowid = {"case_01","case_02","case_04","case_07","case_08","case_10"}
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    u = sorted(e2u[req[cid]["email"].lower()])[0]; h = hist[u]; audit = req[cid]["audit_at"]
    for rid in sorted({s["resource_id"] for s in out[cid][1]}):
        if rid not in byres: continue
        for fid, rec in byres[rid]:
            b = json.dumps(rec).lower(); ids = rec.get("identifiers") or {}
            f = [k for k, c in (("email", any(e in b for e in h["emails"])), ("user_id", u in b), ("phone", any(p in b for p in h["phones"])), ("hash", any(x in b for x in h["hashes"])), ("name", any(n.lower() in b for n in h["names"]))) if c]
            print(f"  {cid} {rid:18} in {fid} ({man[fid]['captured_at'][:16]} {'<=' if man[fid]['captured_at']<=audit else '> '}audit) ids={f or 'none'} status={ {k:v for k,v in list((rec.get('status_fields') or {}).items())[:3]} }")
