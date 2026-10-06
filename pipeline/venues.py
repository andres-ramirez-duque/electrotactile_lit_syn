"""Venue type and canonical name for each paper, so venues can be counted and ranked.

Crossref's record for the DOI is the authority (cached in work/crossref/, never published); the curated .bib is the
fallback for papers without a DOI. Journals are keyed by their first ISSN, which merges renamed titles of the same
journal (IEEE Trans. Bio-Medical Engineering = Biomedical Engineering). Conferences are keyed by series, because
Crossref titles carry the year and edition ("2015 37th Annual International Conference of the IEEE EMBS").
"""
import html
import json
import re
import urllib.parse

from config import PROJECT

CACHE = PROJECT / "work" / "crossref"

# (pattern on the proceedings or book title, series name). First match wins.
SERIES = [
    (r"\bCHI\b|Human Factors in Computing Systems", "ACM CHI"),
    (r"Engineering in Medicine and Biology|\bIEMBS\b|\bEMBC\b", "IEEE EMBC"),
    (r"Conference on Neural Engineering", "IEEE/EMBS Neural Engineering (NER)"),
    (r"World Haptics", "IEEE World Haptics (WHC)"),
    (r"Haptic Interfaces for Virtual Environment", "IEEE Haptics Symposium"),
    (r"^Haptics: ", "EuroHaptics"),  # its LNCS volumes are titled "Haptics: ..."
    (r"Intelligent Robotics and Applications", "ICIRA"),
    (r"User Interface Software and Technology", "ACM UIST"),
    (r"Nordic Conference on Human-Computer", "NordiCHI"),
    (r"Intelligent Robots and Systems", "IEEE/RSJ IROS"),
    (r"IEEE Virtual Reality", "IEEE VR"),
    (r"Biomedical Robotics and Biomechatronics", "IEEE BioRob"),
    (r"Electronics, Circuits and Systems", "IEEE ICECS"),
    (r"Automation Science and Engineering", "IEEE CASE"),
    (r"Power Electronics Specialists", "IEEE PESC"),
    (r"Evaluation and Assessment in Software Engineering", "EASE"),
    (r"Electrical, Electronic and Comput|IcETRAN", "IcETRAN"),
]
# Crossref often names only the publisher for preprints (TechRxiv is "IEEE"); the DOI prefix names the server
PREPRINT_PREFIXES = {"10.36227/techrxiv": "TechRxiv", "10.1101/": "bioRxiv", "10.48550/arxiv": "arXiv",
                     "10.21203/rs": "Research Square", "10.5281/zenodo": "Zenodo", "10.2139/ssrn": "SSRN", "10.31219/osf": "OSF Preprints"}
TYPES = {"journal-article": "journal", "proceedings-article": "conference", "book-chapter": "book",
         "book": "book", "monograph": "book", "posted-content": "preprint", "dissertation": "thesis",
         "report": "other", "standard": "other"}


def series(title):
    for pat, name in SERIES:
        if re.search(pat, title, re.I):
            return name
    # unknown series: drop years, editions and "Proceedings of the" so editions of one series still merge
    t = re.sub(r"\b(19|20)\d\d\b|\b\d+(st|nd|rd|th)\b|^Proceedings( of the)?|\(Cat\. No\.[^)]*\)", "", title, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" ,.-") or "Unknown conference"


def crossref_cached(doi):
    """Crossref message for a DOI, from the cache or the API (then cached); None if Crossref doesn't have it
    (arXiv DOIs are registered with DataCite). Misses are cached too, so they aren't retried every run."""
    import urllib.error
    import resolve
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (urllib.parse.quote(doi.lower(), safe="") + ".json")
    if not f.exists():
        try:
            msg = resolve.crossref(doi)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            msg = {"_not_in_crossref": True}
        f.write_text(json.dumps(msg), encoding="utf-8")
    msg = json.loads(f.read_text(encoding="utf-8"))
    return None if msg.get("_not_in_crossref") else msg


def from_crossref(m):
    """(venue_type, venue_name, venue_key) from a Crossref message."""
    kind = TYPES.get(m.get("type"), "other")
    titles = [html.unescape(t) for t in m.get("container-title") or []]
    if kind == "preprint":
        doi = m.get("DOI", "").lower()
        server = (next((s for pre, s in PREPRINT_PREFIXES.items() if doi.startswith(pre)), None)
                  or (m.get("institution") or [{}])[0].get("name") or "Preprint")
        return "preprint", server, "preprint:" + server.lower()
    if kind == "book" and titles and titles[0] == "Lecture Notes in Computer Science" and len(titles) > 1:
        kind, titles = "conference", titles[1:]  # LNCS volumes are conference proceedings
    if kind == "conference":
        name = series(" ".join(titles) or (m.get("event") or {}).get("name", ""))
        return "conference", name, "conf:" + name.lower()
    if kind == "journal":
        issn = (m.get("ISSN") or [""])[0]
        name = titles[0] if titles else "Unknown journal"
        return "journal", name, "issn:" + issn if issn else "journal:" + name.lower()
    name = titles[-1] if titles else m.get("publisher", "Unknown")
    return kind, name, f"{kind}:{name.lower()}"


def from_bib(e, hint=""):
    """Fallback for papers without a DOI: the .bib entry, else the free-text venue from the 2026-09-17 tables."""
    t = (e or {}).get("entrytype", "")
    doi = (e or {}).get("doi", "").lower()
    server = next((s for pre, s in PREPRINT_PREFIXES.items() if doi.startswith(pre)), None)
    if server:
        return "preprint", server, "preprint:" + server.lower()
    if t == "article" and re.search(r"Universit|Graduate School|Department|Institute of", e.get("journal", "")):
        return "other", "Technical report", "other:report"  # an institution in the journal field: a report
    if t == "article" and e.get("journal"):
        return "journal", e["journal"], "journal:" + e["journal"].lower()
    if t == "inproceedings" and e.get("booktitle") and "Texas Instrument" not in e["booktitle"]:
        name = series(e["booktitle"])
        return "conference", name, "conf:" + name.lower()
    if re.search(r"thesis", hint, re.I) or t in ("phdthesis", "mastersthesis"):
        return "thesis", hint or "Thesis", "thesis"
    if re.search(r"tech ?note|application note|Texas Instrument", hint + " " + (e or {}).get("booktitle", ""), re.I):
        return "other", "Texas Instruments technical note", "other:ti-technote"
    return "other", hint or "Unknown venue", "other:unknown"


def rank(papers):
    """Venues per type, most papers first; journal names unified to the most recent title under one ISSN."""
    groups = {}
    for p in papers:
        if not p.get("venue_key"):
            continue
        g = groups.setdefault(p["venue_key"], {"type": p["venue_type"], "names": [], "citekeys": []})
        g["names"].append((int(p.get("year") or 0), p["venue"]))
        g["citekeys"].append(p["citekey"])
    out = {}
    for key, g in groups.items():
        name = max(g["names"])[1]
        out.setdefault(g["type"], []).append({"name": name, "n": len(g["citekeys"]), "citekeys": sorted(g["citekeys"])})
    for lst in out.values():
        lst.sort(key=lambda v: (-v["n"], v["name"]))
        # competition ranking: ties share a rank (1, 2, 2, 4)
        for i, v in enumerate(lst):
            v["rank"] = lst[i - 1]["rank"] if i and lst[i - 1]["n"] == v["n"] else i + 1
    return out
