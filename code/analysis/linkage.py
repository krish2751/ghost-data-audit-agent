"""Helpers: which gold resources are linkable to the subject by an identifier in their own cited record."""
import json, re
from common import *

_man = manifest()

def record_blobs(fid, rid):
    p = _man[fid]["file_path"]; t = evidence_text(p); rx = re.compile(r"(?<![\w])" + re.escape(rid) + r"(?![\w])")
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

def identifier_hits(blob, user, hist, users):
    b = blob.lower(); h = hist[user]; cur = users[user]["email"].lower(); f = set()
    if cur in b: f.add("email_current")
    if any(e in b for e in h["emails"] if e != cur): f.add("email_old")
    if re.search(r"(?<![\w])" + user + r"(?![\w])", b): f.add("user_id")
    if any(x.lower() in b for x in h["hashes"]): f.add("hash")
    if any(p in b for p in h["phones"]): f.add("phone")
    if any(n.lower() in b for n in h["names"]): f.add("name")
    return f
