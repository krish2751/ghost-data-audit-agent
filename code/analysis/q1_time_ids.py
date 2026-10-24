"""For each sample case: resolve user, list cited evidence with capture time vs audit_at and which user identifiers appear in it."""
import sys
from collections import Counter
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *

users, hist = identities(); e2u = email_to_user(hist); man = manifest(); req, out = sample_cases()
print("audit fields:", Counter(a["field_name"] for h in hist.values() for a in h["audit"]))
text = {fid: evidence_text(m["file_path"]).lower() for fid, m in man.items()}
for cid in sorted(out):
    r = req[cid]; us = e2u.get(r["email"].lower(), set()); st, steps = out[cid]
    u = sorted(us)[0] if us else None
    h = hist.get(u, {})
    cited = sorted({s["evidence_id"] for s in steps if s["evidence_id"]})
    cur = users[u]["email"].lower() if u else None
    print(f"\n{cid} {st} user={u} users_for_email={len(us)} req_email_is_current={r['email'].lower()==cur} audit_at={r['audit_at']} reported={r['reported_status']}")
    for fid in cited:
        m = man[fid]; t = text[fid]
        found = [k for k, vals in (("email", h.get("emails", [])), ("phone", h.get("phones", [])), ("hash", h.get("hashes", [])), ("name", [n.lower() for n in h.get("names", [])]), ("uid", [u or ""])) if any(v and v.lower() in t for v in vals)]
        hist_em = [e for e in h.get("emails", []) if e != cur and e in t]
        print(f"  {fid} {m['file_path'].split('/')[-1][:48]:48} cap={m['captured_at']} {'AFTER' if m['captured_at']>r['audit_at'] else 'before'} ids={found} old_email_in_file={bool(hist_em)}")
