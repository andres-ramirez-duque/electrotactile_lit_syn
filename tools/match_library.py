"""Dry run: match every PDF in the reference folder to a .bib entry and propose a citekey name.

Writes out/library_match.csv for human review. Touches nothing in the source folder.

Matching order, most to least trustworthy:
  1. table4 'stem' == PDF stem -> its DOI -> .bib entry with that DOI
  2. table4 row found but its DOI is not in the .bib -> fuzzy match on table4's full title
  3. no table4 row -> fuzzy match of the filename against .bib titles, flagged for review.
table4 stems are the filename with punctuation replaced by '_' and truncated, hence stem_norm().
"""
import argparse, csv, difflib, re, unicodedata
from pathlib import Path

from local import LAB_ROOT as ROOT
REFS = ROOT / "References"
TABLE4 = ROOT / "Literature synthesis and design principles" / "tables" / "table4_corpus_classification.csv"
OVERRIDES = Path(__file__).resolve().parent / "match_overrides.csv"  # pdf,bib_key|skip,note
OUT = Path(__file__).resolve().parent.parent / "out" / "library_match.csv"

STOP = {"a", "an", "the", "of", "on", "for", "and", "in", "to", "with", "via", "using", "based", "its", "by", "from", "toward", "towards"}


def ascii_fold(s):
    s = re.sub(r"\\['`^\"~=.uvHc]\{?(\w)\}?", r"\1", s)  # LaTeX accents
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_doi(d):
    d = (d or "").strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)


def parse_bib(text):
    """Minimal brace-aware BibTeX reader; enough for this file, avoids a dependency."""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        i, depth = m.end(), 1
        start = i
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[start:i - 1]
        fields, j = {}, 0
        for fm in re.finditer(r"(\w+)\s*=\s*", body):
            if fm.start() < j:
                continue
            k, p = fm.group(1).lower(), fm.end()
            if p < len(body) and body[p] == "{":
                d, q = 1, p + 1
                while q < len(body) and d:
                    d += {"{": 1, "}": -1}.get(body[q], 0)
                    q += 1
                v = body[p + 1:q - 1]
            elif p < len(body) and body[p] == '"':
                q = body.index('"', p + 1) + 1
                v = body[p + 1:q - 1]
            else:
                q = p
                while q < len(body) and body[q] not in ",\n":
                    q += 1
                v = body[p:q]
            fields[k] = re.sub(r"\s+", " ", v.replace("{", "").replace("}", "")).strip()
            j = q
        entries.append({**fields, "entrytype": m.group(1).lower(), "key": m.group(2)})
    return entries


def stem_norm(s):
    return re.sub(r"[^a-z0-9]+", "", ascii_fold(s).lower())


def title_score(a, b):
    return difflib.SequenceMatcher(None, " ".join(tokens(a)), " ".join(tokens(b))).ratio()


def tokens(s):
    s = ascii_fold(s).lower()
    s = re.sub(r"^(ref)[-_ ]?\w{1,4}[-_ ]", "", s)  # drop REF-012_ prefixes
    return [t for t in re.findall(r"[a-z]+", s) if t not in STOP and len(t) > 1]


def citekey(entry):
    """AuthorYear base, as in the curated .bib (Malesevic2021); assign_citekeys adds the a/b/c."""
    author = entry.get("author", "") or entry.get("editor", "")
    first = author.split(" and ")[0].strip()
    words = first.split()
    # .bib people are "Last, First" or "R. M. Strong"; three+ whole words with no comma is an organisation -> IEC
    if "," not in first and len(words) > 2 and not any(w.endswith(".") or len(w) == 1 for w in words):
        last = "".join(w[0] for w in first.split() if w[0].isupper())
    else:
        last = first.split(",")[0] if "," in first else (first.split()[-1] if first.split() else "Anon")
    last = re.sub(r"[^A-Za-z]", "", ascii_fold(last)) or "Anon"
    year = re.sub(r"\D", "", entry.get("year", ""))[:4] or "nd"
    return f"{last}{year}"


def assign_citekeys(bib):
    """Malesevic2021, Malesevic2021a, ... A letter already chosen in the curated .bib key wins
    (Kajimoto2002b stays b); the rest take the next free letter in .bib order."""
    letters = [""] + list("abcdefghijklmnopqrstuvwxyz")
    entries = [e for e in bib if e.get("title")]
    wanted = {}
    for e in entries:
        m = re.search(r"(\d{4})([A-Za-z]?)$", e["key"])
        wanted[e["key"]] = m.group(2).lower() if m and m.group(1) == citekey(e)[-4:] else None
    out, used = {}, {}
    for e in sorted(entries, key=lambda e: wanted[e["key"]] is None):  # explicit letters claim first
        base = citekey(e)
        taken = used.setdefault(base, set())
        suf = wanted[e["key"]] if wanted[e["key"]] is not None and wanted[e["key"]] not in taken else next(l for l in letters if l not in taken)
        taken.add(suf)
        out[e["key"]] = base + suf
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", type=float, default=0.55, help="fuzzy title score below this is 'unmatched'")
    a = ap.parse_args()

    bib = parse_bib((REFS / "references.bib").read_text(encoding="utf-8"))
    by_doi = {norm_doi(e.get("doi")): e for e in bib if e.get("doi")}
    t4 = [r for r in csv.DictReader(open(TABLE4, encoding="utf-8")) if r["stem"]]

    overrides = {r["pdf"]: r for r in csv.DictReader(open(OVERRIDES, encoding="utf-8"))} if OVERRIDES.exists() else {}
    rows, used = [], {}
    for pdf in sorted(REFS.glob("*.pdf")):
        stem, entry, method, score = pdf.stem, None, "", 0.0
        ov = overrides.get(pdf.name)
        if ov and ov["bib_key"] == "skip":
            rows.append({"pdf": pdf.name, "status": "SKIP", "method": "override", "score": "", "bib_key": "", "doi": "",
                         "year": "", "title": ov["note"], "contribution_class": "", "tier": "", "in_table4": False, "new_name": ""})
            continue
        sn = stem_norm(stem)
        cls = None
        if ov:
            entry, method, score = next(e for e in bib if e["key"] == ov["bib_key"]), "override", 1.0
        cls = cls or next((r for r in t4 if sn.startswith(stem_norm(r["stem"]))), None)
        if entry:
            pass
        elif cls and norm_doi(cls["doi"]) in by_doi:
            entry, method, score = by_doi[norm_doi(cls["doi"])], "table4_doi", 1.0
        elif cls:
            best = max(bib, key=lambda e: title_score(cls["title"], e.get("title", "")))
            score = title_score(cls["title"], best.get("title", ""))
            if score >= 0.85:
                entry, method = best, "table4_title"
            else:
                method = "table4_not_in_bib"
        else:
            best = max(bib, key=lambda e: title_score(stem, e.get("title", "")))
            score = title_score(stem, best.get("title", ""))
            # filename is often Author+Year+short title: credit an author/year hit
            yr = re.search(r"(19|20)\d\d", stem)
            if yr and best.get("year", "").startswith(yr.group()) and citekey(best)[:4].lower() in ascii_fold(stem).lower():
                score = min(1.0, score + 0.25)
            if score >= a.cutoff:
                entry, method = best, "fuzzy_filename"
        row = {
            "pdf": pdf.name, "status": "", "method": method, "score": round(score, 2),
            "bib_key": entry["key"] if entry else "", "doi": entry.get("doi", "") if entry else (cls or {}).get("doi", ""),
            "year": entry.get("year", "") if entry else "", "title": entry.get("title", "") if entry else (cls or {}).get("title", ""),
            "contribution_class": (cls or {}).get("contribution_class", ""), "tier": (cls or {}).get("tier", ""),
            "in_table4": bool(cls), "new_name": "",
        }
        if entry:
            used.setdefault(entry["key"], []).append(row)
        rows.append(row)

    keys = assign_citekeys(bib)
    for r in rows:
        if r["status"] == "SKIP":
            continue
        if not r["bib_key"]:
            r["status"] = "NOT_IN_BIB" if r["method"] == "table4_not_in_bib" else "UNMATCHED"
            continue
        r["new_name"] = keys[r["bib_key"]] + ".pdf"
        r["status"] = "DUPLICATE_ENTRY" if len(used[r["bib_key"]]) > 1 else ("OK" if r["method"].startswith(("table4", "override")) else "REVIEW")
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    matched_keys = {r["bib_key"] for r in rows if r["bib_key"]}
    no_pdf = [e for e in bib if e["key"] not in matched_keys]
    with open(OUT.with_name("bib_without_pdf.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bib_key", "year", "doi", "title"])
        for e in no_pdf:
            w.writerow([e["key"], e.get("year", ""), e.get("doi", ""), e.get("title", "")])

    from collections import Counter
    print(f"{len(bib)} bib entries, {len(rows)} PDFs, {len(t4)} table4 rows")
    print(Counter(r["status"] for r in rows))
    print(f"{len(no_pdf)} bib entries without a PDF")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
