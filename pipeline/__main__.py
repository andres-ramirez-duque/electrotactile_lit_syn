"""Lab-side pipeline: python -m pipeline <command>   (run from the project folder, with .venv's Python)

  add <doi|url|pdf>      start a paper (stage 1) and run it as far as it can go
  run <citekey>          continue a paper: fetch, text, model request, draft
  attach <citekey> <pdf> supply the PDF for a paper that has no open-access copy
  review <citekey>       show the draft; correct it by editing work/papers/<citekey>/llm_response.json
  approve <citekey>      accept the (possibly corrected) draft
  commit <citekey>       write it to data/, the shared folder and Zotero
  status                 every paper in work/ and its stage
  seed                   rebuild data/ from the 2026-09-17 synthesis (one-off)
  publish                write site/data/*.json from data/ for the static site
  venues                 refresh venue type/name for every paper (Crossref, cached) and show the ranking

Every stage records its result in work/papers/<citekey>/state.json, so a paper can stop anywhere (waiting for a
PDF, for a model answer, for review) and pick up from there.
"""
import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -m pipeline` puts only the project on the path
import config  # noqa: F401  (sets sys.path for the tools and the kernel)
from config import WORK
import dataset
import fetch
import kernel
import llm
import match_library as ml
import resolve
import venues

FRONT_MATTER = 2600  # chars of the paper's start sent with the excerpt, as in the 2026-09-17 extraction


def load(key):
    d = WORK / key
    if not (d / "state.json").exists():
        raise SystemExit(f"no paper '{key}' in {WORK}")
    return d, json.loads((d / "state.json").read_text(encoding="utf-8"))


def save(d, st):
    (d / "state.json").write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")


def taken_keys():
    bib = ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8"))
    keys = set(ml.assign_citekeys(bib).values()) | {p["citekey"] for p in dataset.read("papers.csv")}
    return keys | {p.name for p in WORK.glob("*") if p.is_dir()}


def cmd_add(a):
    src = a.source
    pdf = Path(src) if src.lower().endswith(".pdf") and Path(src).exists() else None
    doi = resolve.find_doi(src)
    if pdf and not doi:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdf))
        doi = resolve.find_doi(" ".join(doc[i].get_textpage().get_text_range() for i in range(min(2, len(doc)))))
    if not doi:
        raise SystemExit("no DOI found; pass the DOI or the paper's doi.org link")
    # papers the lab decided to keep off the site (or out entirely) never re-enter through the pipeline
    excluded = {ml.norm_doi(x["doi"]): x for x in dataset.read("excluded.csv") if x["doi"]}
    if ml.norm_doi(doi) in excluded:
        x = excluded[ml.norm_doi(doi)]
        raise SystemExit(f"{x['citekey']} is excluded ({x['scope']}, {x['decided']}): {x['reason']}. "
                         f"Remove it from data/excluded.csv to add it after all.")
    entry = resolve.to_entry(resolve.crossref(doi))

    # a paper already in the dataset or the .bib keeps its key (re-extraction replaces, never duplicates)
    existing = {ml.norm_doi(p["doi"]): p["citekey"] for p in dataset.read("papers.csv") if p["doi"]}
    bib = ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8"))
    bib_keys = ml.assign_citekeys(bib)
    in_bib = {ml.norm_doi(e["doi"]): bib_keys[e["key"]] for e in bib if e.get("doi") and e["key"] in bib_keys}
    existing.update(in_bib)
    key = existing.get(doi) or resolve.new_citekey(entry, taken_keys())

    d = WORK / key
    d.mkdir(parents=True, exist_ok=True)
    st = {"citekey": key, "input": src, "doi": doi, "entry": entry, "in_bib": doi in in_bib,
          "stage": "resolved", "log": [f"{datetime.date.today()} resolved {doi} -> {key}"]}
    if pdf:
        shutil.copy2(pdf, d / "paper.pdf")
        st["stage"] = "fetched"
    save(d, st)
    print(f"{key}: {entry.get('title', '')[:80]}")
    a.key = key
    cmd_run(a)


def cmd_run(a):
    d, st = load(a.key)
    if st["stage"] == "resolved":
        shared = config.SHARED / f"{a.key}.pdf"
        if shared.exists():  # already in the library
            shutil.copy2(shared, d / "paper.pdf")
            st["log"].append("PDF taken from the shared folder")
        else:
            url, source, version = fetch.open_access_pdf(st["doi"])
            err = fetch.download(url, d / "paper.pdf") if url else "no open-access copy found"
            if err:
                st["log"].append(f"fetch: {err}")
                save(d, st)
                print(f"{a.key}: waiting for a PDF ({err}). Then: python -m pipeline attach {a.key} <file.pdf>")
                return
            st["log"].append(f"PDF from {source} ({version})")
        st["stage"] = "fetched"
    if st["stage"] == "fetched":
        meta = kernel.etd_extract_pdf_text(str(d), out_dir=str(d))  # writes paper.txt
        if meta[0].get("scanned"):
            st["log"].append("image-only PDF: text extraction found almost nothing; needs OCR or manual entry")
        st["pages"], st["chars"] = meta[0].get("pages"), meta[0].get("chars")
        text = (d / "paper.txt").read_text(encoding="utf-8")
        (d / "model_input.txt").write_text(text[:FRONT_MATTER] + "\n\n[...]\n\n" + kernel.etd_parameter_excerpts(text),
                                           encoding="utf-8")
        st["stage"] = "text"
    if st["stage"] in ("text", "classified"):
        ans = llm.classify(a.backend, d, kernel.etd_classification_system(), kernel.etd_classification_tool(),
                           (d / "model_input.txt").read_text(encoding="utf-8"))
        if ans is None:
            save(d, st)
            print(f"{a.key}: model request written to {d / llm.REQUEST}; waiting for {llm.RESPONSE}")
            return
        st["stage"] = "needs_review"
        st["log"].append(f"classified ({a.backend})")
    save(d, st)
    print(f"{a.key}: {st['stage']}")
    if st["stage"] == "needs_review":
        cmd_review(a)


def draft(d, st):
    """Paper row + records from the model answer (as corrected by the reviewer). Deterministic: rerunnable."""
    x = json.loads((d / llm.RESPONSE).read_text(encoding="utf-8"))
    e = st["entry"]
    x.update({"stem": st["citekey"], "doi": st["doi"]})
    tier = kernel.etd_assign_tier(x["contribution_class"], x["stimulation_regime"],
                                  bool(x["delivers_stimulus_to_humans"]), bool(x["has_device_envelope"]))
    paper = {"citekey": st["citekey"], "first_author": ml.citekey(e)[:-4], "year": e.get("year", ""),
             "title": e.get("title", ""), "doi": st["doi"],
             "contribution_class": x["contribution_class"], "secondary_class": x.get("secondary_class", "none"),
             "stimulation_regime": x["stimulation_regime"], "tier": tier,
             "delivers_stimulus_to_humans": bool(x["delivers_stimulus_to_humans"]),
             "n_participants": "" if x.get("n_participants", -1) in (-1, None) else x["n_participants"],
             "has_device_envelope": bool(x["has_device_envelope"]), "key_design_claim": x.get("key_design_claim", ""),
             "obligation_rationale": x.get("obligation_rationale", ""), "in_bib": st["in_bib"],
             "source": f"pipeline_{datetime.date.today()}", "status": "approved"}
    msg = venues.crossref_cached(st["doi"])
    paper["venue_type"], paper["venue"], paper["venue_key"] = (venues.from_crossref(msg) if msg
                                                              else venues.from_bib(e, e.get("journal", "")))
    recs = kernel.etd_split_records([x]).to_dict("records")
    # comparison studies deliver more than one configuration (Daneffel2025: half-sine vs rectangular); the
    # schema holds one, so the others ride in "extra_delivered" as overrides of the first delivered record
    base = next((r for r in recs if r["record_type"] == "delivered"), None)
    for extra in x.get("extra_delivered", []) if base else []:
        recs.append({**base, **extra})
    records = [dataset.derive({**{k: ("" if v != v else v) for k, v in r.items()}, "citekey": st["citekey"]})
               for r in recs]
    return paper, records


def cmd_review(a):
    d, st = load(a.key)
    paper, records = draft(d, st)
    print(f"\n{paper['citekey']}  {paper['title']}\n  class {paper['contribution_class']}  "
          f"(secondary {paper['secondary_class']})  regime {paper['stimulation_regime']}  tier {paper['tier']}")
    print(f"  claim: {paper['key_design_claim']}\n  rationale: {paper['obligation_rationale']}")
    for r in records:
        shown = {k: v for k, v in r.items() if v not in ("", None) and k not in ("citekey", "stem", "first_author",
                 "year", "doi", "contribution_class", "secondary_class", "stimulation_regime", "paper_tier")}
        print(f"  [{r['record_type']}] " + ", ".join(f"{k}={round(v, 3) if isinstance(v, float) else v}"
                                                 for k, v in shown.items() if k != "record_type"))
        if r.get("record_type") == "delivered" and ((r.get("Q_uC") or 0) > 20 or (r.get("D_uC_cm2") or 0) > 1000
                                                     or (r.get("pulse_width_us") or 0) > 5000):
            print("  ! outside the plausible range: check against the paper before approving")
    print(f"\nTo correct: edit {d / llm.RESPONSE}, then rerun review. To accept: python -m pipeline approve {a.key}")


def cmd_approve(a):
    d, st = load(a.key)
    if st["stage"] != "needs_review":
        raise SystemExit(f"{a.key} is at '{st['stage']}', not waiting for review")
    draft(d, st)  # fails loudly on a malformed correction
    st["stage"] = "approved"
    st["log"].append(f"{datetime.date.today()} approved")
    save(d, st)
    print(f"{a.key}: approved. Next: python -m pipeline commit {a.key}")


def cmd_commit(a):
    import library
    d, st = load(a.key)
    if st["stage"] != "approved":
        raise SystemExit(f"{a.key} is at '{st['stage']}'; only approved papers are committed")
    paper, records = draft(d, st)
    dataset.upsert([paper], records)
    msg = library.upsert(a.key, st["entry"], paper, d / "paper.pdf")
    st["stage"] = "committed"
    st["log"].append(f"{datetime.date.today()} committed: {msg}")
    save(d, st)
    print(f"{a.key}: committed ({len(records)} records). {msg}")


def cmd_attach(a):
    d, st = load(a.key)
    shutil.copy2(a.pdf, d / "paper.pdf")
    st["stage"], st["log"] = "fetched", st["log"] + [f"PDF attached by hand: {Path(a.pdf).name}"]
    save(d, st)
    cmd_run(a)


def cmd_status(a):
    for d in sorted(WORK.glob("*/state.json")):
        st = json.loads(d.read_text(encoding="utf-8"))
        print(f"{st['citekey']:22} {st['stage']:13} {st['log'][-1][:90]}")


def cmd_publish(a):
    print("papers, records, completeness rows:", dataset.publish())
    if dataset.stamp_assets():
        print("asset links in site/index.html re-stamped")


def cmd_venues(a):
    dataset.backfill_venues()
    for kind, lst in venues.rank(dataset.read("papers.csv")).items():
        print(f"\n{kind} ({len(lst)} venues)")
        for v in lst[:6]:
            print(f"  {v['rank']:>2}. {v['name']}  ({v['n']})")


def cmd_seed(a):
    print("papers, records:", dataset.seed_from_synthesis())


def main():
    ap = argparse.ArgumentParser(prog="python -m pipeline")
    ap.add_argument("--backend", default="manual", help="language-model backend (default: manual)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add").add_argument("source")
    for c in ("run", "review", "approve", "commit"):
        sub.add_parser(c).add_argument("key")
    p = sub.add_parser("attach")
    p.add_argument("key")
    p.add_argument("pdf")
    sub.add_parser("status")
    sub.add_parser("seed")
    sub.add_parser("publish")
    sub.add_parser("venues")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
