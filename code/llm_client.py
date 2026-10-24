"""Cached Anthropic client. Every response is stored under code/cache/ keyed by SHA-256 of
model + prompt + image bytes (+ max_tokens), so reruns work offline without an API key.

The key is read from the environment (ANTHROPIC_API_KEY, optionally from the repo-root .env
through python-dotenv) and is never printed or logged.
"""
import base64
import hashlib
import json
import os
import time
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
ROOT = CODE_DIR.parent
CACHE_DIR = CODE_DIR / "cache"
PROMPT_DIR = CODE_DIR / "prompts"
USAGE_LOG = CACHE_DIR / "usage_log.jsonl"
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def load_prompt(name):
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def cache_key(model, prompt, image_paths=(), max_tokens=4096):
    h = hashlib.sha256()
    for part in (model, prompt, str(max_tokens)):
        h.update(part.encode("utf-8")); h.update(b"\0")
    for p in image_paths:
        h.update(hashlib.sha256(Path(p).read_bytes()).digest())
    return h.hexdigest()


def _client():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set and the response is not cached")
    import anthropic
    return anthropic.Anthropic()


def call(model, prompt, image_paths=(), max_tokens=4096, tag=""):
    """Return {'text', 'usage': {'input_tokens','output_tokens'}, 'cached': bool, 'key'}."""
    image_paths = [Path(p) for p in image_paths]
    key = cache_key(model, prompt, image_paths, max_tokens)
    entry = CACHE_DIR / f"{key}.json"
    if entry.exists():
        d = json.loads(entry.read_text(encoding="utf-8"))
        return {"text": d["text"], "usage": d["usage"], "cached": True, "key": key}
    content = []
    for p in image_paths:
        content.append({"type": "image", "source": {"type": "base64",
                        "media_type": MEDIA_TYPES[p.suffix.lower()],
                        "data": base64.standard_b64encode(p.read_bytes()).decode("ascii")}})
    content.append({"type": "text", "text": prompt})
    resp = _client().messages.create(model=model, max_tokens=max_tokens,
                                     messages=[{"role": "user", "content": content}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    CACHE_DIR.mkdir(exist_ok=True)
    entry.write_text(json.dumps({"key": key, "model": model, "tag": tag, "stop_reason": resp.stop_reason,
                                 "images": [p.name for p in image_paths], "usage": usage, "text": text,
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                indent=1), encoding="utf-8")
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "model": model, "tag": tag, **usage}) + "\n")
    return {"text": text, "usage": usage, "cached": False, "key": key}


def parse_json(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)


# ---------------------------------------------------------------------------------------------
# Message-based calls (system prompt, tools, multi-turn). Cached by SHA-256 of the whole request,
# so a replay with identical tool results hits the cache at every round.
# ---------------------------------------------------------------------------------------------
def _request_key(req):
    return hashlib.sha256(json.dumps(req, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def chat(model, system, messages, tools=None, max_tokens=1024, effort=None, schema=None, tag=""):
    """One cached Messages API call. Returns {'content': [block dicts], 'text', 'usage', 'stop_reason', 'cached', 'key'}.

    `schema` requests a JSON-schema constrained final answer (only use it without tools).
    Assistant content blocks (including thinking) must be passed back unchanged in later rounds."""
    req = {"model": model, "system": system, "messages": messages, "max_tokens": max_tokens}
    if tools:
        req["tools"] = tools
    out_cfg = {}
    if effort:
        out_cfg["effort"] = effort
    if schema:
        out_cfg["format"] = {"type": "json_schema", "schema": schema}
    if out_cfg:
        req["output_config"] = out_cfg
    key = _request_key(req)
    entry = CACHE_DIR / f"{key}.json"
    if entry.exists():
        d = json.loads(entry.read_text(encoding="utf-8"))
        return {"content": d["content"], "text": d["text"], "usage": d["usage"], "stop_reason": d["stop_reason"],
                "cached": True, "key": key}
    resp = _client().messages.create(**req)
    content = [b.model_dump(exclude_none=True) for b in resp.content]
    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
    u = resp.usage
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
             "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
    CACHE_DIR.mkdir(exist_ok=True)
    entry.write_text(json.dumps({"key": key, "model": model, "tag": tag, "stop_reason": resp.stop_reason, "usage": usage,
                                 "text": text, "content": content, "request_tools": [t["name"] for t in (tools or [])],
                                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1, ensure_ascii=False),
                     encoding="utf-8")
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "model": model, "tag": tag, **usage}) + "\n")
    return {"content": content, "text": text, "usage": usage, "stop_reason": resp.stop_reason, "cached": False, "key": key}
