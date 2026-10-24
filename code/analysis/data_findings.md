# Data findings (index)

Detailed notes: `data_overview.md` (activity and evidence survey), `findings_time_conflicts_risks_identity.md`, `findings_account_link.md`, `rule_condition_heuristics.md`. Exploration scripts are `q*.py` in this folder; none is imported by the solver.

## No hardcoding

Check: `.venv/bin/python code/evaluation/hardcoding_audit.py` scans every `.py`/`.md` under `code/` (not `cache/`, `runs/`) for case ids, resource ids with numbers, evidence ids, activity/audit ids, user ids, emails, evidence file names and sample-answer reads, grouped by solver / prompts / analysis / evaluation.

Result (after cleanup):
- **Solver: 0 hits.** Four early hits were harmless and removed: a `--cases case_01,case_02` usage example, a `handover` source label, a "handover TXT" tool description and example ids in the screenshot prompt format line.
- **Prompts: 1 hit**, `screenshot_extract.md` shows format examples (`account_1234`, `search_12`, ...). Kept deliberately: editing the prompt invalidates the cached screenshot extractions, and a re-extraction changed one case's status (case_63), so the prompt text is pinned.
- **Analysis: 62 hits in 18 files** and **evaluation: 3 hits** (docstrings, intent_eval, scorer). Exploration and scoring code only; the solver imports nothing from `analysis/` or `evaluation/`.
- **Sample answers:** only `code/evaluation/` and `code/analysis/` read `sample_output.csv`. The solver reads `sample_deletion_requests.csv` (inputs only, for `--sample`) and no answers.
- **Intent regex:** the earlier patch copied phrasing from specific requests. It was replaced by a generic fallback (deletion stems in several languages, a negation window before each cue, verification wording). The model reader is the primary path; the fallback disagrees with it on 1 of 550 requests (a "marketing lists only" request). Re-running the 518 after the change: 0 status changes, 0 step changes.

Remaining sample-derived heuristics (generic rules inferred from the samples, not case-specific; listed in `rule_condition_heuristics.md`): resource-prefix to system/category mapping, `contact_lookup`/legacy-contact-index category overrides, the activity time-window account discovery (`WINDOW_MIN`), and the reading rules in `data/states.py`. These can still overfit the 32 samples, so a holdout split is planned.

## Rule-condition reader result

`code/evaluation/conditions_eval.py`: 123 reader items in 114 of 550 cases (101 support-message context, 13 attachment ownership, 9 retention window), average 1.09 rounds per run, 16 tool calls, 0 errors. Answers: support context yes 101/101; attachment yes 5, unclear 8; retention yes 4, unclear 5. No treatment, status or step changed versus the rule defaults. The first prompt version flipped three sample cases (it treated an attachment with the subject's own order as "shared", and one-line support summaries as "no context"); the prompt was corrected on that evidence, so these samples are no longer an independent test of it.

## Link reader (model-assisted evidence linking) result

Goal: tie records that carry no identifier (absent accounts, anonymized analytics, retained audit records) to the subject. `readers/link_reader.py` gets a pool of unlinked, unclaimed resources with activity within +-180 min of `reported_at` and returns yes/no/unclear + confidence + basis; code accepts only pool members, `yes` at or above a confidence floor, passing the existence safeguard. Scored by `code/evaluation/link_eval.py`.

- Sample pools: 110 candidates; 18 of the 21 still-unlinked gold resources were in a pool (3 were not: `account_004`, `audit_record_5569`, `audit_record_6645` appear nowhere in participant data).
- Reader answers: 78 `unclear`, 14 `no`, 17 `yes` (5 high, 12 medium). Real hits: 2 of 5 at high, 4 of 12 at medium (precision 40% / 33%). Average 1.53 rounds.
- Sample step F1: no reader 94.0%, accept high 93.8%, accept medium+ 93.4%; status 32/32 in every variant. The reader finds no more than timing already gave and adds false steps, so it is off by default (`--links model` to enable).
- A deterministic change helped more: an audit/legal record may count as existing when its own snapshot time (inside a later-captured export) is at or before `audit_at`; such records are verified with an empty evidence_id and never cited (F1 92.5 -> 94.0, exact sequence 13 -> 16). This relaxes "state only from files captured <= audit_at" for retained records only; needs the owner's approval.
