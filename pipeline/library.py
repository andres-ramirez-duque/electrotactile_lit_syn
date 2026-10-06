"""Stage 7 (library half): put an approved paper's PDF in the shared folder and its item in the Zotero group.

Reuses the migration tools' Zotero client, item builder and state file (out/zotero_map.json), so items made
here are indistinguishable from the migrated ones and reruns never duplicate anything.
"""
import json
import shutil
import urllib.parse
import urllib.request

import match_library as ml
import migrate_files as mf
import zotero_import as zi


def _state():
    return json.loads(zi.MAP.read_text())


def zotero_key_for(citekey, state):
    """Zotero item key for a citekey: migrated items are keyed by .bib key, pipeline items by citekey."""
    if citekey in state["items"]:
        return state["items"][citekey]
    bib = ml.parse_bib(ml.BIB.read_text(encoding="utf-8"))
    inv = {ck: bk for bk, ck in ml.assign_citekeys(bib).items()}
    return state["items"].get(inv.get(citekey, ""))


def classification_tags(paper):
    tags = [f"tier: {paper['tier']}"]
    if paper.get("secondary_class") not in (None, "", "none"):
        tags.append(f"secondary: {zi.CLASSES[paper['secondary_class']]}")
    return tags


def upsert(citekey, entry, paper, pdf_path=None):
    """Create or update the Zotero item; copy the PDF and link it. Returns a short log line."""
    z, state = zi.Zotero(zi.api_key()), _state()
    cols = [state["collections"][zi.PARENT], state["collections"][zi.CLASSES[paper["contribution_class"]]]]
    tags = classification_tags(paper)
    key, log = zotero_key_for(citekey, state), []

    if key:
        cur = json.load(urllib.request.urlopen(urllib.request.Request(f"{zi.API}/items/{key}", headers=z.h)))["data"]
        # keep tags someone added by hand; replace only the ones this pipeline owns
        own = ("tier: ", "secondary: ", "needs-classification")
        kept = [t for t in cur["tags"] if not t["tag"].startswith(own)]
        z.req("POST", "/items", [{"key": key, "version": cur["version"], "collections": cols,
                                  "tags": kept + [{"tag": t} for t in tags]}])
        log.append(f"updated Zotero item {key}")
    else:
        item = zi.to_item(z, entry, citekey, cols, tags, ["Added by pipeline"])
        key = z.post("/items", [item])[0]
        state["items"][citekey] = key
        log.append(f"created Zotero item {key}")

    if pdf_path:
        dest = mf.DEST / f"{citekey}.pdf"
        if not dest.exists():
            shutil.copy2(pdf_path, dest)
            log.append(f"copied {dest.name} to shared folder")
        if dest.name not in state["attachments"]:
            att = {"itemType": "attachment", "linkMode": "linked_url", "parentItem": key, "title": "PDF (SharePoint)",
                   "url": mf.sp_url(dest.name), "contentType": "application/pdf", "accessDate": "", "note": "",
                   "tags": [], "relations": {}}
            state["attachments"][dest.name] = z.post("/items", [att])[0]
            log.append("linked PDF")
    zi.MAP.write_text(json.dumps(state, indent=1))
    return "; ".join(log)
