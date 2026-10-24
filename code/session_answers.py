"""Helper for answering queued reader requests inside the Claude Code session (no API tokens).

    .venv/bin/python code/session_answers.py list [tag]        # show pending requests (compact)
    .venv/bin/python code/session_answers.py put ANSWERS.json  # {key: answer_text_or_object, ...} -> cache_session/
Answers are stored with usage 0 and backend 'claude_code_session'; they are never mixed with API cache entries.
"""
import json
import sys
import time
from pathlib import Path

CODE = Path(__file__).resolve().parent
SESSION = CODE / "cache_session"


def main():
    cmd = sys.argv[1]
    if cmd == "list":
        tag = sys.argv[2] if len(sys.argv) > 2 else None
        for f in sorted((SESSION / "pending").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            if tag and d["tag"] != tag:
                continue
            if (SESSION / f"{d['key']}.json").exists():
                continue
            print(f"=== {d['key'][:12]} tag={d['tag']}")
            print(d["messages"][-1]["content"] if isinstance(d["messages"][-1]["content"], str) else d["messages"][-1]["content"])
    elif cmd == "put":
        answers = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        pend = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (SESSION / "pending").glob("*.json")}
        n = 0
        for short, ans in answers.items():
            keys = [k for k in pend if k.startswith(short)]
            assert len(keys) == 1, (short, keys)
            text = ans if isinstance(ans, str) else json.dumps(ans, ensure_ascii=False)
            d = pend[keys[0]]
            (SESSION / f"{keys[0]}.json").write_text(json.dumps(
                {"key": keys[0], "model": d["model"], "tag": d["tag"], "backend": "claude_code_session", "stop_reason": "end_turn",
                 "usage": {"input_tokens": 0, "output_tokens": 0}, "text": text, "content": [{"type": "text", "text": text}],
                 "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1, ensure_ascii=False), encoding="utf-8")
            n += 1
        print("stored", n, "answers")


if __name__ == "__main__":
    main()
