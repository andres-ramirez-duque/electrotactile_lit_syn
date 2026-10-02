"""Paths and constants shared by the pipeline. Lab-side only: none of these locations are published."""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TOOLS = PROJECT / "tools"
sys.path.insert(0, str(TOOLS))  # match_library / migrate_files / zotero_import are reused, not copied
sys.path.insert(0, str(Path(__file__).resolve().parent / "extraction"))

WORK = PROJECT / "work" / "papers"     # per-paper state; never published
DATA = PROJECT / "data"                # the published dataset (papers.csv, records.csv)
SITE_DATA = PROJECT / "site" / "data"  # JSON the static site reads

from local import LAB_ROOT as LAB, SHARED_FOLDER as SHARED  # noqa: E402  (local.json, never committed)
REFS = LAB / "References"
SYNTHESIS = LAB / "Literature synthesis and design principles"

# Every value the pipeline writes is a draft until a person approves it (docs/architecture.md, stage 6).
STAGES = ("resolved", "fetched", "text", "classified", "needs_review", "approved", "committed")
