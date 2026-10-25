# Ghost Data Still Exists: deletion-audit agent

HackerRank Orchestrate, October 2026. The challenge contract is in [`problem_statement.md`](./problem_statement.md).

For every request in `dataset/deletion_requests.csv` the solver decides `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` and
writes the ordered `steps_json` to `output.csv` at the repository root.

## Setup and run

Python 3 with the packages already installed in `.venv` (`anthropic`, `python-dotenv`, `pypdf`). From the repository root:

```bash
.venv/bin/python code/main.py
```

writes `output.csv` (518 rows).

```bash
.venv/bin/python code/main.py --sample
```

runs the 32 public samples to `code/runs/sample_pred.csv`.

```bash
.venv/bin/python code/evaluation/main.py code/runs/sample_pred.csv
```

scores a prediction file against `dataset/sample_output.csv`.

Model answers are cached in `code/cache/` (the answers of the final API run, see `code/evaluation/usage_report.md`), so a
run needs no API key and makes no API calls by default. To call the API
for requests that are not cached, set `LLM_BACKEND=api` and put `ANTHROPIC_API_KEY` in the environment or in an
uncommitted `.env` at the repository root.

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
7. **Steps** (`planner.py`, `validator.py`): findings, remediation and verification in the required order; every row is
   validated (phases, states, step numbers, evidence cited only when captured by `audit_at`) before it is written.

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
                          audit, failure diff, mismatch review, usage summary; evaluation_report.md, usage_report.md
code/analysis/            measurement scripts; data_findings.md lists the data pattern behind every rule
code/cache/               cached model answers
```

## Packaging

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/runs/*" "*/.DS_Store"
```

Submission link: https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists
