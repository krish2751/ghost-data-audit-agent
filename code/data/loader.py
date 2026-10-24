"""Dataset CSV loaders (everything resolves from the repo root)."""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "dataset"


def read_csv(name):
    with open(DS / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def requests(sample=False):
    return read_csv("sample_deletion_requests.csv" if sample else "deletion_requests.csv")


def manifest():
    return {m["file_id"]: m for m in read_csv("evidence_files.csv")}


def rules():
    return read_csv("deletion_rules.csv")


def activity():
    return read_csv("system_activity.csv")


LINK_RX = re.compile(r"linked (\S+) \((\S+)\) to (\S+@\S+) and (user_\d+)")


def activity_links(rows):
    """LINK_RESOURCE_IDENTITY rows -> list of (activity_id, resource_id, email_lower, user_id, event_time)."""
    out = []
    for a in rows:
        if a["event_type"] == "LINK_RESOURCE_IDENTITY":
            m = LINK_RX.search(a["details"])
            if m:
                out.append((a["activity_id"], m.group(1), m.group(3).lower(), m.group(4), a["event_time"]))
    return out
