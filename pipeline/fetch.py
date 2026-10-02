"""Stage 2: get the PDF. Open-access copies only; anything else the user supplies.

Publisher sites that refuse scripted downloads (403/418) are respected, not worked around: the paper is
marked as waiting for a PDF and the user drops one in with `pipeline attach`.
"""
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

UA = "BodyElectric-library-sync/1.0"


def open_access_pdf(doi):
    """(pdf_url, source, version) from OpenAlex's best open-access location, or (None, ...)."""
    try:
        w = json.load(urllib.request.urlopen("https://api.openalex.org/works/doi:" + urllib.parse.quote(doi), timeout=30))
    except Exception:
        return None, "", ""
    loc = w.get("best_oa_location") or {}
    return loc.get("pdf_url"), (loc.get("source") or {}).get("display_name", ""), loc.get("version", "")


def download(url, dest):
    """Returns '' on success, otherwise the reason. Falls back to curl, whose Windows build uses the system
    certificate store; this Python's bundled store rejects some hosts (arxiv.org, 2026-10-02)."""
    try:
        data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=120).read()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code} (publisher refuses scripted downloads; download it in a browser)"
    except Exception:
        if not shutil.which("curl"):
            return "download failed and curl is unavailable"
        r = subprocess.run(["curl", "-sSL", "-A", UA, "-o", str(dest), url], capture_output=True)
        if r.returncode:
            return r.stderr.decode(errors="replace").strip()
        data = dest.read_bytes()
    if not data.startswith(b"%PDF"):
        dest.unlink(missing_ok=True)
        return "response was not a PDF (probably a landing page)"
    dest.write_bytes(data)
    return ""
