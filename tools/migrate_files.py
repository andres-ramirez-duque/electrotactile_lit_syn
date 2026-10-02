"""Copy matched PDFs into the shared SharePoint-synced folder under their citekey names.

Reads out/library_match.csv (from match_library.py), never moves or deletes source files,
and writes out/files_manifest.csv with the SharePoint URL each file will have once synced.
Re-running is safe: files already present with the same size are left alone.
"""
import csv, hashlib, shutil, urllib.parse
from pathlib import Path

from match_library import REFS

HERE = Path(__file__).resolve().parent.parent
from local import SHARED_FOLDER as DEST, SHAREPOINT_FOLDER_URL
# Synced as a folder scope of the site's document library (OneDrive registry: IsFolderScope=1).
SP_FOLDER = SHAREPOINT_FOLDER_URL
# Supplementary files ride along with their paper rather than becoming items of their own.
SUPPLEMENTS = {"Trout_supplementary_Fig1.pdf": ("Trout2023", "_supp1")}


def sp_url(name):
    return urllib.parse.quote(SP_FOLDER + name, safe=":/")


def sha1(p):
    return hashlib.sha1(p.read_bytes()).hexdigest()


def main():
    rows = list(csv.DictReader(open(HERE / "out" / "library_match.csv", encoding="utf-8")))
    by_key = {r["bib_key"]: r for r in rows if r["status"] == "OK"}
    plan = [(r["pdf"], r["new_name"], r["bib_key"], "main") for r in rows if r["status"] == "OK"]
    for pdf, (key, suffix) in SUPPLEMENTS.items():
        plan.append((pdf, by_key[key]["new_name"][:-4] + suffix + ".pdf", key, "supplement"))

    copied = skipped = 0
    manifest = []
    for src_name, new_name, key, role in plan:
        src, dst = REFS / src_name, DEST / new_name
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            skipped += 1
        else:
            shutil.copy2(src, dst)
            copied += 1
        manifest.append({"bib_key": key, "role": role, "file": new_name, "source": src_name,
                         "bytes": src.stat().st_size, "sha1": sha1(src), "sharepoint_url": sp_url(new_name)})

    with open(HERE / "out" / "files_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)
    total = sum(m["bytes"] for m in manifest)
    print(f"{copied} copied, {skipped} already present, {total / 1e6:.0f} MB total -> {DEST}")


if __name__ == "__main__":
    main()
