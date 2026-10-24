"""Checks: (1) email_hash vs sha256(email); (2) cache_/email_delivery_ in gold; (3) low-ID sample patterns vs the rest."""
import hashlib, re, sys
from collections import Counter
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *

users, hist = identities()
print("== 1. email_hash")
variants = {"sha256(lower)": lambda e: e.lower(), "sha256(raw)": lambda e: e, "sha256(lower+strip)": lambda e: e.strip().lower()}
for name, f in variants.items():
    ok = sum(hashlib.sha256(f(u["email"]).encode()).hexdigest() == u["email_hash"] for u in users.values())
    print(f"  identities current: {name}: {ok}/{len(users)}")
bad = [u["user_id"] for u in users.values() if hashlib.sha256(u["email"].lower().encode()).hexdigest() != u["email_hash"]]
print("  mismatches (sha256 lower):", len(bad), bad[:5])
aud = [a for a in rows("user_audit_log.csv") if a["field_name"] == "email_hash"]
okn = sum(hashlib.sha256(a["new_value"].lower().encode()).hexdigest() == a["new_value"] or True for a in aud)
emails = {a["user_id"]: [] for a in aud}
# each email_hash audit row: does old/new hash equal sha256 of some known email of that user?
allh = {u: {hashlib.sha256(e.encode()).hexdigest() for e in h["emails"]} for u, h in hist.items()}
inset = sum((a["old_value"] in allh[a["user_id"]]) and (a["new_value"] in allh[a["user_id"]]) for a in aud)
print(f"  audit email_hash rows where old & new hash = sha256 of a known email of that user: {inset}/{len(aud)}")
print("  email case: current emails with uppercase:", sum(u['email'] != u['email'].lower() for u in users.values()))

req, out = sample_cases()
print("\n== 2. prefixes in gold answers")
pre = Counter(); per_case = {}
for cid, (st, steps) in out.items():
    ps = Counter(re.sub(r"_?\d+$", "", s["resource_id"]) for s in steps)
    per_case[cid] = ps; pre.update(ps)
print(" ", dict(pre))
print("  cache_/email_delivery_ present:", any(k in pre for k in ("cache", "email_delivery")))
print("  system_ids:", dict(Counter(s["system_id"] for _, st in out.values() for s in st)))

print("\n== 3. low-ID vs other sample patterns")
def num(rid): return int(re.search(r"(\d+)$", rid).group(1))
low = {}
for cid, (st, steps) in out.items():
    ids = [num(s["resource_id"]) for s in steps]
    low[cid] = all(i < 1000 for i in ids) and any(len(re.search(r"(\d+)$", s["resource_id"]).group(1)) == 3 for s in steps)
for grp, lab in ((True, "low-id (3-digit ids)"), (False, "other")):
    cs = [c for c in out if low[c] == grp]
    print(f"  {lab}: {len(cs)} cases {sorted(cs, key=lambda c:int(c.split('_')[1]))[:40]}")
    print("    status:", dict(Counter(out[c][0] for c in cs)), " steps/case avg:", round(sum(len(out[c][1]) for c in cs)/max(1,len(cs)),1))
    print("    ev files:", dict(Counter(s["evidence_id"] for c in cs for s in out[c][1] if s["evidence_id"])))
    print("    reported:", dict(Counter(req[c]["reported_status"] for c in cs)))
    print("    ops:", dict(Counter(s["operation"] for c in cs for s in out[c][1])))
    print("    systems:", dict(Counter(s["system_id"] for c in cs for s in out[c][1])))
for c in ("case_01", "case_02"):
    print(" ", c, out[c][0], [(s["system_id"], s["resource_id"], s["operation"], s["evidence_id"]) for s in out[c][1]])
