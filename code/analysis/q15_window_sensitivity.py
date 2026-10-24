"""How sensitive is the joint account assignment to the window size? Accounts resolved / correct on the samples."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).resolve().parent))
import joint
from fallback import Context
from common import sample_cases

ctx = Context(intent_mode="regex", conditions_mode="default")
_, gold = sample_cases()
gold_acc = {c: {s["resource_id"] for s in g[1] if s["resource_id"].startswith("account")} for c, g in gold.items()}
print("window_min | accounts assigned (all 550) | samples assigned | samples correct | samples wrong")
for w in (30, 60, 90, 120, 180, 360, 1440):
    res, info = joint.compute(ctx, window_min=w)
    acc = res["account"]
    sa = {c: a for c, (a, _) in acc.items() if c in gold_acc}
    ok = sum(1 for c, a in sa.items() if a in gold_acc[c]); bad = len(sa) - ok
    print(f"{w:10d} | {len(acc):28d} | {len(sa):16d} | {ok:15d} | {bad}")
