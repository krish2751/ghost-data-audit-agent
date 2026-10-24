"""For sample flow/backup resources: activity events (time, type, result) next to the gold state and evidence state."""
import json, re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *

req, out = sample_cases(); man = manifest()
act = rows("system_activity.csv"); by = {}
for a in act: by.setdefault(a["resource_id"], []).append(a)
def evidence_view(fid, rid):
    t = evidence_text(man[fid]["file_path"]); lines = [l.strip() for l in t.splitlines() if re.search(r"(?<![\w])" + rid + r"(?![\w])", l)]
    return [l[:230] for l in lines[:2]]
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    st, steps = out[cid]
    tgt = [s for s in steps if s["system_id"] in ("integration_service", "backup_service") and s["phase"] != "REMEDIATION"]
    if not tgt: continue
    print(f"\n{cid} {st} audit_at={req[cid]['audit_at']} reported={req[cid]['reported_status']}")
    seen = set()
    for s in tgt:
        rid = s["resource_id"]
        if rid in seen: continue
        seen.add(rid)
        gold = [x["operation"] for x in steps if x["resource_id"] == rid]
        print(f"  {rid}: gold={gold} cited={[x['evidence_id'] for x in steps if x['resource_id']==rid and x['evidence_id']][:1]}")
        for a in sorted(by.get(rid, []), key=lambda a: a["event_time"]):
            print(f"      act {a['event_time']} {'AFTER ' if a['event_time']>req[cid]['audit_at'] else 'before'} {a['event_type']:<22} {a['reported_result']:<8} {a['activity_id']}")
        ev = [x["evidence_id"] for x in steps if x["resource_id"] == rid and x["evidence_id"]]
        if ev:
            for l in evidence_view(ev[0], rid): print("      ev:", l)
