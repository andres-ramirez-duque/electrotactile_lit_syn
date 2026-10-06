# Electrotactile literature synthesis

Shared reference library and parameter-synthesis pipeline for the BodyElectric lab.

## Where things live
| What | Where |
|---|---|
| Source PDFs (read-only to this project) | `BodyElectric_cl_fs/References` |
| Reference list: Better BibTeX auto-export of the Zotero group (Zotero is the source of truth) | `References/BodyElectric.bib` |
| Renamed PDFs, shared with the group (OneDrive/SharePoint sync) | `University of Glasgow/BodyElectric - References` |
| Reference metadata, collections, notes | Zotero group (id in `local.json`), no file storage used |
| Prior synthesis (tables 1–4, figures, write-up) | `BodyElectric_cl_fs/Literature synthesis and design principles` |
| Extraction procedure rescued from the Claude skill | `pipeline/extraction/` (`SKILL.md`, `kernel.py`) |

The Zotero API key is read from `zotero.env` and is never committed or printed.

## Phases
1. **Library migration**: `tools/match_library.py` (dry run) → review `out/library_match.csv`
   → `tools/migrate_files.py` (copy + rename into the shared folder)
   → `tools/zotero_import.py --apply` (items, 8 class sub-collections, tier/secondary tags, SharePoint links).
   *Done 2026-10-02: 115 items, 90 linked PDFs. Open items below.*
2. **Ingestion pipeline**: URL/DOI/PDF → metadata → extraction (`pipeline/extraction`)
   → human review → dataset → stats/figures → shared folder + Zotero.
3. **Websites**: private lab ingest page, and a public synthesis site with an in-browser
   manuscript checker (manuscript text never leaves the visitor's machine; submission is opt-in).

## Ground rules
- PDFs are never published; the public site shows extracted parameters and statistics only.
- Extracted values enter the dataset only after a person reviews them.
- The public checker can only be as good as the written reporting standard
  (tiers D1–D5 in `design_principles_synthesis.md`); that standard is the lab's call.

## Citation keys
Since 2026-10-06 keys are set in Zotero and exported by Better BibTeX; the rules below are how they were first made
and how the pipeline names a new paper.
`AuthorYear` plus `a`, `b`, ... (`Kajimoto2002`, `Kajimoto2002b`), ASCII-folded (`Pena2021`), organisations
by initials (`IEC2023`). A letter already chosen in the curated .bib key is kept; otherwise letters follow .bib
order. The key is the PDF file name and is set in each Zotero item's Citation Key field (not Extra: the app ignores that). After any change to the
scheme: `match_library.py`, then `rekey.py` (renames files, updates Zotero in place; swaps need `--skip-rename`
after a two-phase rename).

## Pipeline status
Design: `docs/architecture.md`. Run with `.venv/Scripts/python -m pipeline <command>` (see `pipeline/__main__.py`).
- `data/` seeded from the 2026-09-17 synthesis: 99 papers, 122 records (table4 counted the TacTex PDF twice).
- Stages resolve → fetch → text → model request → review → approve → commit work end to end with the
  `manual` backend; tested on Hugosdottir2019 (2026-10-02), which is waiting for a person's approval.
- `commit` (dataset + shared folder + Zotero) has not run yet; it will on the first approval.
- `publish` writes `site/data/`; the site (`site/`) is static and previewed with `python -m http.server`.
- Language-model backend: only `manual` so far. API backends are a later decision.

## Library migration: manual decisions
`tools/match_overrides.csv` records the matches made by hand (with reasons).

## Open items (updated 2026-10-05)
- Done 2026-10-05: the 11 table4 papers missing from the .bib: 9 added (.bib, Zotero, shared folder), 2 dropped
  (`data/excluded.csv`, PDFs in `References/_excluded/`).
- Done 2026-10-05: 12 hand-downloaded PDFs linked. Dropped Miao2017, Esram2007, Bhadra2005 (.bib; Zotero trash);
  Felizardo2016 and vanRaan2004 stay in .bib/Zotero but never on the site (`data/excluded.csv`, scope site_only;
  Zotero tag `not-on-site`). Still without a PDF: IEC2023 (standard).
- Done 2026-10-06: Zotero is the source of truth; `BodyElectric.bib` is its Better BibTeX export and the tools take
  its keys as final (`bib_keys_final` in local.json). The old hand-kept `references.bib` is no longer read.
  Kajimoto1999 still needs a venue (edit it in Zotero).
- Done 2026-10-06: the 20 never-extracted .bib papers went through the pipeline (manual backend), reviewed and
  approved: 18 committed, Cunningham2025 and Ke2015 site_only. Only IEC2023 remains unclassified (no PDF).
- Done 2026-10-06: expansion screening (35 candidates): 2 already held, 13 dropped (`data/excluded.csv`), 17 committed.
  Pending: Lim2024 on hold (reviewer to pick the experiment to record). Graczyk2024 and Blau2024 committed.
- Choose the language-model backend (GitHub Models/Copilot, an open model, or the Claude API).
- Site: chart labels are small at phone width; the checker's PDF upload is untested on a real PDF.

## License
Code: MIT (`LICENSE`). Dataset (`data/`, `site/data/`): CC BY 4.0 (`data/LICENSE.md`).
