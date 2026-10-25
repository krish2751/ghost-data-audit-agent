@AGENTS.md

## Project Rules

1. Follow the README layout exactly, everything from the repo root. The solution lives in `code/main.py` and writes `output.csv` to the repo root. Evaluation material lives in `code/evaluation/`.
2. Use `.venv/bin/python` and `.venv/bin/pip` for everything; the needed libraries are already installed there.
3. The API key is in `.env` at the repo root. Never read, print, or edit `.env`.
4. Do not cat whole evidence files into the chat. Write small scripts that print summaries.
5. No hardcoded case answers.

## Problem & status

Keep the Decisions and Open questions lists current whenever something is settled.

- **Goal:** for each request in `dataset/deletion_requests.csv`, decide `COMPLETE` / `INCOMPLETE` / `NOT_APPLICABLE` and write ordered `steps_json` to the root `output.csv` (contract: `problem_statement.md`).
- **Complete only when:** every relevant copy got its `deletion_rules.csv` treatment, no active sync/import/restore path can recreate the data, retained records keep only permitted identifiers, and required retained records still exist.
- **Architecture:** code makes every decision; the model only reads. `code/main.py` -> `fallback.py` (decision engine) using `data/` (loader, identity, evidence index, readings), `joint.py` (records with no identifier), `planner.py`, `validator.py`. Readers in `code/readers/` (intent; rule conditions with the time-gated tools in `tools/registry.py`) return facts only, through the cached client `llm_client.py`; screenshots are extracted once (`screenshots.py`). Prompts in `code/prompts/`. README.md describes setup and run.
- **Rule sources:** every rule comes from `problem_statement.md` or a measured pattern documented with numbers in `code/analysis/data_findings.md`; unmeasured items are listed there under "Flagged".
- **Status (code-produced numbers only):** samples status 32/32, exact sequence 22/32, step P/R/F1 100/94.82/97.34, field accuracy 94.82. Root `output.csv` 518 rows (358 INCOMPLETE, 150 COMPLETE, 10 NOT_APPLICABLE). Hardcoding audit (`code/evaluation/hardcoding_audit.py`): solver 0 hits. Final API run done 2026-10-25 (523 calls, $2.00, output identical to the cached run); evaluation_report.md and usage_report.md written. Catalog-link fixes added afterwards (2 rows: case_39, case_61), re-run from the final cache with 0 new calls; validator rejects COMPLETE with []. code.zip built (README packaging command; clean unzip + dataset reproduces output.csv offline).
- **Model calls:** default backend is cache only (no API spending); `LLM_BACKEND=api` enables API calls. The owner authorized the final run (done); do not spend more without asking. Results judged inside the coding session are never evidence and are not stored.
- **Decisions so far:**
  - State and cited evidence come only from files captured <= `audit_at` (equality included). Identity links may come from any file; a resource counts only if seen in a file/activity row <= `audit_at`; audit-log identity changes apply only up to `audit_at`.
  - Retained audit/legal records may exist through a later export whose own record time is <= `audit_at`; verified with `""`, never cited (5 of 5 such sample records are in the answers).
  - A copy in any replica counts as remaining; latest pre-audit observation wins, within it the worst reading.
  - Flow/backup is a risk when evidence reads enabled/restorable; activity `reported_result` values are claims. Without `enabled`, a status field (delivered/healthy -> ACTIVE) decides; mode does not.
  - Catalog link rows (both formats) link only for the case whose [requested_at, audit_at] contains them; a screen record with no id maps to the record its catalog row names. Not dropped when the screenshot shows other identifiers (reverted).
  - Link by current/historical emails, `user_id`/`customer_reference`/`subject_reference`, SHA-256 of the lowercase email, phones; not by names.
  - Intent: the reader decides; `CLASSIFY_REQUEST` intake rows only break ties when the reader is not high-confidence. Verifying a deletion counts as a deletion request.
  - Records with no identifier: joint assignment (one account per case, other users' claims excluded, status/result agreement, window learned from identifier-linked pairs; analytics use a window and pairs learned per outcome from all non-account kinds). Ties stay unresolved.
  - One account per case: when several accounts are identifier-linked, keep those deleted inside the learned window.
  - COMPLETE-evidence tie-break: after the plain passes, an ambiguous case that is COMPLETE without the account keeps only candidates with a compliant pre-audit observation (not a hard filter: case_01/02/31 verify unobserved accounts).
  - Verification lists the full end state; INCOMPLETE remediation/verification use empty `evidence_id`. Rows sorted by `case_id` as strings.
  - Link reader and session backend removed (no code-produced evidence of value).
- **Open questions:**
  - Which source wins when two pre-audit sources disagree (7 of 1,361 decisions have disagreeing older observations).
  - Where `CACHE_ENTRY` / `EMAIL_DELIVERY_LOG` / `PRODUCT_TELEMETRY` evidence lives (none in text evidence or answers).
  - Verify-evidence anchor fallback for cases that cite nothing (flagged, 3 uses).
- **Pointers:** `code/analysis/data_findings.md`, `code/analysis/data_overview.md`, scorer `code/evaluation/main.py`.
