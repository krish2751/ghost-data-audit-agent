"""For each sample case: every evidence file that mentions the subject's resources/identifiers, ordered by capture time, vs what the answer cited."""
import re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *

users, hist = identities(); e2u = email_to_user(hist); man = manifest(); req, out = sample_cases()
text = {fid: evidence_text(m["file_path"]).lower() for fid, m in man.items()}
def has(t, tok): return re.search(r"(?<![\w])" + re.escape(tok.lower()) + r"(?![\w])", t) is not None
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; st, steps = out[cid]; u = sorted(e2u[r["email"].lower()])[0]; h = hist[u]
    res = sorted({s["resource_id"] for s in steps}); cited = {s["evidence_id"] for s in steps if s["evidence_id"]}
    toks = res + [u] + sorted(h["emails"])
    rows_ = []
    for fid, m in man.items():
        t = text[fid]
        hit_res = [x for x in res if has(t, x)]; hit_id = [x for x in [u] + sorted(h["emails"]) if has(t, x)]
        if hit_res or hit_id:
            rows_.append((m["captured_at"], fid, len(hit_res), len(res), hit_id and "id", fid in cited))
    rows_.sort()
    print(f"\n{cid} {st} audit_at={r['audit_at']} resources={len(res)}")
    for cap, fid, nr, tot, idh, c in rows_:
        print(f"   {'*' if c else ' '} {fid} cap={cap} {'AFTER ' if cap > r['audit_at'] else 'before'} res_hits={nr}/{tot} id={'y' if idh else 'n'}")
