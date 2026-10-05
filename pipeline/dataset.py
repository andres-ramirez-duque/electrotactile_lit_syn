"""The published dataset: data/papers.csv (one row per paper) and data/records.csv (one row per record).

A paper can carry several records (delivered dose, device envelope, interface), each scored against its own
obligation; see pipeline/extraction/SKILL.md. Derived dose columns follow the 2026-09-17 synthesis exactly
(upper end of each delivered range, Shannon k=1.5 as an external reference), so new papers stay comparable.
"""
import csv
import math
import re
import shutil

from config import DATA, SYNTHESIS

PAPER_COLS = ["citekey", "first_author", "year", "title", "venue", "venue_type", "venue_key", "doi", "contribution_class",
              "secondary_class", "stimulation_regime", "tier", "delivers_stimulus_to_humans", "n_participants",
              "has_device_envelope", "key_design_claim", "obligation_rationale", "in_bib", "source", "status"]
RECORD_COLS = ["citekey", "record_type", "tier", "dose_group", "n_participants", "body_site", "waveform_polarity",
               "current_mA_min", "current_mA_max", "pulse_width_us", "pulse_rate_Hz", "area_mm2", "area_source",
               "J_peak_mA_cm2", "Q_uC", "D_uC_cm2", "Javg_mA_cm2", "frac_shannon_k15", "density_band",
               "compliance_V", "pulse_width_us_min", "pulse_width_us_max", "pulse_rate_Hz_min", "pulse_rate_Hz_max",
               "bandwidth_or_carrier_Hz", "n_channels", "output_impedance_Mohm", "load_tested",
               "impedance_reported", "measurement_freq_Hz", "electrode_material", "interface_contribution"]


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or x in (-1.0, 0.0) else x


def derive(rec):
    """Dose metrics for one delivered record, in place. Same formulas as table1_stimulation_parameters.csv."""
    if rec.get("record_type") != "delivered":
        return rec
    i = _num(rec.get("current_mA_max")) or _num(rec.get("current_mA_min"))
    pw, prr, area = _num(rec.get("pulse_width_us")), _num(rec.get("pulse_rate_Hz")), _num(rec.get("area_mm2"))
    q = i * pw / 1000.0 if i and pw else None
    a_cm2 = area / 100.0 if area else None
    rec["Q_uC"] = q
    rec["J_peak_mA_cm2"] = i / a_cm2 if i and a_cm2 else None
    rec["D_uC_cm2"] = d = q / a_cm2 if q and a_cm2 else None
    rec["Javg_mA_cm2"] = i * pw * 1e-6 * prr / a_cm2 if i and pw and prr and a_cm2 else None
    rec["frac_shannon_k15"] = d / (10 ** 1.5 / q) if d and q else None
    rec["density_band"] = ("" if d is None else "I_low_density_large_area" if d < 10
                           else "II_display_scale" if d < 100 else "III_point_contact")
    return rec


def read(name):
    p = DATA / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def write(name, rows, cols):
    DATA.mkdir(exist_ok=True)
    with open(DATA / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def upsert(papers_new, records_new):
    """Replace a paper's row and all its records (re-extraction supersedes, never duplicates)."""
    keys = {p["citekey"] for p in papers_new}
    papers = [p for p in read("papers.csv") if p["citekey"] not in keys] + papers_new
    records = [r for r in read("records.csv") if r["citekey"] not in keys] + records_new
    papers.sort(key=lambda p: p["citekey"].lower())
    records.sort(key=lambda r: (r["citekey"].lower(), r["record_type"]))
    write("papers.csv", papers, PAPER_COLS)
    write("records.csv", records, RECORD_COLS)


def seed_from_synthesis():
    """One-off: load the 2026-09-17 synthesis (table4 papers, table1 records) under the current citekeys.

    Papers matched to the curated .bib take its key; the 11 table4 papers not in the .bib get an AuthorYear key
    that avoids every .bib key, and in_bib=False so they can be reviewed (out/TODO_review_not_in_bib.csv).
    """
    import match_library as ml
    bib = ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8"))
    keys = ml.assign_citekeys(bib)
    t4 = list(csv.DictReader(open(SYNTHESIS / "tables" / "table4_corpus_classification.csv", encoding="utf-8")))
    t1 = list(csv.DictReader(open(SYNTHESIS / "tables" / "table1_stimulation_parameters.csv", encoding="utf-8")))
    match = {r["pdf"]: r for r in csv.DictReader(open(ml.OUT, encoding="utf-8"))}
    pdf_stems = {ml.stem_norm(p[:-4]): p for p in match}
    taken = set(keys.values())

    by_doi = {ml.norm_doi(e.get("doi")): e["key"] for e in bib if e.get("doi") and e["key"] in keys}
    stem_key, papers, seen, dup_stems = {}, [], set(), set()
    # papers the lab decided to leave out (data/excluded.csv) stay out on every rebuild
    excl = read("excluded.csv")
    excl_doi = {ml.norm_doi(x["doi"]) for x in excl if x["doi"]}
    excl_title = {ml.stem_norm(x["title"]) for x in excl}
    for r in t4:
        if ml.norm_doi(r["doi"]) in excl_doi or ml.stem_norm(r["title"]) in excl_title:
            dup_stems.add(r["stem"])  # drops its records too
            continue
        pdf = next((p for s, p in pdf_stems.items() if s.startswith(ml.stem_norm(r["stem"]))), None)
        m = match.get(pdf, {})
        # a table4 row whose file was since renamed (Zhou2022) or skipped as a duplicate copy (TaxTec = TacTex)
        # still resolves through its DOI
        bk = m["bib_key"] if m.get("status") == "OK" else by_doi.get(ml.norm_doi(r["doi"]))
        if bk:
            ck, in_bib = keys[bk], True
        else:
            base = re.sub(r"[^A-Za-z]", "", ml.ascii_fold(r["first_author"])) + r["year"]
            ck = next(base + s for s in [""] + list("abcdefghijklmnopqrstuvwxyz") if base + s not in taken)
            taken.add(ck)
            in_bib = False
        stem_key[r["stem"]] = ck
        if ck in seen:  # table4 counted REF-067/REF-090 (byte-identical TacTex PDFs) twice
            dup_stems.add(r["stem"])
            continue
        seen.add(ck)
        papers.append({**r, "citekey": ck, "in_bib": in_bib, "key_design_claim": "",
                       "source": f"synthesis_2026-09-17_{r['added_in']}", "status": "approved"})
    records = [{**r, "citekey": stem_key[r["stem"]]} for r in t1 if r["stem"] not in dup_stems]
    # papers added through the pipeline since the synthesis are not in table4: keep them and their records
    later = [p for p in read("papers.csv") if p.get("source", "").startswith("pipeline_")]
    keep = {p["citekey"] for p in later}
    papers = [p for p in papers if p["citekey"] not in keep] + later
    records = [r for r in records if r["citekey"] not in keep] + [r for r in read("records.csv") if r["citekey"] in keep]
    write("papers.csv", sorted(papers, key=lambda p: p["citekey"].lower()), PAPER_COLS)
    write("records.csv", sorted(records, key=lambda r: (r["citekey"].lower(), r["record_type"])), RECORD_COLS)
    backfill_venues()
    return len(papers), len(records)


def backfill_venues():
    """Venue type, canonical name and grouping key for every paper; also takes a missing DOI from the .bib."""
    import match_library as ml
    import venues
    bib = ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8"))
    keys = ml.assign_citekeys(bib)
    by_key = {keys[e["key"]]: e for e in bib if e["key"] in keys}
    papers = read("papers.csv")
    for p in papers:
        e = by_key.get(p["citekey"], {})
        if not p["doi"] and e.get("doi"):
            p["doi"] = ml.norm_doi(e["doi"])
        msg = venues.crossref_cached(p["doi"]) if p["doi"] else None
        vt, vn, vk = venues.from_crossref(msg) if msg else venues.from_bib({**e, "doi": p["doi"]}, p.get("venue", ""))
        p.update(venue_type=vt, venue=vn, venue_key=vk)
    write("papers.csv", papers, PAPER_COLS)
    return papers



def _typed(row):
    out = {}
    for k, v in row.items():
        if v in ("True", "False"):
            out[k] = v == "True"
        elif v in ("", "nan", "None"):
            out[k] = None
        else:
            try:
                out[k] = float(v) if k not in ("citekey", "year", "doi", "title") else v
            except ValueError:
                out[k] = v
    return out


def publish():
    """data/*.csv -> site/data/*.json. Only the published dataset goes out: no paths, PDFs, text or keys."""
    import json
    import pandas as pd
    import kernel
    from config import SITE_DATA
    papers = [_typed(p) for p in read("papers.csv")]
    records = [_typed(r) for r in read("records.csv")]
    for p in papers:
        p.pop("source", None)
        p.pop("status", None)
    comp = kernel.etd_reporting_completeness(pd.DataFrame(records)).to_dict("records")
    import venues
    ranked = venues.rank(read("papers.csv"))
    standard = {tier: [{"label": l, "field": c} for l, c, _k in fields]
                for tier, fields in kernel.etd_obligation_fields().items()}
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    for p in papers:
        p.pop("venue_key", None)
    for name, obj in {"papers": papers, "records": records, "completeness": comp, "standard": standard,
                      "venues": ranked}.items():
        (SITE_DATA / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                                                           allow_nan=False, default=str), encoding="utf-8")
    for name in ("papers.csv", "records.csv"):  # the downloadable dataset, same files as data/
        shutil.copy2(DATA / name, SITE_DATA / name)
    return len(papers), len(records), len(comp)


def stamp_assets():
    """Add ?v=<content hash> to the asset links in site/index.html, so browsers fetch a changed script or
    stylesheet at once instead of serving GitHub Pages' 10-minute cached copy."""
    import hashlib
    from config import PROJECT
    site = PROJECT / "site"
    page = (site / "index.html").read_text(encoding="utf-8")

    def stamp(m):
        f = site / m.group(1)
        return f'"{m.group(1)}?v={hashlib.sha1(f.read_bytes()).hexdigest()[:8]}"' if f.exists() else m.group(0)
    new = re.sub(r'"(assets/[\w.-]+\.(?:js|css))(?:\?v=\w+)?"', stamp, page)
    (site / "index.html").write_text(new, encoding="utf-8")
    return new != page
