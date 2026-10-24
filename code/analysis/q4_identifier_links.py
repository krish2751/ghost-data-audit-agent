"""For each gold resource with a cited file: which subject identifiers appear in that resource's own record?"""
import json, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *

users, hist = identities(); e2u = email_to_user(hist); man = manifest(); req, out = sample_cases()
def blobs(fid, rid):
    """Text blobs that belong to the record for rid in file fid."""
    p = man[fid]["file_path"]; t = evidence_text(p); rx = re.compile(r"(?<![\w])" + rid + r"(?![\w])")
    if p.endswith(".json"):
        res = []
        def walk(x):
            if isinstance(x, dict):
                if x.get("resource_id") == rid: res.append(json.dumps(x))
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(json.loads(t)); return res
    lines = t.splitlines(); hit = [l for l in lines if rx.search(l)]
    if p.endswith(".log"):
        tr = {m for l in hit for m in re.findall(r"trace_id=(\S+)", l)}
        hit += [l for l in lines if l not in hit and any(f"trace_id={x}" in l for x in tr)]
    return hit
ctr = Counter(); none_rows = []; by_fam = defaultdict(Counter)
for cid, (st, steps) in sorted(out.items()):
    u = sorted(e2u[req[cid]["email"].lower()])[0]; h = hist[u]; cur = users[u]["email"].lower()
    for rid, fid in sorted({(s["resource_id"], s["evidence_id"]) for s in steps if s["evidence_id"]}):
        bl = " ".join(blobs(fid, rid)).lower(); fam = man[fid]["file_path"].split(".")[-1]
        found = set()
        if cur in bl: found.add("email_current")
        if any(e in bl for e in h["emails"] if e != cur): found.add("email_old")
        if re.search(r"(?<![\w])" + u + r"(?![\w])", bl): found.add("user_id")
        if any(x.lower() in bl for x in h["hashes"] | {hashlib_ for hashlib_ in []}): found.add("hash")
        if any(p in bl for p in h["phones"]): found.add("phone")
        if any(n.lower() in bl for n in h["names"]): found.add("name")
        key = ",".join(sorted(found)) or "NONE"; ctr[key] += 1; by_fam[fam][key] += 1
        if key == "NONE": none_rows.append((cid, rid, fid, [s['operation'] for s in steps if s['resource_id']==rid][:2]))
print("identifier combos in the resource's own record:"); [print(f"  {n:3d} {k}") for k, n in ctr.most_common()]
print("by file type:", {k: dict(v) for k, v in by_fam.items()})
print("resources with no subject identifier in their record (", len(none_rows), "):")
for r in none_rows[:25]: print("  ", r)
