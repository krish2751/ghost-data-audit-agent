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
