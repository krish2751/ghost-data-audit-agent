"""Test: gold account = nearest account DELETE_RECORD (by activity number) before the activity block of identifier-linkable resources."""
import re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
from linkage import *

users, hist = identities(); e2u = email_to_user(hist); req, out = sample_cases()
act = rows("system_activity.csv"); N = lambda a: int(a.split("_")[1])
by = {}
for a in act: by.setdefault(a["resource_id"], []).append(a)
nonlink = [a for a in act if a["event_type"] != "LINK_RESOURCE_IDENTITY"]
mono = sum(N(x["activity_id"]) < N(y["activity_id"]) and x["event_time"] > y["event_time"] for x, y in zip(sorted(nonlink, key=lambda a: N(a["activity_id"])), sorted(nonlink, key=lambda a: N(a["activity_id"]))[1:]))
print("activity-number vs time: adjacent pairs where later id has earlier time:", mono, "of", len(nonlink) - 1)
TREAT = {"DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "RETAIN_RECORD", "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "CHECK_DATA_FLOW", "CHECK_RESTORE_ACCESS"}
dels = sorted((a for a in act if a["event_type"] == "DELETE_RECORD" and a["target_system"] == "account_service"), key=lambda a: N(a["activity_id"]))
right = wrong = amb = noanchor = 0
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    r = req[cid]; st, steps = out[cid]; u = sorted(e2u[r["email"].lower()])[0]
    gold_acc = sorted({s["resource_id"] for s in steps if s["system_id"] == "account_service"})
    anchors = {}
    for rid, fid in sorted({(s["resource_id"], s["evidence_id"]) for s in steps if s["evidence_id"]}):
        if rid.startswith("account"): continue
        f = identifier_hits(" ".join(record_blobs(fid, rid)), u, hist, users)
        if f:
            ev = [N(a["activity_id"]) for a in by.get(rid, []) if a["event_type"] in TREAT and a["event_time"] <= r["audit_at"]]
            if ev: anchors[rid] = min(ev)
    if not anchors:
        noanchor += 1; print(f"{cid}: NO ANCHOR (no identifier-linkable resource with treatment/check activity); gold={gold_acc}"); continue
    first = min(anchors.values())
    prior = [a for a in dels if N(a["activity_id"]) < first]
    pred = prior[-1]["resource_id"] if prior else None
    gap = [a["resource_id"] for a in prior[-3:]]
    ok = pred in gold_acc
    right += ok; wrong += (not ok)
    between = [a for a in dels if N(a["activity_id"]) < first and N(a["activity_id"]) > N(prior[-1]["activity_id"])] if prior else []
    dist = first - N(prior[-1]["activity_id"]) if prior else None
    print(f"{cid}: anchors={ {k:v for k,v in anchors.items()} } pred={pred} gold={gold_acc} {'OK' if ok else 'WRONG'} dist={dist} last3_prior_deletes={gap}")
print(f"\nright={right} wrong={wrong} no_anchor={noanchor} of {len(out)}")
