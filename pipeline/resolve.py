"""Stage 1: turn a DOI, a URL or a PDF into bibliographic metadata and a citation key."""
import json
import re
import urllib.parse
import urllib.request

import match_library as ml

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)
CROSSREF_TYPES = {"journal-article": "article", "proceedings-article": "inproceedings", "book-chapter": "inbook",
                  "posted-content": "misc", "book": "book", "report": "techreport", "standard": "techreport"}


def find_doi(s):
    """DOI from a DOI string, a doi.org/publisher URL, or the first pages of a PDF's text."""
    s = urllib.parse.unquote(s)
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", s)
    if m:
        return "10.48550/arXiv." + m.group(1)
    m = DOI_RE.search(s)
    return m.group(0).rstrip(".,;)]").lower() if m else None


def crossref(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    req = urllib.request.Request(url, headers={"User-Agent": "BodyElectric-library-sync/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))["message"]


def to_entry(msg):
    """Crossref record -> the same dict shape match_library.parse_bib produces, so one code path serves both."""
    authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") if a.get("family")
                           else a.get("name", "") for a in msg.get("author", []))
    parts = (msg.get("issued") or msg.get("published") or {}).get("date-parts", [[None]])[0]
    container = (msg.get("container-title") or [""])[0]
    etype = CROSSREF_TYPES.get(msg.get("type"), "misc")
    e = {"entrytype": etype, "author": authors, "title": (msg.get("title") or [""])[0],
         "year": str(parts[0] or ""), "doi": msg.get("DOI", "").lower(), "url": msg.get("URL", ""),
         "publisher": msg.get("publisher", ""), "volume": msg.get("volume", ""), "number": msg.get("issue", ""),
         "pages": msg.get("page", ""), "issn": (msg.get("ISSN") or [""])[0]}
    if len(parts) > 1 and parts[1]:
        e["month"] = "jan feb mar apr may jun jul aug sep oct nov dec".split()[parts[1] - 1]
    e["journal" if etype == "article" else "booktitle"] = container
    return {k: v for k, v in e.items() if v}


def new_citekey(entry, taken):
    """AuthorYear plus the first free letter, against every key already in use (dataset, .bib, Zotero)."""
    base = ml.citekey(entry)
    return next(base + s for s in [""] + list("abcdefghijklmnopqrstuvwxyz") if base + s not in taken)
