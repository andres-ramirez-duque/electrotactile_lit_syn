# Architecture

Two halves with a hard line between them:

- **Lab side (private, runs on a lab machine).** Needs the SharePoint-synced PDF folder, the Zotero key and,
  eventually, a language-model key. Nothing here is ever pushed to GitHub.
- **Public side (GitHub Pages, static).** Dashboard and manuscript checker built from the *published dataset*:
  bibliographic metadata plus extracted parameters. No PDFs, no paper text, no keys, no manuscripts.

GitHub Pages only serves static files, so it cannot run Python, hold secrets, or receive uploads. That decides
most of the design: everything that needs a secret or a PDF runs locally, and the site reads JSON.

```
 new paper (DOI / URL / PDF)
        │
        ▼
 ┌─────────────────────── lab machine: python -m pipeline ───────────────────────┐
 │ 1 resolve    DOI → Crossref/OpenAlex metadata, citekey (AuthorYear[a-z])       │
 │ 2 fetch      open-access PDF if one exists, else the PDF you supply            │
 │ 3 text       pypdfium2 text + parameter excerpt (kernel)                        │
 │ 4 classify   LANGUAGE MODEL: classify_and_split (kernel schema)   ◄── backend   │
 │ 5 derive     tier, records, charge/density/band, audit flags (kernel)          │
 │ 6 review     a person approves or corrects the values  ◄── nothing skips this  │
 │ 7 commit     data/papers.csv + data/records.csv; PDF → SharePoint; Zotero item │
 │ 8 publish    site/data/*.json (aggregates + per-paper parameters) → git push   │
 └────────────────────────────────────────────────────────────────────────────────┘
        │ git push (dataset + site only)
        ▼
 ┌──────────────── GitHub Pages ────────────────┐
 │ Dashboard: dose landscape, bands, reporting  │
 │ Checker: runs in the visitor's browser       │
 └──────────────────────────────────────────────┘
```

Per-paper working state lives in `work/papers/<citekey>/` (metadata, text, excerpt, model request/response,
draft record, status), so every stage can be rerun or inspected and a half-finished paper is never lost.

## Language-model backend (decision deferred)

Stage 4 is the only stage that needs a model. It goes through one interface,
`classify(system, tool_schema, text) -> dict`, with interchangeable backends:

| Backend | What it is | Status |
|---|---|---|
| `manual` | Writes the request to `work/papers/<key>/llm_request.md`; a person (or a Claude Code session) writes `llm_response.json` | Built first; used to test the whole flow |
| `openai_compat` | Any OpenAI-compatible endpoint: GitHub Models (GitHub token), a local open model via Ollama | To try at the end |
| `anthropic` | Claude API | To try at the end |

Whatever the backend, its output is a draft that stage 6 reviews. Backends are compared on the existing
100-paper corpus, where table4/table1 are the reference answers.

## Manuscript checker (public site)

Checks an unpublished manuscript against the reporting standard: the per-tier field lists in
`etd_obligation_fields()` (D1 full dose, D2 instrument envelope, D3 interface, ...).

- Runs **entirely in the browser**: PDF text via pdf.js, field detection with the kernel's parameter patterns
  ported to JavaScript. The manuscript is never uploaded and never sent to a language model.
- The author picks the paper type (or accepts a suggestion), sees which required fields were found, with the
  sentence each came from, and which are missing.
- Sharing is a separate, explicit step: download a small report (field list, no text), or choose to send the
  manuscript to the lab through an institutional channel (to be decided; a static site cannot receive files).

## What is published

| Published (git, public) | Never published |
|---|---|
| `data/papers.csv`: citekey, authors, year, title, venue, DOI, class, tier, rationale | PDFs, extracted text, excerpts |
| `data/records.csv`: extracted parameters and derived dose per record | `work/`, `out/` (file paths, SharePoint URLs, Zotero ids) |
| `site/`: dashboard and checker | `*.env`, any key |
| pipeline code | visitors' manuscripts |

Extracted numbers and citations are facts about the papers, not their text; the site links to each DOI.

## Open decisions
- Language-model backend (above).
- Repository name and GitHub account for Pages.
- Channel for manuscripts that authors choose to share.
- Whether the lab-side review step stays a CLI or gets a local web page (CLI first).
