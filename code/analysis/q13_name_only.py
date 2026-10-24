"""Do records mention a subject by name only (no email/hash/phone/user_id of theirs)? Names are not used as link tokens."""
import sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collections import Counter
from fallback import Context, _matcher
from data import loader

ctx = Context(intent_mode="regex", conditions_mode="default")
reqs = loader.requests(sample=True) + loader.requests(sample=False)
name_count = Counter(u["name"].lower() for u in ctx.ids.users.values())
hits = Counter(); examples = {}
for r in reqs:
    uids = ctx.ids.resolve_email(r["email"])
    if not uids: continue
    uid = uids[0]; ids = ctx.ids.identifiers(uid, r["audit_at"])
    rx = _matcher(ctx.ids.tokens(uid, r["audit_at"]))
    names = {n.lower() for n in ids["name"]}
    for o in ctx.ix.obs:
        if not o.resource_id or rx.search(o.text): continue
        t = o.text.lower()
        for n in names:
            if n in t:
                k = "name unique in directory" if name_count.get(n, 0) <= 1 else "name shared by several users"
                hits[k] += 1; examples.setdefault(k, (r["case_id"], o.resource_id, o.file_id, n))
print("record+name-only matches (no other identifier of that user):", dict(hits))
for k, v in examples.items(): print(" e.g.", k, v)

from analysis.common import sample_cases  # noqa
