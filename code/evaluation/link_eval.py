"""Score the link reader against the sample answers (evaluation only): which proposed links are real resources of the case?

Usage: .venv/bin/python code/evaluation/link_eval.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import loader  # noqa: E402
from fallback import Context  # noqa: E402
from readers.intent_reader import prefetch_intents  # noqa: E402
from readers.link_reader import read_links  # noqa: E402
import fallback  # noqa: E402


def main():
    gold = {r["case_id"]: {s["resource_id"] for s in json.loads(r["steps_json"])} for r in csv.DictReader(open(loader.DS / "sample_output.csv"))}
    ctx = Context(link_mode="off"); reqs = loader.requests(sample=True); prefetch_intents(ctx, reqs)
    tab = Counter(); rounds = []; pooled = 0; missed_in_pool = missed_not_in_pool = 0
    for req in reqs:
        res = fallback.solve(ctx, req)
        have = {d["resource_id"] for d in res["resources"]}
        uid = res["uid"]
        cand = {d["resource_id"] for d in res["resources"]}
        links, run, pool = read_links(ctx, req, uid, cand)
        rounds.append(run["rounds"]); pooled += len(pool)
        g = gold[req["case_id"]]
        for rid, x in links.items():
            tab[(x.get("belongs"), x.get("confidence"), rid in g and rid not in have)] += 1
        for rid in g - have:
            if rid in pool: missed_in_pool += 1
            else: missed_not_in_pool += 1
        for rid in g - have:
            pass
    print(f"cases {len(reqs)}; avg rounds {sum(rounds)/len(rounds):.2f}; candidates in pools {pooled}")
    print("gold resources still unlinked after identifier linking: in candidate pool", missed_in_pool, "| not in pool", missed_not_in_pool)
    print("(belongs, confidence, is_true_missing_resource): count")
    for k, n in sorted(tab.items(), key=lambda x: str(x)): print("  ", k, n)


if __name__ == "__main__":
    main()
