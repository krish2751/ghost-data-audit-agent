"""Where does a resource id appear (activity + evidence), to see how it could be tied to a user."""
import re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import *
man = manifest(); req, out = sample_cases()
text = {fid: evidence_text(m["file_path"]) for fid, m in man.items()}
act = rows("system_activity.csv")
for cid in sys.argv[1:]:
    st, steps = out[cid]; u_email = req[cid]["email"]
    print(f"\n== {cid} {st} email={u_email}")
    for rid in sorted({s["resource_id"] for s in steps}):
        rx = re.compile(r"(?<![\w])" + rid + r"(?![\w])")
        a = [f"{x['activity_id']}:{x['event_type']}:{x['reported_result']}@{x['event_time'][5:16]}" for x in act if x["resource_id"] == rid]
        f = [fid for fid, t in text.items() if rx.search(t)]
        print(f"  {rid}: activity={a}  evidence_files={f}")
