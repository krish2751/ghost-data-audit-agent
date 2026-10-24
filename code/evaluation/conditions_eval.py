"""Impact of the rule-condition reader: item counts, answers, rounds, treatment flips, and sample score.

Usage: .venv/bin/python code/evaluation/conditions_eval.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import loader  # noqa: E402
from fallback import Context, solve_all  # noqa: E402
from readers.intent_reader import prefetch_intents  # noqa: E402


def run(ctx, reqs):
    return solve_all(ctx, reqs)


def main():
    reqs = loader.requests() + loader.requests(sample=True)
    base = Context(use_png=True, conditions_mode="default"); prefetch_intents(base, reqs)
    ctx = Context(use_png=True, conditions_mode="model"); ctx.intent_cache = base.intent_cache
    a, b = run(base, reqs), run(ctx, reqs)
    items = rounds = tool_calls = cases = errs = 0
    types, answers, flips = Counter(), Counter(), []
    for cid, (res, steps) in b.items():
        c = res.get("conditions")
        if not c:
            continue
        cases += c["items"] > 0
        items += c["items"]; rounds += c["rounds"]; tool_calls += c["tool_calls"]; errs += bool(c["error"])
        for d in res["resources"]:
            if d.get("condition"):
                types[d["condition"]["type"]] += 1; answers[(d["condition"]["type"], d["condition"]["answer"])] += 1
        flips += [(cid, x) for x in c["applied"]]
    print(f"cases with reader items: {cases}; items: {items}; reader runs: {sum(1 for r in b.values() if r[0].get('conditions', {}).get('items'))}; "
          f"avg rounds/run: {rounds / max(1, cases):.2f}; tool calls: {tool_calls}; errors: {errs}")
    print("item types:", dict(types))
    print("answers:", dict(answers))
    print("treatment changes applied:", len(flips), flips[:10])
    st = sum(a[k][0]["status"] != b[k][0]["status"] for k in a)
    sp = sum(a[k][1] != b[k][1] for k in a)
    print(f"deletion_status changes vs defaults: {st} of {len(a)}; steps changed: {sp}")


if __name__ == "__main__":
    main()
