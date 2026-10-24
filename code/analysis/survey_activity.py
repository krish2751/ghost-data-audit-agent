"""Print a per-event_type survey of dataset/system_activity.csv (counts, systems, result values, detail patterns)."""
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def norm(text):
    text = re.sub(r"\b[a-z_]+_\d+\b", lambda m: re.sub(r"\d+", "N", m.group()), text)
    text = re.sub(r"[\w.+-]+@[\w.-]+", "<EMAIL>", text)
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<HASH>", text)
    return re.sub(r"\d+", "N", text)


rows = list(csv.DictReader(open(ROOT / "dataset" / "system_activity.csv", encoding="utf-8")))
by = defaultdict(list)
for r in rows:
    by[r["event_type"]].append(r)

print(f"total rows {len(rows)}; time {min(r['event_time'] for r in rows)} .. {max(r['event_time'] for r in rows)}")
print("resource_id prefixes overall:", dict(Counter(re.sub(r"\d+$", "N", r["resource_id"]) for r in rows).most_common(15)))
for et, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print(f"\n### {et}  n={len(rs)}")
    print("  source->target:", dict(Counter(f"{r['source_system']}->{r['target_system']}" for r in rs).most_common(8)))
    print("  results:", dict(Counter(r["reported_result"] for r in rs)))
    print("  resource prefixes:", dict(Counter(re.sub(r"\d+$", "N", r["resource_id"]) for r in rs).most_common(6)))
    pats = Counter(norm(r["details"]) for r in rs)
    print(f"  distinct detail patterns: {len(pats)}")
    for p, n in pats.most_common(TOP):
        print(f"   {n:4d}  {p[:170]}")
