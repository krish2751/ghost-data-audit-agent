"""Print a structural survey of dataset/evidence (manifest, SQL schemas, JSON keys, log line shapes, PDF text, PNG names)."""
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "dataset"
man = list(csv.DictReader(open(EV / "evidence_files.csv", encoding="utf-8")))


def norm(text):
    text = re.sub(r"[\w.+-]+@[\w.-]+", "<EMAIL>", text)
    text = re.sub(r"\b[0-9a-f]{32,}\b", "<HASH>", text)
    text = re.sub(r"\d{4}-\d\d-\d\d[T ][\d:.]+Z?", "<TS>", text)
    return re.sub(r"\d+", "N", text)


print("manifest rows", len(man))
print("by extension:", dict(Counter(Path(m["file_path"]).suffix for m in man)))
print("by origin:", dict(Counter(m["origin"] for m in man)))
print("captured_at range:", min(m["captured_at"] for m in man), "..", max(m["captured_at"] for m in man))
missing = [m["file_path"] for m in man if not (EV / m["file_path"]).exists()]
print("manifest paths missing on disk:", missing)
on_disk = {str(p.relative_to(EV)) for p in (EV / "evidence").rglob("*") if p.is_file()}
print("files on disk not in manifest:", sorted(on_disk - {m["file_path"] for m in man}))

print("\n=== SQL ===")
sql = [m for m in man if m["file_path"].endswith(".sql")]
shapes = {}
for m in sql:
    text = (EV / m["file_path"]).read_text(encoding="utf-8", errors="replace")
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(text)
        err = None
    except Exception as e:  # report and continue
        err = str(e)[:80]
    tabs = {}
    for (t,) in con.execute("select name from sqlite_master where type='table' order by 1"):
        cols = [c[1] for c in con.execute(f"pragma table_info('{t}')")]
        tabs[t] = (len(cols), con.execute(f'select count(*) from "{t}"').fetchone()[0], cols)
    m["_tabs"] = tabs
    shapes.setdefault(tuple(sorted((t, tuple(v[2])) for t, v in tabs.items())), []).append(m)
    if err:
        print("  exec error", m["file_id"], err)
    con.close()
print(f"{len(sql)} SQL files, {len(shapes)} distinct schemas")
for sh, ms in shapes.items():
    print(f"- schema shared by {len(ms)} files, e.g. {ms[0]['file_id']} {ms[0]['file_path'].split('/')[-1]} origin={ms[0]['origin']}")
    for t, v in ms[0]["_tabs"].items():
        print(f"    {t}({', '.join(v[2])}) rows={v[1]}")
print("SQL leading statement words:", dict(Counter(
    ln.split()[0].upper() for m in sql for ln in (EV / m["file_path"]).read_text(errors="replace").splitlines()
    if ln.strip() and not ln.startswith("--")).most_common(8)))
print("SQL comment-line examples:")
for ln in [l for l in (EV / sql[0]["file_path"]).read_text(errors="replace").splitlines() if l.startswith("--")][:6]:
    print("   ", ln[:140])

print("\n=== JSON ===")
for m in [m for m in man if m["file_path"].endswith(".json")]:
    d = json.loads((EV / m["file_path"]).read_text(encoding="utf-8"))
    def desc(x, depth=0):
        if isinstance(x, dict):
            return "{" + ", ".join(f"{k}:{desc(v, depth + 1) if depth < 2 else '..'}" for k, v in list(x.items())[:8]) + "}"
        if isinstance(x, list):
            return f"[{len(x)}x " + (desc(x[0], depth + 1) if x else "") + "]"
        return type(x).__name__
    print(f"- {m['file_id']} {m['file_path'].split('/')[-1]} origin={m['origin']}: {desc(d)[:330]}")

print("\n=== TXT ===")
for m in [m for m in man if m["file_path"].endswith(".txt")]:
    t = (EV / m["file_path"]).read_text(encoding="utf-8", errors="replace")
    print(f"- {m['file_id']} {m['file_path'].split('/')[-1]} origin={m['origin']} chars={len(t)} :: {norm(t[:200])!r}")

print("\n=== LOGS ===")
for m in [m for m in man if m["file_path"].endswith(".log")]:
    lines = (EV / m["file_path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    pats = Counter(norm(l)[:110] for l in lines)
    print(f"- {m['file_id']} {m['file_path'].split('/')[-1]} origin={m['origin']} lines={len(lines)} patterns={len(pats)}")
    for p, n in pats.most_common(2):
        print(f"     {n:4d} {p}")

print("\n=== PDF ===")
try:
    from pypdf import PdfReader
    for m in [m for m in man if m["file_path"].endswith(".pdf")]:
        r = PdfReader(str(EV / m["file_path"]))
        t = " ".join((p.extract_text() or "") for p in r.pages)
        print(f"- {m['file_id']} {m['file_path'].split('/')[-1]} origin={m['origin']} pages={len(r.pages)} chars={len(t)} :: {norm(t[:230])!r}")
except ImportError:
    print("pypdf not available")

print("\n=== PNG ===")
for m in [m for m in man if m["file_path"].endswith(".png")]:
    print(f"- {m['file_id']} {m['file_path'].split('/')[-1]} origin={m['origin']} captured={m['captured_at']} bytes={(EV / m['file_path']).stat().st_size}")
