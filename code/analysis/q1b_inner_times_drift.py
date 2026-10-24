"""(a) Latest in-file timestamp of each cited file vs audit_at; (b) primary-vs-replica drift for cited SQL files."""
import re, sqlite3, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
man = manifest(); req, out = sample_cases()
TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
print("(a) cited file: capture, max in-file ts, audit_at, #ts after audit_at")
done = set()
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    for fid in sorted({s["evidence_id"] for s in out[cid][1] if s["evidence_id"]}):
        ts = TS.findall(evidence_text(man[fid]["file_path"])); a = req[cid]["audit_at"]
        late = sum(t > a for t in ts)
        if (fid, a) not in done:
            done.add((fid, a)); print(f"  {cid} {fid} cap={man[fid]['captured_at']} max_ts={max(ts) if ts else '-'} audit={a} late_ts={late}")
print("\n(b) cited SQL files: tables holding each gold resource")
for cid in sorted(out, key=lambda c: int(c.split("_")[1])):
    st, steps = out[cid]
    for fid in sorted({s["evidence_id"] for s in steps if s["evidence_id"] and man[s["evidence_id"]]["file_path"].endswith(".sql")}):
        con = sqlite3.connect(":memory:"); con.executescript(evidence_text(man[fid]["file_path"]))
        tabs = [t for (t,) in con.execute("select name from sqlite_master where type='table'")]
        for rid in sorted({s["resource_id"] for s in steps if s["evidence_id"] == fid}):
            where = []
            for t in tabs:
                cols = [c[1] for c in con.execute(f"pragma table_info('{t}')")]
                if "resource_id" in cols and con.execute(f"select 1 from {t} where resource_id=?", (rid,)).fetchone(): where.append(t)
            print(f"  {cid} {fid} {rid:15} in={where} gold={[s['operation'] for s in steps if s['resource_id']==rid]}")
