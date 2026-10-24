@AGENTS.md

## Project Rules

1. Follow the README layout exactly, everything from the repo root. The solution lives in `code/main.py` and writes `output.csv` to the repo root. Evaluation material lives in `code/evaluation/`.
2. Use `.venv/bin/python` and `.venv/bin/pip` for everything; the needed libraries are already installed there.
3. The API key is in `.env` at the repo root. Never read, print, or edit `.env`.
4. Do not cat whole evidence files into the chat. Write small scripts that print summaries.
5. No hardcoded case answers.

## Problem & status

Keep the Decisions and Open questions lists current whenever something is settled.

- **Goal:** for each request in `dataset/deletion_requests.csv`, decide `COMPLETE` / `INCOMPLETE` / `NOT_APPLICABLE` and write ordered `steps_json` to the root `output.csv` (contract: `problem_statement.md`, `README.md`).
- **Complete only when:** every relevant copy got its `deletion_rules.csv` treatment, no active sync/import/restore path can recreate the data, retained records keep only permitted identifiers, and required retained records still exist.
- **Requirements:** read the CSVs and evidence from `dataset/`; exact output schema; eval via `code/evaluation/main.py`; no hardcoded answers.
- **Architecture (revised):** deterministic code makes every decision; the model is only a *reader*. Pipeline: `code/data/` (evidence index, identity, states), `code/tools/registry.py` (time-gated tools), `code/fallback.py` (decision engine), `planner.py`, `validator.py`, `intent.py`, `main.py`. Readers (`code/readers/`): loop of up to 4 rounds with the tools, returns structured facts + short reason, never steps/status; untrusted text is fenced and ignored as instructions; all calls through the cached client (`code/llm_client.py`, `chat()`), prompts in `code/prompts/`. Readers: intent (done), rule conditions (done: `readers/condition_reader.py`, support shared context, attachment ownership, retention window), unreadable evidence (todo). See `code/analysis/rule_condition_heuristics.md`.
- **Status:** intent reader done (samples 32/32, custom 15/15 incl. 9 NA in 9 languages, 10 CLASSIFY-joined cases all NA, avg 1.0 rounds, 518 -> 10 NA, same as regex-after-fix). Deterministic baseline done (root `output.csv` written, 518 rows). Samples: status 32/32, step P/R/F1 99.4/86.5/92.5, exact sequence 13/32. Tuned on all 32 samples (no holdout). Run: `.venv/bin/python code/main.py [--sample]`, score: `.venv/bin/python code/evaluation/main.py code/runs/sample_pred.csv`. Rule-condition reader: 123 items in 114 cases, avg 1.09 rounds, 0 treatment/status/step changes vs defaults (samples unchanged: F1 92.5). Link reader built (`readers/link_reader.py`, off by default: does not beat timing, see `code/analysis/data_findings.md`). Late-snapshot existence for audit/legal records (pending owner approval) lifts samples to F1 94.0, exact 16/32, status 32/32. Next: unreadable-evidence reader, holdout split, reports. Hardcoding audit: `code/evaluation/hardcoding_audit.py` (solver 0 hits).
- **Decisions so far** (observed in the 32 samples unless noted):
  - State and cited evidence come only from files captured <= `audit_at` (equality included). Identity links may come from any file; a resource counts only if seen in a file/activity row <= `audit_at`; audit-log identity changes apply only up to `audit_at`.
  - A copy in any replica counts as remaining; absence = latest pre-audit observation says not found, or a covering snapshot lacks it. Latest file wins; within it the worst reading.
  - Flow/backup is a risk when evidence reads enabled/restorable (activity CHECK_* with no later disable/block agrees); activity `reported_result` values are claims.
  - Link by current/old emails, `user_id`/`customer_reference`/`subject_reference`, SHA-256 of the lowercase email, phones; lowercase before matching. Log lines are joined by trace id.
  - Intent: the reader decides from the request text; `CLASSIFY_REQUEST` rows (joined to cases 533-542 through ledger evidence_50) only break ties when the reader is not high-confidence. Verifying/auditing a deletion counts as a deletion request (the 4 sample cases 21/25/27/28).
  - Rule conditions: reader returns yes/no/unclear (+ retain_until); code maps no -> DELETE (support message), REDACT (shared attachment), DELETE (expired retention); unclear keeps the rule default. Prompts tuned on sample outcomes (first version flipped 3 sample cases wrongly), so holdout still needed.
  - Verification lists the full end state (clean and retained records too); INCOMPLETE remediation/verification use empty `evidence_id`. Category quirks: contact_lookup -> marketing (analytics_platform), legacy contact index -> secondary identifier, delete.
  - Rows are sorted by `case_id` as strings (ids are unpadded, so `case_100` < `case_33`); ambiguity noted.
  - Account discovery heuristic when no evidence link: sole unclaimed account DELETE_RECORD within +-120 min of `reported_at` (ablation: +1.8 F1, +5 exact sequences).
- **Open questions:**
  - Clean resources with no identifier (absent accounts, anonymized analytics, retained audit records) are all of the baseline's misses (26 of 193 steps); needs the agent's weak-link judgment.
  - Which source wins when two pre-audit sources disagree (no sample shows it).
  - Where `CACHE_ENTRY` / `EMAIL_DELIVERY_LOG` evidence lives (none in text evidence or gold).
  - `NOT_APPLICABLE` untested by samples; regex intent baseline misses negations (fixed for visible phrasing only); 10 `CLASSIFY_REQUEST` rows not joined.
- **Pointers:** `code/analysis/data_overview.md`, `code/analysis/findings_*.md`, scorer `code/evaluation/main.py`, PNG extractions cached in `code/cache/`.
