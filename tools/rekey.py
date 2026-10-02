"""Apply a citation-key scheme change to files and Zotero without recreating anything.

Run after changing match_library.citekey/assign_citekeys and rerunning match_library.py:
  1. renames the shared PDFs from the old manifest names to the new ones (no copies, no deletes),
  2. reruns migrate_files to rewrite the manifest with the new SharePoint URLs,
  3. updates each Zotero item's 'Citation Key:' line and each linked attachment's URL in place.
Old manifest is expected at out/files_manifest.before-rekey.csv.
"""
import argparse, csv, json, re, urllib.request

import match_library as ml
import migrate_files as mf
import zotero_import as zi

OLD = zi.HERE / "out" / "files_manifest.before-rekey.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-rename", action="store_true", help="files already renamed (e.g. by hand for key swaps)")
    a = ap.parse_args()
    old = {(r["bib_key"], r["role"]): r for r in csv.DictReader(open(OLD, encoding="utf-8"))}
    match = [r for r in csv.DictReader(open(zi.HERE / "out" / "library_match.csv", encoding="utf-8")) if r["status"] == "OK"]
    new_main = {r["bib_key"]: r["new_name"] for r in match}

    renamed = 0
    for (bk, role), r in old.items():
        new = new_main[bk] if role == "main" else new_main[bk][:-4] + r["file"][r["file"].rindex("_supp"):]
        src, dst = mf.DEST / r["file"], mf.DEST / new
        if not a.skip_rename and src.exists() and src != dst:
            if dst.exists():
                raise SystemExit(f"refusing to overwrite {dst.name}")
            src.rename(dst)
            renamed += 1
    print(f"renamed {renamed} files")
    import sys
    sys.argv = sys.argv[:1]
    mf.main()

    manifest = {(r["bib_key"], r["role"]): r for r in csv.DictReader(open(zi.HERE / "out" / "files_manifest.csv", encoding="utf-8"))}
    state = json.loads(zi.MAP.read_text())
    z = zi.Zotero(zi.api_key())
    keys = ml.assign_citekeys(ml.parse_bib((ml.REFS / "references.bib").read_text(encoding="utf-8")))

    def fetch(item_keys):
        out = []
        for i in range(0, len(item_keys), 50):
            r = urllib.request.urlopen(urllib.request.Request(f"{zi.API}/items?itemKey={','.join(item_keys[i:i + 50])}&format=json", headers=z.h))
            out += [x["data"] for x in json.load(r)]
        return out

    # parent items: set the native citationKey field; drop the old 'Citation Key:' Extra line
    upd = []
    by_zkey = {v: k for k, v in state["items"].items()}
    for d in fetch(list(state["items"].values())):
        ck = keys[by_zkey[d["key"]]]
        extra = re.sub(r"(?m)^Citation Key: .*\n?", "", d["extra"]).strip()
        if extra != d["extra"] or d.get("citationKey") != ck:
            upd.append({"key": d["key"], "version": d["version"], "extra": extra, "citationKey": ck})
    for i in range(0, len(upd), 50):
        res = z.req("POST", "/items", upd[i:i + 50])
        if res.get("failed"):
            raise SystemExit(json.dumps(res["failed"])[:1000])
    print(f"updated citation keys on {len(upd)} items")

    # attachments: old file name -> (bib_key, role) -> new URL
    old_by_file = {r["file"]: k for k, r in old.items()}
    att_upd, new_att_map = [], {}
    for d in fetch(list(state["attachments"].values())):
        fn = next(f for f, k in state["attachments"].items() if k == d["key"])
        ident = old_by_file.get(fn) or next(k for k, r in manifest.items() if r["file"] == fn)
        m = manifest[ident]
        new_att_map[m["file"]] = d["key"]
        if d["url"] != m["sharepoint_url"]:
            title = d["title"] if ident[1] == "main" else f"Supplement (SharePoint): {m['file']}"
            att_upd.append({"key": d["key"], "version": d["version"], "url": m["sharepoint_url"], "title": title})
    for i in range(0, len(att_upd), 50):
        res = z.req("POST", "/items", att_upd[i:i + 50])
        if res.get("failed"):
            raise SystemExit(json.dumps(res["failed"])[:1000])
    state["attachments"] = new_att_map
    zi.MAP.write_text(json.dumps(state, indent=1))
    print(f"updated {len(att_upd)} attachment links")


if __name__ == "__main__":
    main()
