"""Score the intent reader: samples, custom multilingual cases, the CLASSIFY_REQUEST-joined cases, and impact on all 518.

Usage: .venv/bin/python code/evaluation/intent_eval.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from custom_intent_cases import CASES  # noqa: E402
from data import loader  # noqa: E402
from fallback import Context, solve  # noqa: E402
from intent import wants_deletion  # noqa: E402
from readers.intent_reader import prefetch_intents, read_intent  # noqa: E402


def main():
    ctx = Context(use_png=False, intent_mode="model")
    reqs, samples = loader.requests(), loader.requests(sample=True)
    allreqs = reqs + samples
    prefetch_intents(ctx, allreqs)
    for _, _, t, _ in CASES:
        ctx.intent_cache[t] = read_intent(t)
    rounds, calls = [], 0

    print("== 1. samples (all 32 are deletion requests) ==")
    ok = sum(ctx.intent(r, (ctx.ids.resolve_email(r["email"]) or [None])[0])[0] for r in samples)
    print(f"model says deletion: {ok}/{len(samples)}")

    print("\n== 2. custom multilingual cases ==")
    good = 0
    for name, lang, text, label in CASES:
        r = ctx.intent_cache[text]; f = r["facts"]
        hit = f is not None and f["asks_for_deletion"] == label
        good += hit
        print(f"  {'OK ' if hit else 'BAD'} {name:26} lang={f['language'] if f else '?':10} expect={'DEL' if label else 'NA '} "
              f"got={'DEL' if f and f['asks_for_deletion'] else 'NA '} conf={f['confidence'] if f else '?'} inj={f['contains_instructions_to_assistant'] if f else '?'}")
    na = [c for c in CASES if not c[3]]
    print(f"custom accuracy: {good}/{len(CASES)}  (NOT_APPLICABLE cases: {len(na)}, in {len({c[1] for c in na})} languages)")

    print("\n== 3. cases whose account has an intake CLASSIFY_REQUEST (non-deletion) row ==")
    joined = []
    for r in reqs:
        u = (ctx.ids.resolve_email(r["email"]) or [None])[0]
        if u and ctx.classify_nondeletion(u, r["audit_at"]):
            joined.append(r)
    wrong = [r["case_id"] for r in joined if ctx.intent(r, ctx.ids.resolve_email(r["email"])[0])[0]]
    print(f"joined cases: {len(joined)} ({sorted(r['case_id'] for r in joined)}); model-based decision still 'deletion' for: {wrong or 'none'}")

    print("\n== 4. impact on the 518 evaluation requests ==")
    changed, flags, base_na, model_na, types = [], Counter(), 0, 0, Counter()
    for r in reqs:
        u = (ctx.ids.resolve_email(r["email"]) or [None])[0]
        m, info = ctx.intent(r, u)
        b = wants_deletion(r["request_text"])
        base_na += not b; model_na += not m
        for fl in info["flags"]:
            flags[fl] += 1
        if info.get("facts"):
            types[info["facts"]["request_type"]] += 1
        rounds.append(info.get("rounds", 0))
        if m != b:
            changed.append((r["case_id"], b, m, r["request_text"][:80]))
    print(f"NOT_APPLICABLE: regex baseline {base_na}, model {model_na}; decisions that differ: {len(changed)}")
    for c in changed: print("   ", c)
    print("request types:", dict(types), " flags:", dict(flags))
    uniq = {r["request_text"] for r in reqs}
    print(f"unique request texts: {len(uniq)} of {len(reqs)}; average reader rounds per item: {sum(rounds)/len(rounds):.2f}")

    # pipeline status changes
    diff = 0
    for r in reqs:
        ctx.intent_mode = "regex"; a = solve(ctx, r)["status"]
        ctx.intent_mode = "model"; b = solve(ctx, r)["status"]
        diff += a != b
    print(f"deletion_status changes vs regex-baseline pipeline: {diff} of {len(reqs)}")


if __name__ == "__main__":
    main()
