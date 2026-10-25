"""Reader loop: the model fetches evidence with time-gated tools (max rounds) and returns structured facts.

The model never decides statuses or writes steps; callers turn the returned facts into decisions in code.
"""
import json

import llm_client

MAX_ROUNDS = 4


def fence(tag, text):
    """Wrap untrusted text so the model treats it as data. Closing-tag lookalikes are neutralised."""
    safe = (text or "").replace(f"</{tag}>", f"< /{tag}>")
    return f"<{tag}>\n{safe}\n</{tag}>"


def run_reader(model, system, user_text, schema, tools=None, case_tools=None, effort="low", max_tokens=1024,
               max_rounds=MAX_ROUNDS, tag=""):
    """Returns {'facts': dict|None, 'rounds': int, 'calls': [usage...], 'tool_calls': int, 'error': str|None}.

    Without tools the schema is enforced by the API; with tools the model is asked for JSON and it is parsed."""
    messages = [{"role": "user", "content": user_text}]
    calls, tool_calls = [], 0
    for rnd in range(1, max_rounds + 1):
        last = rnd == max_rounds
        try:
            r = llm_client.chat(model, system, messages, tools=tools or None, max_tokens=max_tokens,
                                effort=effort, schema=schema if not tools else None, tag=tag)
        except llm_client.CacheMiss as e:
            return {"facts": None, "rounds": rnd, "calls": calls, "tool_calls": tool_calls, "error": f"cache_miss:{e}"}
        calls.append({"usage": r["usage"], "cached": r["cached"]})
        uses = [b for b in r["content"] if b.get("type") == "tool_use"]
        if r["stop_reason"] == "tool_use" and uses and not last:
            messages.append({"role": "assistant", "content": r["content"]})
            results = []
            for u in uses:
                tool_calls += 1
                res = case_tools.call(u["name"], u["input"])
                results.append({"type": "tool_result", "tool_use_id": u["id"], "content": json.dumps(res, default=str)[:12000]})
            if rnd + 1 == max_rounds:  # keep the same tools (thinking blocks are bound to them) but ask for the final answer
                results.append({"type": "text", "text": "This was the last round that allows tool calls. Reply now with the final JSON only; do not call any tool."})
            messages.append({"role": "user", "content": results})
            continue
        try:
            return {"facts": llm_client.parse_json(r["text"]), "rounds": rnd, "calls": calls, "tool_calls": tool_calls, "error": None}
        except ValueError as e:
            return {"facts": None, "rounds": rnd, "calls": calls, "tool_calls": tool_calls, "error": f"unparseable: {e}"}
    return {"facts": None, "rounds": max_rounds, "calls": calls, "tool_calls": tool_calls, "error": "round limit"}
