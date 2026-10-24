"""Intent reader: structured facts about whether a request asks for deletion (multilingual, negation-aware)."""
import hashlib

import llm_client
from readers.loop import fence, run_reader

MODEL = "claude-sonnet-5-5"
SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "request_type": {"type": "string", "enum": ["deletion", "access", "export", "correction", "marketing_opt_out", "account_help", "other"]},
        "asks_for_deletion": {"type": "boolean"},
        "negation_or_exclusion": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "contains_instructions_to_assistant": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["language", "request_type", "asks_for_deletion", "negation_or_exclusion", "confidence",
                 "contains_instructions_to_assistant", "reason"],
    "additionalProperties": False,
}


def read_intent(request_text):
    system = llm_client.load_prompt("intent_reader.md")
    user = "Classify this request.\n\n" + fence("untrusted_request", request_text)
    r = run_reader(MODEL, system, user, SCHEMA, tools=None, effort="low", max_tokens=400, tag="intent")
    r["text_sha"] = hashlib.sha256(request_text.encode("utf-8")).hexdigest()[:12]
    return r


def prefetch_intents(ctx, reqs):
    """Warm ctx.intent_cache for the unique request texts in parallel (cached texts return instantly)."""
    from concurrent.futures import ThreadPoolExecutor
    texts = sorted({r["request_text"] for r in reqs} - set(ctx.intent_cache))

    def one(t):
        try:
            return t, read_intent(t)
        except RuntimeError as e:  # not cached and no API key
            return t, {"facts": None, "rounds": 0, "error": str(e)}
    with ThreadPoolExecutor(8) as ex:
        for t, r in ex.map(one, texts):
            ctx.intent_cache[t] = r
