# Ghost Data Still Exists: deletion-audit agent

HackerRank Orchestrate, October 2026. The challenge contract is in [`problem_statement.md`](./problem_statement.md).

For every request in `dataset/deletion_requests.csv` the solver decides `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` and
writes the ordered `steps_json` to `output.csv` at the repository root, one row per request in the same order as
`dataset/deletion_requests.csv` (case_33, case_34, …, case_550).

## Setup and run

Python 3.13 with the packages in `requirements.txt` (`anthropic`, `pypdf`, `python-dotenv`). The challenge `dataset/`
folder must sit at the repository root next to `code/`; it is not part of `code.zip`. From the repository root:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Then:

```bash
.venv/bin/python code/main.py
```

writes `output.csv` (518 rows).

```bash
.venv/bin/python code/main.py --sample
```

runs the 32 public samples to `code/runs/sample_pred.csv`.

```bash
.venv/bin/python code/validator.py            # or: code/validator.py --sample
```

checks `output.csv` (or the sample predictions) against the submission contract and prints errors and warnings.

```bash
.venv/bin/python code/evaluation/main.py code/runs/sample_pred.csv
```

scores a prediction file against `dataset/sample_output.csv`.

Model answers are cached in `code/cache/`: these are the answers of the final API run (see
`code/evaluation/usage_report.md`). So the commands above need no API key and make no API calls.

| environment variable | values | meaning |
|---|---|---|
| `LLM_BACKEND` | `cache` (default) or `api` | `cache`: cached model answers only; an uncached request falls back: regex intent, rule-default conditions, or the screenshot is skipped. `api`: uncached requests call the Claude API and are cached. |
| `ANTHROPIC_API_KEY` | your key | needed only with `LLM_BACKEND=api`; read from the environment or an uncommitted `.env` at the repository root, never logged |

The final API run that produced `output.csv` was:

```bash
LLM_BACKEND=api .venv/bin/python code/main.py
```

It ran with an empty cache except the 11 screenshot extractions, so every intent and rule-condition read was a fresh API
call. Then `.venv/bin/python code/evaluation/usage_summary.py --log code/evaluation/final_run_usage_log.jsonl`
summarizes its usage.

Options: `--cases ID1,ID2` (subset), `--out PATH`, `--intent regex` (no model for intent), `--conditions default`
(rule defaults instead of the condition reader).

## How it works

Code makes every decision. The model only reads text and returns structured facts.

1. **Intent** (`readers/intent_reader.py`, model): does the request text authorize deletion, in any language, with
   negations? If not, the case is `NOT_APPLICABLE` with `[]`. The deterministic decision is in `intent.py`.
2. **Identity** (`data/identity.py`): the request email resolves to a user through current and historical emails; the
   user's identifiers are all emails, their SHA-256 hashes, phones and the user id, with audit-log changes applied only
   up to `audit_at`.
3. **Evidence index** (`data/evidence_index.py`): SQL snapshots are executed in SQLite, JSON bundles, text ledgers and logs
   (joined by trace id) are parsed, PDF text is extracted, and the 11 screenshots are read once by the model into records
   (`screenshots.py`, cached).
4. **Linking** (`fallback.py`): records whose own content holds one of the user's identifiers, plus
   `LINK_RESOURCE_IDENTITY` activity rows. Records with no identifier (absent accounts, anonymized analytics) are assigned
   by joint propagation over all requests (`joint.py`): one account per case, accounts claimed by other users excluded,
   the reported status must agree with the DELETE result, and the event must fall in a time window learned from the
   identifier-linked cases.
5. **State at `audit_at`** (`data/states.py`, `fallback._decide`): only files captured at or before `audit_at`; the latest
   observation wins, a copy in any replica counts, activity results are claims.
6. **Policy** (`schema.TREATMENT` from `deletion_rules.csv`): delete, redact, anonymize, retain, disable a flow or block a
   restore. Text-dependent rule conditions (shared support context, attachment ownership, retention windows) are read by
   the rule-condition reader (`readers/condition_reader.py`, model with time-gated tools in `tools/registry.py`).
7. **Steps** (`planner.py`, `validator.py`): findings, then remediation, then verification. Within a phase, steps follow
   the operation order and then `system_id` and `resource_id`.
8. **Validation** (`validator.py`): every row is validated before it is written, then the whole file is checked. These are
   **errors**:
   - the header is not exactly `case_id,deletion_status,steps_json`;
   - a request is missing, extra or duplicated, or rows are out of the request file's order;
   - a status is not COMPLETE, INCOMPLETE or NOT_APPLICABLE, or NOT_APPLICABLE has steps;
   - `steps_json` is not a valid JSON array, or a step does not have exactly the seven fields;
   - `step_no` is not consecutive from 1;
   - a phase, operation or state is not allowed, or a state does not match its operation;
   - phase order or within-phase sort order is broken;
   - a finding, or a verification of a COMPLETE case, has no `evidence_id`;
   - a remediation step, or a verification of an INCOMPLETE case, has an `evidence_id`;
   - a cited evidence ID does not exist or is captured after its case's `audit_at`.

   COMPLETE with `[]` is a **warning**. It is allowed, per the official clarification, for an authorized request with no
   observed violation and no evidence-backed check.

Model: `claude-sonnet-5-5` for intent, rule conditions and screenshots. Every call goes through `llm_client.py`, which
caches by request hash; untrusted text is fenced and treated as data.

## Layout

```text
code/main.py              entry point
code/fallback.py          decision engine
code/joint.py             joint assignment of records with no identifier
code/data/                loaders, identity, evidence index, readings
code/readers/             intent and rule-condition readers, reader loop
code/tools/registry.py    time-gated tools for the condition reader
code/prompts/             reader prompts
code/planner.py, code/validator.py, code/schema.py, code/intent.py, code/llm_client.py, code/screenshots.py
code/evaluation/          scorer, intent and condition evaluations, custom intent and end-to-end cases, hardcoding
                          audit, mismatch and extraction reviews, usage summary; evaluation_report.md, usage_report.md
code/analysis/            measurement scripts; data_findings.md lists the data pattern behind every rule
code/cache/               cached model answers
```

## Packaging

```bash
zip -r code.zip README.md requirements.txt code -x "*/__pycache__/*" "*/.venv/*" "*/runs/*" "*.DS_Store"
```

`code.zip` holds the solution, prompts, cached model answers and `code/evaluation/` (including `evaluation_report.md` and
`usage_report.md`); `output.csv` and `log.txt` are submitted separately. `dataset/`, `.env` and virtual environments
are not included.

Submission link: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
