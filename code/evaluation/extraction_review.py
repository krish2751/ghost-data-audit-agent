"""Review of what the pipeline read from the 11 screenshots (model extraction, cached) and the 4 PDFs (pypdf text), and
where each fact is used. For verification only: reads the pipeline's inputs and outputs, changes nothing.

Usage: .venv/bin/python code/evaluation/extraction_review.py   (writes code/evaluation/extraction_review.md)

For every extracted ID the report counts the participant files that contain it besides the file it was read from.
An ID found nowhere else is flagged: it is the most likely misread (or a value that only this artifact shows).
Uses per fact: steps that cite the file for that resource (output.csv and the sample predictions), cases whose subject
identifiers match the extracted record (identifier link), and cases that include the resource with the file that
decided its state.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screenshots  # noqa: E402
from data import loader  # noqa: E402
from data.evidence_index import RES_RX, prefix_of  # noqa: E402
from schema import PREFIX_INFO  # noqa: E402
from data.states import reading  # noqa: E402
from fallback import Context, _matcher, solve_all  # noqa: E402
from readers.intent_reader import prefetch_intents  # noqa: E402

ROOT = loader.ROOT
DS = loader.DS
OUT = ROOT / "code" / "evaluation" / "extraction_review.md"
ANSWER_FILE = "dataset/sample_output.csv"
ID_RX = [RES_RX, re.compile(r"\buser_\d+\b"), re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), re.compile(r"\b[0-9a-f]{64}\b"),
         re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*-\d{4,}\b"), re.compile(r"\+\d[\d ()-]{7,}\d")]
ID_FIELDS = ("email", "phone", "email_hash", "user_id", "customer_reference", "subject_reference")
SEP = {"Record", "Detail"}


def cell(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def ids_in(text):
    out = []
    for rx in ID_RX:
        for m in rx.finditer(text or ""):
            v = m.group(0).strip()
            if v not in out:
                out.append(v)
    return out


def digits(s):
    return re.sub(r"\D", "", s)


class Corpus:
    """Lowercase text of every participant file (PDFs as pypdf text) plus the cached screenshot extractions."""

    def __init__(self, ctx):
        self.src = {}
        for p in sorted(DS.glob("*.csv")):
            self.src[f"dataset/{p.name}"] = p.read_text(encoding="utf-8")
        for fid, m in ctx.man.items():
            path = DS / m["file_path"]
            if path.suffix == ".pdf":
                self.src[fid] = ctx.pdf_text(fid)
            elif path.suffix == ".png":
                try:
                    data, _ = screenshots.extract({"file_id": fid, "file_path": m["file_path"]})
                except Exception:
                    data = None
                self.src[fid] = json.dumps(data, ensure_ascii=False)
            else:
                self.src[fid] = path.read_text(encoding="utf-8", errors="replace")
        self.low = {k: v.lower() for k, v in self.src.items()}
        self.dig = {k: digits(v) for k, v in self.src.items()}
        self.png = {fid for fid, m in ctx.man.items() if m["file_path"].endswith(".png")}

    def where(self, value, own):
        """(dataset sources, other screenshot extractions, in answer file) containing value, excluding `own`."""
        v = value.lower()
        phone = bool(re.fullmatch(r"\+?[\d ()-]{9,}", value))
        hit = [k for k in self.low if k != own and (v in self.low[k] or (phone and digits(value) in self.dig[k]))]
        return ([k for k in hit if k not in self.png and k != ANSWER_FILE], [k for k in hit if k in self.png], ANSWER_FILE in hit)


def presence(corpus, value, own, fid_label):
    if any(ch in value for ch in "*•…"):
        return "masked value", ""
    ds, png, ans = corpus.where(value, own)
    if ds:
        return f"{len(ds)} file(s): " + ", ".join(fid_label(k) for k in ds[:4]) + (" …" if len(ds) > 4 else ""), ""
    note = []
    if png:
        note.append("other screenshot extraction(s): " + ", ".join(png))
    if ans:
        note.append("sample_output.csv")
    return ("only in " + "; ".join(note)) if note else "nowhere else", "**FLAG**"


def main():
    samples, full = loader.requests(sample=True), loader.requests()
    reqs = samples + full
    sample_ids = {r["case_id"] for r in samples}
    by_case = {r["case_id"]: r for r in reqs}
    ctx = Context()
    prefetch_intents(ctx, reqs)
    solved = solve_all(ctx, reqs)
    corpus = Corpus(ctx)
    label = lambda c: f"{c} (sample)" if c in sample_ids else c
    fid_label = lambda k: k if k.startswith("dataset/") else f"{k} `{Path(ctx.man[k]['file_path']).name}`"

    cites = defaultdict(list)    # (file_id, resource_id) -> step refs
    member = defaultdict(list)   # resource_id -> (case, deciding file)
    for cid, (res, steps) in solved.items():
        for s in steps:
            if s["evidence_id"]:
                cites[(s["evidence_id"], s["resource_id"])].append(f"{label(cid)} step {s['step_no']} {s['operation']}")
        for d in res["resources"]:
            member[d["resource_id"]].append((cid, d["verify_evidence"] or d["finding_evidence"] or "no file"))
    matchers = {cid: _matcher(ctx.ids.tokens(res["uid"], by_case[cid]["audit_at"]))
                for cid, (res, _) in solved.items() if "uid" in res}

    def uses(fid, rid, obs):
        out = list(cites.get((fid, rid), []))
        if prefix_of(rid or "") not in PREFIX_INFO:
            return ["not a record kind the pipeline tracks (ignored)"]
        if obs is not None:
            for cid, rx in sorted(matchers.items()):
                m = rx.findall(obs.text)
                if m:
                    out.append(f"identifier link to {label(cid)} (`{solved[cid][0]['uid']}`) via {', '.join(sorted(set(m)))}")
        for cid, f in sorted(member.get(rid, [])):
            if f != fid:
                out.append(f"in {label(cid)}, state decided by {f}")
        return out

    flags, body = [], []
    obs_by = defaultdict(dict)
    for o in ctx.ix.obs:
        if o.resource_id:
            obs_by[o.file_id].setdefault(o.resource_id, o)

    # ---------------------------------------------------------------- screenshots
    body += ["## Screenshots (model extraction, `code/screenshots.py`, cached API answers)", ""]
    for row in screenshots.png_files():
        fid = row["file_id"]
        data, info = screenshots.extract(row)
        body += [f"### {fid} `{Path(row['file_path']).name}`", "",
                 f"captured_at {row['captured_at']}, origin `{row['origin']}`; screen \"{cell(data.get('screen_title'))}\" "
                 f"(`{cell(data.get('system'))}`), screen timestamp {data.get('screen_timestamp')}; "
                 f"{len(data.get('records', []))} record(s); extraction tokens {info['usage']['input_tokens']} in / "
                 f"{info['usage']['output_tokens']} out.", ""]
        if data.get("filters_or_query"):
            body.append(f"Query/filter shown: `{cell(data['filters_or_query'])}`")
        if data.get("empty_state_text"):
            body.append(f"Empty-state text: \"{cell(data['empty_state_text'])}\"")
        for rec in data.get("records", []):
            rid = rec.get("resource_id")
            o = obs_by[fid].get(rid)
            body += ["", f"**Record `{rid}`** — pipeline reading: `{reading(o) if o else 'not indexed'}`", "",
                     "| field | value | elsewhere in the dataset | flag |", "|---|---|---|---|"]
            vals = [("resource_id", rid)] if rid else []
            vals += [(f"identifiers.{k}", v) for k, v in (rec.get("identifiers") or {}).items() if v]
            vals += [(f"status.{k}", v) for k, v in (rec.get("status_fields") or {}).items() if v is not None]
            vals += [(f"time.{k}", v) for k, v in (rec.get("timestamps") or {}).items() if v]
            seen_vals = {str(v) for _, v in vals}
            for k, v in (rec.get("other_fields") or {}).items():
                for x in ids_in(str(v)):
                    if x not in seen_vals:
                        vals.append((f"other.{k}", x)); seen_vals.add(x)
            u = uses(fid, rid, o)
            for k, v in vals:
                is_id = k == "resource_id" or k.split(".", 1)[-1] in ID_FIELDS or k.startswith("other.")
                if is_id:
                    where, flag = presence(corpus, str(v), fid, fid_label)
                    if flag:
                        flags.append((fid, Path(row["file_path"]).name, rid, k, v, where, u))
                else:
                    where, flag = "", ""
                body.append(f"| {k} | `{cell(v)}` | {cell(where)} | {flag} |")
            body += ["", "Used by: " + ("; ".join(u) if u else "nothing (no case links or cites this record)")]
        screen_ids = [x for x in ids_in((data.get("filters_or_query") or "") + " " + (data.get("notes") or ""))
                      if x not in {r.get("resource_id") for r in data.get("records", [])}]
        if screen_ids:
            body += ["", "IDs in the screen's query/notes (not records; not used for linking):", "",
                     "| ID | elsewhere in the dataset | flag |", "|---|---|---|"]
            for x in screen_ids:
                where, flag = presence(corpus, x, fid, fid_label)
                if flag:
                    flags.append((fid, Path(row["file_path"]).name, "(screen notes)", "notes", x, where, []))
                body.append(f"| `{cell(x)}` | {cell(where)} | {flag} |")
        body.append("")

    # ---------------------------------------------------------------- PDFs
    body += ["## PDFs (pypdf text layer, no model)", ""]
    for fid, m in sorted(ctx.man.items()):
        if not m["file_path"].endswith(".pdf"):
            continue
        text = ctx.pdf_text(fid)
        lines = [l.strip() for l in text.splitlines() if l.strip() and l.strip() not in SEP]
        body += [f"### {fid} `{Path(m['file_path']).name}`", "",
                 f"captured_at {m['captured_at']}, origin `{m['origin']}`; {len(lines)} text lines.", "",
                 "| line | text | IDs in the line |", "|---|---|---|"]
        for i, l in enumerate(lines, 1):
            body.append(f"| {i} | {cell(l)} | {', '.join(f'`{x}`' for x in ids_in(l)) or ''} |")
        body += ["", "| extracted ID | elsewhere in the dataset | flag | used by |", "|---|---|---|---|"]
        for x in ids_in(text):
            where, flag = presence(corpus, x, fid, fid_label)
            u = uses(fid, x, obs_by[fid].get(x)) if RES_RX.fullmatch(x) else \
                [f"identifier of {label(c)}" for c, rx in sorted(matchers.items()) if rx.fullmatch(x.lower())]
            if flag:
                flags.append((fid, Path(m["file_path"]).name, "-", "pdf text", x, where, u))
            body.append(f"| `{cell(x)}` | {cell(where)} | {flag} | {cell('; '.join(u)) or '-'} |")
        rids = sorted(obs_by[fid])
        body += ["", f"Resources indexed from this PDF: {', '.join(f'`{r}`' for r in rids) or 'none'}."]
        for r in rids:
            u = uses(fid, r, obs_by[fid][r])
            body.append(f"- `{r}` (reading `{reading(obs_by[fid][r])}`): " + ("; ".join(u) if u else "not used"))
        body.append("")

    mism = []
    for (fid, rid), refs in sorted(cites.items()):
        o = obs_by[fid].get(rid)
        if o is None or o.kind not in ("png", "pdf"):
            continue
        idv = [v for k, v in o.attrs.items() if k in ID_FIELDS and v]
        for ref in refs:
            cid = ref.split(" ")[0]
            if idv and cid in matchers and not matchers[cid].search(o.text):
                mism.append(f"| {fid} | `{rid}` | {cell(ref)} | `{solved[cid][0]['uid']}` | "
                            f"{', '.join(f'`{cell(v)}`' for v in idv)} | {solved[cid][0]['resources'] and next((d['why'] for d in solved[cid][0]['resources'] if d['resource_id'] == rid), '?')} |")
    used = lambda f: bool(f[6]) and f[6] != ["not a record kind the pipeline tracks (ignored)"]
    head = ["# Extraction review: screenshots and PDFs", "",
            "Generated by `code/evaluation/extraction_review.py` from the cached screenshot extractions, the pypdf text "
            "and the current pipeline outputs (518 requests and 32 samples, solved in-process from cached model answers). "
            "\"Elsewhere in the dataset\" counts participant files other than the source file itself; other screenshot "
            "extractions and `sample_output.csv` are reported separately, since they are not independent evidence. An ID "
            "found in no other participant file is flagged. Masked values (with `*`) are not searched.", "",
            f"## Flagged IDs ({len(flags)}, {sum(1 for f in flags if used(f))} of them used by a case)", "",
            "Flags whose record is used by a case come first: a misread there would change an output. The others are "
            "records shown only in that artifact (other customers on the same screen, order or ticket numbers) that no "
            "case links or cites.", ""]
    flags.sort(key=lambda f: (not used(f), f[0]))
    if flags:
        head += ["| file | record | field | value | found | used by |", "|---|---|---|---|---|---|"]
        head += [f"| {f} `{n}` | `{r}` | {k} | `{cell(v)}` | {cell(w)} | {cell('; '.join(u)) or '-'} |"
                 for f, n, r, k, v, w, u in flags]
    else:
        head.append("None: every extracted ID appears in at least one other participant file.")
    head += ["", f"## Cited records whose extracted identifiers do not match the citing case's subject ({len(mism)})", "",
             "The record is linked another way (for example a LINK_RESOURCE_IDENTITY activity row), but the identifiers "
             "read from the artifact belong to someone else or were misread.", ""]
    head += (["| file | record | step | case subject | extracted identifiers | linked by |", "|---|---|---|---|---|---|"] + mism
             if mism else ["None."])
    OUT.write_text("\n".join(head + [""] + body) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(flags)} flagged IDs")


if __name__ == "__main__":
    main()
