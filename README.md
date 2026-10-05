# Electrotactile literature synthesis

Shared reference library and parameter-synthesis pipeline for the BodyElectric lab.

## Where things live
| What | Where |
|---|---|
| Source PDFs + `references.bib` (read-only to this project) | `BodyElectric_cl_fs/References` |
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
- `out/TODO_review_not_in_bib.csv`: 11 papers in table4 but not in the curated .bib; decide add/drop.
- `out/TODO_manual_downloads.csv`: 18 .bib entries without a PDF (6 open access but blocking scripts, 11 paywalled,
  plus the IEC 60601-2-10 standard). Drop PDFs into `References/` named `<BibKey>_...pdf`, then run the tools.
- A regenerated curated .bib is coming; rerun `match_library.py` + `rekey.py` against it. Give Kajimoto1999 a booktitle.
- 26 Zotero items tagged `needs-classification`: .bib papers never extracted. 8 already have PDFs and can go through
  the pipeline.
- Choose the language-model backend (GitHub Models/Copilot, an open model, or the Claude API).
- Site: chart labels are small at phone width; the checker's PDF upload is untested on a real PDF.

## License
Code: MIT (`LICENSE`). Dataset (`data/`, `site/data/`): CC BY 4.0 (`data/LICENSE.md`).
