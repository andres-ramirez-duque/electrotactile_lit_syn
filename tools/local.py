"""Machine- and lab-specific settings, read from local.json at the project root (never committed).

Copy local.example.json to local.json and fill it in. Keeping these out of the code lets the repository be public
without exposing folder layouts, the SharePoint site or the Zotero group.
"""
import json
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "local.json"
if not _FILE.exists():
    raise SystemExit(f"missing {_FILE.name}: copy local.example.json to local.json and fill in your paths")
_cfg = json.loads(_FILE.read_text(encoding="utf-8"))

LAB_ROOT = Path(_cfg["lab_root"])                  # holds References/ and the synthesis folder
SHARED_FOLDER = Path(_cfg["shared_folder"])        # OneDrive/SharePoint-synced folder for the renamed PDFs
SHAREPOINT_FOLDER_URL = _cfg["sharepoint_folder_url"].rstrip("/") + "/"
ZOTERO_GROUP = int(_cfg["zotero_group_id"])
ZOTERO_KEY_FILE = Path(_cfg["zotero_key_file"])
