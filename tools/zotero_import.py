"""Load the curated .bib into the BodyElectric Zotero group.

- One parent collection with the 8 contribution classes (table4) as sub-collections.
- Tags: the dose-reporting tier, and the secondary contribution class when there is one.
- Each item with a PDF gets a linked-URL attachment pointing at the SharePoint copy; nothing is
  uploaded to Zotero storage (the group has no file quota to spare).
- Citation keys go in Zotero's own citationKey field (the one the desktop app and Better BibTeX show),
  matching the PDF file names. An earlier version wrote them to Extra, which the app ignores.

Dry run by default; --apply writes. out/zotero_map.json records what exists, so reruns only add
what is missing. The API key is read from zotero.env and never printed.
"""
import argparse, csv, json, re, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path

import match_library as ml

HERE = Path(__file__).resolve().parent.parent
from local import ZOTERO_GROUP as GROUP, ZOTERO_KEY_FILE
API = f"https://api.zotero.org/groups/{GROUP}"
ENV = ZOTERO_KEY_FILE
MAP = HERE / "out" / "zotero_map.json"

PARENT = "Electrotactile corpus"
CLASSES = {
    "stimulator_hardware_electronics": "Stimulator hardware & electronics",
    "interface_and_application": "Interfaces & applications",
    "peripheral_neurophysiology": "Peripheral neurophysiology",
    "review_survey_methodology": "Reviews, surveys & methodology",
    "perceptual_psychophysics_skin": "Perception & psychophysics",
    "electrode_and_skin_interface": "Electrode & skin interface",
    "safety_dosimetry_model": "Safety & dosimetry models",
    "ac_instrumentation_not_stimulation": "AC instrumentation (non-stimulating)",
}
TYPE_MAP = {"article": "journalArticle", "inproceedings": "conferencePaper", "inbook": "bookSection",
            "incollection": "bookSection", "book": "book", "techreport": "report", "misc": "preprint"}
# .bib field -> Zotero field, per item type; anything the type's template rejects is dropped
FIELD_MAP = {
    "journalArticle": {"journal": "publicationTitle", "volume": "volume", "number": "issue", "pages": "pages", "issn": "ISSN"},
    "conferencePaper": {"booktitle": "proceedingsTitle", "pages": "pages", "publisher": "publisher", "series": "series", "isbn": "ISBN"},
    "bookSection": {"booktitle": "bookTitle", "pages": "pages", "publisher": "publisher", "series": "series", "isbn": "ISBN", "address": "place"},
    "book": {"publisher": "publisher", "isbn": "ISBN", "address": "place", "series": "series"},
    "report": {"institution": "institution", "number": "reportNumber", "address": "place"},
    "preprint": {"publisher": "repository"},
}
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def api_key():
    m = re.search(r"([A-Za-z0-9]{24})", ENV.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"no API key found in {ENV}")
    return m.group(1)


class Zotero:
    def __init__(self, key):
        self.h = {"Zotero-API-Key": key, "Zotero-API-Version": "3", "Content-Type": "application/json"}
        self.templates = {}

    def req(self, method, path, body=None, base=API):
        h = dict(self.h)
        if method == "POST":
            h["Zotero-Write-Token"] = uuid.uuid4().hex
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(base + path, data, h, method=method)) as r:
                    if r.headers.get("Backoff"):
                        time.sleep(int(r.headers["Backoff"]))
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 503) and attempt < 4:
                    time.sleep(int(e.headers.get("Retry-After", 5)))
                    continue
                raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:300]}")

    def template(self, item_type):
        if item_type not in self.templates:
            self.templates[item_type] = self.req("GET", f"/items/new?itemType={item_type}", base="https://api.zotero.org")
        return self.templates[item_type]

    def post(self, path, objs):
        """POST in batches of 50; returns one key per object, or raises listing the failures."""
        keys = []
        for i in range(0, len(objs), 50):
            res = self.req("POST", path, objs[i:i + 50])
            if res.get("failed"):
                raise RuntimeError(json.dumps(res["failed"], indent=1)[:2000])
            keys += [res["successful"][str(j)]["key"] for j in range(len(objs[i:i + 50]))]
        return keys


def creators(author, ctype="author"):
    out = []
    for name in [a.strip() for a in author.split(" and ") if a.strip()]:
        if "," in name:
            last, first = [s.strip() for s in name.split(",", 1)]
            out.append({"creatorType": ctype, "lastName": last, "firstName": first})
        elif len(name.split()) > 3:  # organisation (braced in the .bib)
            out.append({"creatorType": ctype, "name": name})
        else:
            parts = name.split()
            out.append({"creatorType": ctype, "lastName": parts[-1], "firstName": " ".join(parts[:-1])})
    return out


def to_item(z, e, citekey, collections, tags, extra_lines):
    itype = TYPE_MAP.get(e["entrytype"], "document")
    if itype == "report" and e.get("type", "").lower() == "standard":
        itype = "standard"
    t = z.template(itype)
    it = {k: v for k, v in t.items()}
    it["title"] = e.get("title", "")
    it["creators"] = creators(e.get("author", "")) + creators(e.get("editor", ""), "editor")
    mon = MONTHS.get(e.get("month", "")[:3].lower())
    it["date"] = f"{e.get('year', '')}-{mon:02d}" if mon and e.get("year") else e.get("year", "")
    for src, dst in {**FIELD_MAP.get(itype, {}), "doi": "DOI", "url": "url", "abstract": "abstractNote"}.items():
        if e.get(src) and dst in t:
            it[dst] = e[src]
    if itype == "standard":
        it.update({k: v for k, v in {"organization": e.get("institution", ""), "number": e.get("number", ""), "place": e.get("address", "")}.items() if k in t})
    if "DOI" not in t and e.get("doi"):  # conference papers in older schemas, book sections
        extra_lines.append(f"DOI: {e['doi']}")
    it["citationKey"] = citekey
    it["extra"] = "\n".join(extra_lines)
    it["collections"] = collections
    it["tags"] = [{"tag": tg} for tg in tags]
    return it


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to Zotero (default: dry run)")
    a = ap.parse_args()

    bib = [e for e in ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8")) if e.get("title")]
    match = {r["bib_key"]: r for r in csv.DictReader(open(HERE / "out" / "library_match.csv", encoding="utf-8")) if r["status"] == "OK"}
    files = {}
    for r in csv.DictReader(open(HERE / "out" / "files_manifest.csv", encoding="utf-8")):
        files.setdefault(r["bib_key"], []).append(r)
    t4 = list(csv.DictReader(open(ml.TABLE4, encoding="utf-8")))
    t4_by_doi = {ml.norm_doi(r["doi"]): r for r in t4 if r["doi"]}

    state = json.loads(MAP.read_text()) if MAP.exists() else {"collections": {}, "items": {}, "attachments": {}}
    z = Zotero(api_key())

    keys = ml.assign_citekeys(bib)
    plan = []
    for e in bib:
        m = match.get(e["key"])
        ck = keys[e["key"]]
        cls = None
        if m:  # same stem rule as match_library: table4 stems are sanitised, truncated file names
            cls = next((r for r in t4 if ml.stem_norm(Path(m["pdf"]).stem).startswith(ml.stem_norm(r["stem"]))), None)
        cls = cls or t4_by_doi.get(ml.norm_doi(e.get("doi")))
        plan.append((e, ck, cls))

    n_cls = sum(1 for _, _, c in plan if c)
    print(f"{len(plan)} items ({n_cls} classified, {len(plan) - n_cls} unclassified -> '{PARENT}' root + tag 'needs-classification'), "
          f"{sum(len(files.get(e['key'], [])) for e, _, _ in plan)} SharePoint links, {len(CLASSES) + 1} collections")
    if not a.apply:
        for e, ck, c in plan[:5]:
            print(f"  {ck:32} {(c or {}).get('contribution_class', '-'):36} {(c or {}).get('tier', '')}")
        print("dry run: rerun with --apply to write")
        return

    def save():
        MAP.write_text(json.dumps(state, indent=1))

    # collections
    if PARENT not in state["collections"]:
        state["collections"][PARENT] = z.post("/collections", [{"name": PARENT}])[0]
        save()
    todo = [c for c in CLASSES.values() if c not in state["collections"]]
    if todo:
        for name, key in zip(todo, z.post("/collections", [{"name": n, "parentCollection": state["collections"][PARENT]} for n in todo])):
            state["collections"][name] = key
        save()

    # items
    new = []
    for e, ck, c in plan:
        if e["key"] in state["items"]:
            continue
        cols = [state["collections"][PARENT]]
        tags, extra = [], []
        if c:
            cols.append(state["collections"][CLASSES[c["contribution_class"]]])
            tags.append(f"tier: {c['tier']}")
            if c["secondary_class"] not in ("", "none"):
                tags.append(f"secondary: {CLASSES[c['secondary_class']]}")
        else:
            tags.append("needs-classification")
        if e["key"] in match:
            extra.append(f"Original file: {match[e['key']]['pdf']}")
        new.append((e["key"], to_item(z, e, ck, cols, tags, extra)))
    for (bk, _), key in zip(new, z.post("/items", [it for _, it in new]) if new else []):
        state["items"][bk] = key
    save()

    # linked-URL attachments
    att = []
    for bk, rows in files.items():
        for r in rows:
            if r["file"] in state["attachments"] or bk not in state["items"]:
                continue
            title = "PDF (SharePoint)" if r["role"] == "main" else f"Supplement (SharePoint): {r['file']}"
            att.append((r["file"], {"itemType": "attachment", "linkMode": "linked_url", "parentItem": state["items"][bk],
                                    "title": title, "url": r["sharepoint_url"], "contentType": "application/pdf",
                                    "accessDate": "", "note": "", "tags": [], "relations": {}}))
    for (fn, _), key in zip(att, z.post("/items", [x for _, x in att]) if att else []):
        state["attachments"][fn] = key
    save()
    print(f"created {len(new)} items, {len(att)} attachments; {len(state['items'])} items tracked in {MAP.name}")


if __name__ == "__main__":
    main()
