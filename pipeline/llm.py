"""Stage 4: the one step that needs a language model, behind one interface so the backend can change.

classify(paper_dir, system, tool, text) returns the tool's arguments as a dict, or None when the answer is not
available yet. Only `manual` exists so far (docs/architecture.md, "Language-model backend"): it writes the
request as a readable file and waits for a JSON answer next to it, which a person or a Claude Code session
provides. API backends slot in here later with the same signature.
"""
import json

REQUEST, RESPONSE = "llm_request.md", "llm_response.json"


def manual(paper_dir, system, tool, text):
    resp = paper_dir / RESPONSE
    if resp.exists():
        return json.loads(resp.read_text(encoding="utf-8"))
    schema = json.dumps(tool["input_schema"], indent=1, ensure_ascii=False)
    (paper_dir / REQUEST).write_text(
        f"# Classification request: {paper_dir.name}\n\n"
        f"Answer with a single JSON object matching the schema below and save it as `{RESPONSE}` in this "
        f"folder. Then rerun `python -m pipeline run {paper_dir.name}`.\n\n"
        f"## Instructions\n\n{system}\n\n## Tool: {tool['name']}\n\n{tool['description']}\n\n"
        f"```json\n{schema}\n```\n\n## Paper text (front matter + parameter excerpt)\n\n{text}\n",
        encoding="utf-8")
    return None


BACKENDS = {"manual": manual}


def classify(backend, paper_dir, system, tool, text):
    if backend not in BACKENDS:
        raise SystemExit(f"backend '{backend}' not implemented yet; available: {', '.join(BACKENDS)}")
    return BACKENDS[backend](paper_dir, system, tool, text)
