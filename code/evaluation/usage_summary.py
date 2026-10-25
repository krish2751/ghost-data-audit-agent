"""Token and cost summary of the model calls behind a run, from the client's usage log and cache entries.

Usage: .venv/bin/python code/evaluation/usage_summary.py [--requests N]
Every API call appends {key, model, tag, tokens} to code/cache/usage_log.jsonl (llm_client). Cache entries that are used
by the run but were not called in it (none, or reused screenshot extractions) are listed separately from their entry.
Prices are USD per million tokens (Claude API list prices for the models used).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm_client  # noqa: E402

PRICES = {"claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20}}


def cost(model, t):
    p = PRICES[model]
    return (t["input"] * p["input"] + t["output"] * p["output"] + t["cache_read"] * p["cache_read"]) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=518, help="requests the run answered (for per-request averages)")
    args = ap.parse_args()
    logged = []
    if llm_client.USAGE_LOG.exists():
        logged = [json.loads(l) for l in llm_client.USAGE_LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    called = {e["key"] for e in logged}
    reused = []
    for p in sorted(llm_client.CACHE_DIR.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["key"] not in called:
            reused.append({"key": d["key"], "model": d["model"], "tag": d.get("tag", ""), **d["usage"],
                           "created": d.get("created")})

    def table(rows, title):
        agg = defaultdict(lambda: {"calls": 0, "input": 0, "output": 0, "cache_read": 0})
        for e in rows:
            tag = "screenshot" if e["tag"].startswith("evidence_") else e["tag"].split(":")[0]
            for k in ((e["model"], tag), (e["model"], "all")):
                a = agg[k]
                a["calls"] += 1
                a["input"] += e.get("input_tokens", 0)
                a["output"] += e.get("output_tokens", 0)
                a["cache_read"] += e.get("cache_read_input_tokens", 0) or 0
        print(f"\n## {title}\n")
        print("| model | reader | calls | input tokens | output tokens | cache-read tokens | total tokens | cost (USD) |")
        print("|---|---|---|---|---|---|---|---|")
        tot = {"calls": 0, "input": 0, "output": 0, "cache_read": 0, "cost": 0.0}
        for (m, tag), a in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1] == "all", x[0][1])):
            c = cost(m, a)
            name = "**all**" if tag == "all" else tag
            print(f"| {m} | {name} | {a['calls']} | {a['input']:,} | {a['output']:,} | {a['cache_read']:,} | "
                  f"{a['input'] + a['output'] + a['cache_read']:,} | {c:.4f} |")
            if tag == "all":
                for k in ("calls", "input", "output", "cache_read"):
                    tot[k] += a[k]
                tot["cost"] += c
        return tot

    t1 = table(logged, f"API calls made by the run ({llm_client.USAGE_LOG.relative_to(llm_client.ROOT)})")
    t2 = table(reused, "Cached answers used but not called in this run") if reused else None
    n = args.requests
    print("\n## Totals\n")
    for name, t in (("run calls", t1), ("run calls + reused entries", None if t2 is None else
                     {k: t1[k] + t2[k] for k in t1})):
        if t is None:
            continue
        tok = t["input"] + t["output"] + t["cache_read"]
        print(f"- {name}: {t['calls']} calls, {tok:,} tokens ({t['input']:,} in / {t['output']:,} out), "
              f"${t['cost']:.4f}; per request (n={n}): {tok / n:,.0f} tokens, ${t['cost'] / n:.5f}")
    if reused:
        print("\nReused entries: " + ", ".join(f"{e['tag']} (created {e['created']})" for e in reused))


if __name__ == "__main__":
    main()
