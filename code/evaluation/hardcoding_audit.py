"""Scan code/ for hardcoded case ids, resource ids, evidence ids/file names, emails/user ids and sample-answer reads.

Usage: .venv/bin/python code/evaluation/hardcoding_audit.py
Solver files = everything except analysis/ (exploration), evaluation/ (scoring + test fixtures), cache/, runs/.
"""
import re
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
PATTERNS = {
    "case id": r"\bcase_\d+\b",
    "resource id": r"\b(?:account|search|support|analytics|export|backup|data_flow|audit_record|tombstone|legal_hold|marketing|cache|email_delivery)_\d+\b",
    "evidence id": r"\bevidence_\d+\b",
    "activity/audit id": r"\b(?:activity|audit)_\d+\b",
    "user id": r"\buser_\d+\b",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}",
    "evidence file name": r"\b(?:service_events|resource_lookup_trace|support_replica|customer_data_\w+|snapshot_bundle|service_resource_export|handover|syslog_archive|operations_stream)\w*",
    "sample answer read": r"sample_output|sample_cases",  # loader.requests(sample=True) reads sample *inputs*, which is allowed
}
SKIP_DIRS = {"cache", "runs", "__pycache__"}


def scope(path):
    rel = path.relative_to(CODE).parts
    if rel[0] == "prompts":
        return "prompts"  # format examples such as account_1234 inside prompt text; changing a prompt invalidates its cache
    if rel[0] in ("analysis",):
        return "analysis"
    if rel[0] == "evaluation":
        return "evaluation"
    return "solver"


def main():
    hits = {"solver": [], "prompts": [], "analysis": [], "evaluation": []}
    for p in sorted(CODE.rglob("*")):
        if p.suffix not in (".py", ".md") or any(part in SKIP_DIRS for part in p.parts) or p == Path(__file__).resolve():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for name, rx in PATTERNS.items():
                if re.search(rx, line):
                    hits[scope(p)].append((str(p.relative_to(CODE.parent)), n, name, line.strip()[:110]))
    for sc, hs in hits.items():
        files = sorted({h[0] for h in hs})
        print(f"\n## {sc}: {len(hs)} hits in {len(files)} files")
        if sc in ("solver", "prompts") or "-v" in sys.argv:
            for f, n, name, line in hs:
                print(f"  {f}:{n} [{name}] {line}")
        else:
            print("  files:", ", ".join(files))
    return 1 if hits["solver"] else 0


if __name__ == "__main__":
    sys.exit(main())
