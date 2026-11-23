"""Electrode geometry and skin interface: pitch, gap, contact, array, return path, coupling, impedance.

Ported 2026-11-23 from the electrotactile-dose-extraction skill and kept independent of it. Differences are
deliberate: length lists and ranges keep every value, mmHg/mmol are not lengths, a stated gap is never overwritten,
spacing of unstated basis is its own field (never silently a pitch), impedances cited from other papers are marked,
and every drafted value must be backed by a quote that occurs in the paper (audit).

  mine(text)     deterministic sentence queue: for reading, recall over precision, never a result
  tool/system    the model request; the answer goes through review like every other extraction
  audit          quotes must occur in the paper, numbers must occur in the quotes
  derive         gap, pitch/contact ratio, packing, pitch floor
"""
import math
import re
import unicodedata

PITCH_FLOOR_MM = 1.0    # threshold rises sharply at smaller pitch (Kajimoto2026; pitch and gap confounded there)
SA1_SPACING_MM = 1.15   # SA-I receptive-field spacing implied by 76 dots/cm2

ELECTRODE_FIELDS = {  # field: (kind, description); the authoritative checklist
    "configuration": ("text", "short label when a paper uses more than one electrode, else empty"),
    "contact_shape": ("text", "disc, ring, square, rectangle, line, pin, pad, textile or empty"),
    "contact_dim_mm": ("num", "stated linear dimension of ONE active contact: diameter, side, length or outer diameter"),
    "contact_dim2_mm": ("num", "second dimension: width of a rectangle, inner diameter of a ring"),
    "contact_area_mm2": ("num", "only if the paper states the area of one contact"),
    "n_contacts": ("num", "active contacts"),
    "material": ("text", "contact material"),
    "pitch_mm": ("num", "centre-to-centre distance, only when stated as pitch / centre-to-centre"),
    "gap_mm": ("num", "edge-to-edge distance, only when stated as gap / edge-to-edge / border-to-border"),
    "spacing_mm": ("num", "electrode spacing or distance whose basis the paper does not state"),
    "array_rows": ("num", "only if the layout is given as rows and columns"),
    "array_cols": ("num", "only if the layout is given as rows and columns"),
    "return_configuration": ("text", "one of the RETURN vocabulary, or empty"),
    "return_area_mm2": ("num", "stated area of the return electrode"),
    "return_site": ("text", "where the return electrode sits"),
    "coupling_state": ("text", "one of the COUPLING vocabulary, or empty"),
    "coupling_resistivity_ohm_m": ("num", "stated resistivity of the coupling medium"),
    "skin_prep": ("text", "skin preparation"),
    "body_site": ("text", "where the active contacts sit"),
    "skin_type": ("text", "glabrous, hairy or empty, only if stated or the site is unambiguous"),
}
IMPEDANCE_FIELDS = {
    "configuration": ("text", "electrode label or condition"),
    "Z_ohm_min": ("num", "impedance, low end (= high end for a single value)"),
    "Z_ohm_max": ("num", "impedance, high end"),
    "Z_definition": ("text", "what the impedance is between, and how measured"),
    "Z_source": ("text", "measured (by this paper), stated (given without a method or source), cited (from elsewhere), model, or design_target"),
    "measurement_freq_Hz": ("num", "measurement frequency"),
    "measurement_current_mA": ("num", "measurement current"),
    "coupling_state": ("text", "coupling at the measurement"),
    "area_mm2": ("num", "area of the electrode it was measured through"),
    "body_site": ("text", "site of the measurement"),
}
Z_SOURCES = ("measured", "stated", "cited", "model", "design_target")

PATTERNS = (
    ("pitch", r"\b(?:pitch|cent(?:er|re)[- ]?to[- ]?cent(?:er|re)|mil cent(?:er|re)s|inter[- ]?electrode\s*(?:distance|"
              r"spacing|separation|interval)|electrode\s*(?:spacing|interval)|spaced|spacing|at intervals? of|lattice)"),
    ("gap", r"\b(?:gap|(?:edge|border)[- ]?to[- ]?(?:edge|border)|separation between|clearance)"),
    ("contact", r"\b(?:electrode\s*(?:diameter|radius|size|width|area)|active\s*(?:area|site)|contact\s*(?:area|diameter|"
                r"size|pad)|(?:disc|disk|pin|probe|dot|tip|pad)\s*(?:diameter|radius|area|size|electrode)|diameter|radius|"
                r"surface area)"),
    ("array", r"\b(?:\d+\s*[x×*]\s*\d+\s*(?:array|matrix|grid|electrode|pads)|array\s*of\s*\d+|\d+\s*(?:electrodes|pads|"
              r"dots|taxels|tactors)\b|electrode\s*(?:array|matrix)|dots?\s*(?:per|/)\s*cm)"),
    ("return", r"\b(?:concentric|coaxial|monopolar|unipolar|bipolar|common\s*(?:ground|return|anode|cathode)|return\s*"
               r"(?:electrode|path|pad)|ground\s*(?:plane|electrode|pad)|(?:counter|reference|indifferent)\s*electrode|"
               r"dispersive|current\s*steering)"),
    ("coupling", r"\b(?:hydrogel|gel(?:led|s)?\b|electrode\s*(?:paste|cream)|saline|electrolyte|conductive\s*(?:paste|"
                 r"textile|fabric|yarn|ink)|dry\s*(?:electrode|contact|skin)|moist\w*|wet(?:ted)?\s*(?:skin|electrode)|"
                 r"abrad\w*|skin\s*prep\w*|alcohol|resistivity|self[- ]adhesive)"),
    ("material", r"\b(?:Ag\s*/?\s*AgCl|stainless\s*steel|gold|platinum|carbon\s*(?:rubber|black|fib)|PEDOT|copper|"
                 r"titanium|graphite)\b"),
    ("impedance", r"\b(?:impedance|(?:skin|contact|interface|electrode)\s*resistance|[kM]\s*(?:Ω|ohm)|Ω\s*[·.]?\s*c?m\b)"),
)
RETURN = (  # a hint for the reader; the reviewer settles the label
    ("concentric", r"concentric|coaxial|ring\s*(?:return|around)"),
    ("weighted_array", r"weighted\s*(?:array|pattern|sum|current)|current\s*steering|sum\s*of\s*weights"),
    ("array_common_return", r"common\s*(?:ground|return|anode|cathode)|ground\s*plane|peripheral\s*ground|"
                            r"surrounding\s*electrodes"),
    ("adjacent_bipolar", r"adjacent\s*(?:pair|electrodes)|bipolar\s*(?:pair|configuration|montage)|interdigitat|"
                         r"closely\s*spaced\s*pair"),
    ("remote_monopolar", r"monopolar|unipolar|(?:remote|distant)\s*(?:return|electrode)|dispersive|indifferent|"
                         r"reference\s*(?:pad|electrode)\s*on"),
    ("pad_pair", r"(?:large|gelled)[- ]?pad\s*pair|two\s*(?:large|self[- ]adhesive)\s*(?:pads|electrodes)"),
    ("row_column_addressed", r"crossed\s*(?:linear|line)|row\s*and\s*column|matrix\s*address|"
                             r"(?:anode|cathode)\s*columns"),
)
COUPLING = (
    ("hydrogel", r"hydrogel|gel\s*pad|pre[- ]?gelled|self[- ]?adhesive"),
    ("gel_paste", r"electrode\s*(?:gel|paste|cream)|conductive\s*(?:gel|paste)|gelled|electrolyte\s*gel"),
    ("saline", r"saline|salt\s*solution|soaked"),
    ("textile", r"conduct(?:ive|ing)\s*(?:textile|fabric|yarn|thread)|woven|knitted|embroider"),
    ("wet", r"wet(?:ted)?\s*(?:skin|electrode|finger)|moisten|damp"),
    ("dry", r"\bdry\s*(?:electrode|contact|skin|condition)|(?:without|no)\s*(?:any\s*)?(?:conductive\s*)?"
            r"(?:gel|paste|electrolyte|medium)"),
)

_N = r"\d+(?:\.\d+)?"
_RUN = rf"({_N}(?:\s*(?:mm|cm|µm)?\s*(?:[x×*–—-]|to)\s*{_N}){{0,2}})"
_END = r"(?!\w|\s?/\s?s|\s?\^?\s?[23²³](?![\d.]))"  # not mmHg or mmol, and not an area or volume
_UNITS = (
    (r"(\d+)\s*/\s*(\d+)\s*-?\s*in(?:ch(?:es)?|\.)?\b", "frac_inch", 25.4),
    (rf"{_RUN}\s*-?\s*mils?\b", "mil", 0.0254),
    (rf"(?<![/\d.])({_N})\s*-?\s*in(?:ch(?:es)?|\.)(?![a-z])", "inch", 25.4),
    (rf"(?<![\d.]){_RUN}\s*-?\s*(?:mm|millimet(?:er|re)s?){_END}", "mm", 1.0),
    (rf"(?<![\d.]){_RUN}\s*-?\s*(?:cm|centimet(?:er|re)s?){_END}", "cm", 10.0),
    (rf"(?<![\d.]){_RUN}\s*-?\s*(?:µm|um|microns?|micromet(?:er|re)s?){_END}", "um", 0.001),
)


def clean(text):
    """Readable text from the PDF layer: rejoin hyphenated line breaks (U+FFFE in pdfium), one mu and Omega."""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if t.count("\n\n") > 0.4 * t.count("\n"):  # pdfium's CRLF doubled by text-mode writing: every line break is two
        t = t.replace("\n\n", "\n")
    t = re.sub("(?<=[A-Za-z])(?<![mc]m)(?<!mil)[￾­\x02]\\s*(?=[a-z])|(?<=[a-z])(?<![mc]m)(?<!mil)-[ \\t]*\\r?\\n\\s*(?=[a-z])", "", t)
    t = re.sub("[￾­\x02‐‑]\\s*", "-", t).replace("μ", "µ").replace("Ω", "Ω")
    return re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)


def lengths_mm(s):
    """Every length in s as (mm, unit as written, matched text), in order. Imperial included (founding papers use
    mils and fractional inches); '2.5 x 1.25 mm' and '0.25-3.0 mm' keep every value; areas are not lengths."""
    out = []
    for pat, unit, f in _UNITS:
        for m in re.finditer(pat, s, re.I):
            if unit == "frac_inch":
                vals = [float(m[1]) / float(m[2])] if float(m[2]) else []
            else:
                vals = [float(v) for v in re.findall(_N, m[1])]
            out += [(m.start(), round(v * f, 4), unit, m[0].strip()) for v in vals]
    return [t[1:] for t in sorted(out, key=lambda t: t[0])]


def contact_area(shape, dim, dim2=None):
    """mm2 of one contact from its stated shape and dimension; None rather than a guess."""
    s = (shape or "").lower()
    if not dim or dim <= 0:
        return None
    if re.search(r"annul|ring|concentric", s):
        return round(math.pi * (dim ** 2 - dim2 ** 2) / 4, 4) if dim2 and dim2 < dim else None
    if re.search(r"disc|disk|circ|round|dot|pin|needle|probe|tip", s):
        return round(math.pi * dim ** 2 / 4, 4)
    if "square" in s:
        return round(dim ** 2, 4)
    if re.search(r"rect|strip|bar|line|pad", s) and dim2:
        return round(dim * dim2, 4)
    return None


def classify(s, vocab="return"):
    table = RETURN if vocab == "return" else COUPLING
    return "|".join(n for n, p in table if re.search(p, s or "", re.I)) or "unspecified"


def mine(text, max_chars=400):
    """Candidate sentences tagged by field, strongest first. A queue for reading: a 'mm' hit is often not a pitch."""
    body = clean(text)
    refs = [m.start() for m in re.finditer(r"\n\s*(?:REFERENCES|References|Bibliography)\s*\r?\n", body)]
    if refs and refs[-1] > 0.5 * len(body):
        body = body[:refs[-1]]
    rows, seen = [], set()
    for raw in re.split(r"(?<=[.;:])\s+(?=[A-Z0-9(])|(?:\r?\n){2,}", body):
        s = re.sub(r"\s+", " ", raw).strip()
        if len(s) < 25 or s in seen:
            continue
        seen.add(s)
        # a table or an unsplit run becomes several windows, so no length in it is lost
        for part in ([s] if len(s) <= max_chars else re.findall(rf".{{1,{max_chars}}}(?:\s|$)", s)):
            tags = [n for n, p in PATTERNS if re.search(p, part, re.I)]
            if tags:
                rows.append({"fields": tags, "lengths_mm": [v for v, _, _ in lengths_mm(part)], "sentence": part.strip()})

    def rank(r):
        num = bool(r["lengths_mm"]) or bool(re.search(r"\d\s*(?:[mc]m\s?2|[mc]m²|[kM]?\s?Ω|[kM]?\s?ohm)", r["sentence"]))
        return -(2 * bool({"pitch", "gap", "contact"} & set(r["fields"]) and num) + num), -len(r["fields"])
    return sorted(rows, key=rank)


def system():
    return ("Extract electrode geometry and skin-interface parameters from one electrotactile or neurostimulation paper. "
            "Report only what the text states; leave a field out when it is absent, never infer a plausible geometry. "
            "Pitch (centre-to-centre) is not gap (edge-to-edge); if the basis is unstated use spacing_mm. A dimension in mm "
            "is not an area: '5 mm electrode' is a diameter. A contact is one active contact, never the array footprint. "
            "An electrode count is not a row/column layout unless both are given. Convert imperial units to mm. The return "
            "electrode has its own area and site. Coupling is recorded separately from material. Give one electrode entry "
            "per electrode actually used here, not those of cited work. For impedance, say whether this paper measured it "
            "(Z_source) and give frequency and coupling where stated. Each entry carries the verbatim sentence(s). "
            "return_configuration is one of: " + ", ".join(n for n, _ in RETURN) +
            ". coupling_state is one of: " + ", ".join(n for n, _ in COUPLING) + ".")


def tool():
    def obj(fields):
        p = {k: {"type": "number" if kind == "num" else "string", "description": d} for k, (kind, d) in fields.items()}
        p["quotes"] = {"type": "array", "items": {"type": "string"}, "description": "verbatim sentence(s) with the values"}
        p["notes"] = {"type": "string"}
        return {"type": "array", "items": {"type": "object", "properties": p, "required": ["quotes"]}}
    return {"name": "report_geometry", "description": "Electrode geometry and skin interface of one paper.",
            "input_schema": {"type": "object", "required": ["electrodes", "impedances"],
                             "properties": {"electrodes": obj(ELECTRODE_FIELDS), "impedances": obj(IMPEDANCE_FIELDS)}}}


def _flat(s):
    return re.sub(r"[^a-z0-9µω]", "", unicodedata.normalize("NFKD", clean(s)).lower().replace("μ", "µ"))


def _states(v, q, area=False):
    """Does quote q state number v: as a length in any unit, literally, or scaled (kΩ, MΩ, cm2)?"""
    q = re.sub(r"(?<![.\d])(\d{1,3})[, ](?=\d{3}(?![.\d]))", r"\1", q)  # 10,000 and 10 000
    nums = {float(n) for n in re.findall(_N, q)}
    nums |= {float(m) * 10 ** int(x) for m, x in re.findall(rf"({_N})\s*[Xx×·]\s*10\^?(\d)\b", q)}  # 2 x 10(6), superscript lost
    vals = nums | {x for x, _, _ in lengths_mm(q)}
    if re.search(r"\d\s?k(?:[ΩX]|ohm|Hz)?\b|\(kΩ\)", q, re.I):  # kX: a font-mapped ohm sign; bare "k": one that was lost
        vals |= {n * 1e3 for n in nums}
    vals |= {n * 1e6 for n in nums if re.search(r"M\s?(?:Ω|ohm)|mega", q)}
    vals |= {n * 100 for n in nums if re.search(r"cm\s?[2²]", q)} | {n * 645.16 for n in nums if re.search(r"in\.?\s?[2²]|sq", q)}
    vals |= {math.pi * x * x / 4 for x in vals} if area else set()
    if re.search(r"radius|radii", q, re.I):
        vals |= {2 * x for x in vals}
    words = "one two three four five six seven eight nine ten eleven twelve".split()
    vals |= {i + 1.0 for i, w in enumerate(words) if re.search(rf"\b{w}\b", q, re.I)}
    return any(abs(v - x) <= 0.02 * abs(v) + 1e-9 for x in vals)


def audit(ans, text):
    """Problems in a drafted answer: quotes absent from the paper, numbers absent from their quotes, bad vocabulary."""
    body, bad = _flat(text), []
    for kind, fields in (("electrodes", ELECTRODE_FIELDS), ("impedances", IMPEDANCE_FIELDS)):
        for i, r in enumerate(ans.get(kind, [])):
            at, qs = f"{kind}[{i}]", r.get("quotes") or []
            if not qs:
                bad.append(f"{at}: no quote")
            for part in (p for q in qs for p in re.split(r"\.\.\.|…", q)):
                if _flat(part) not in body:
                    bad.append(f"{at}: quote not in the paper: {part.strip()[:70]!r}")
            for k, v in r.items():
                if k in ("quotes", "notes"):
                    continue
                if k not in fields:
                    bad.append(f"{at}: unknown field {k}")
                elif fields[k][0] == "num" and not _states(float(v), clean(" ".join(qs)),
                                                              area=kind == "impedances" and k == "area_mm2"):
                    bad.append(f"{at}: {k}={v} not in its quote")
            for k, voc in (("return_configuration", RETURN), ("coupling_state", COUPLING)):
                if r.get(k) and r[k] not in {n for n, _ in voc}:
                    bad.append(f"{at}: {k}={r[k]!r} is not in the vocabulary")
            if kind == "impedances" and r.get("Z_source") not in Z_SOURCES:
                bad.append(f"{at}: Z_source must be one of {Z_SOURCES}")
    return bad


def _f(v):
    try:
        x = float(v)
        return None if math.isnan(x) or x < 0 else x
    except (TypeError, ValueError):
        return None


ELECTRODE_COLS = ["citekey", *ELECTRODE_FIELDS, "area_mm2", "area_source", "pitch_used_mm", "pitch_source", "gap_used_mm",
                  "pitch_to_contact_ratio", "packing_per_cm2", "at_or_below_pitch_floor", "sa1_ratio", "notes"]
IMPEDANCE_COLS = ["citekey", *IMPEDANCE_FIELDS, "Z_ohm", "Z_area_ohm_cm2", "notes"]


def derive(r):
    """Derived columns, in place. Pitch comes from a stated gap + contact width when only those are given, and says so;
    spacing of unstated basis derives nothing."""
    dim, dim2 = _f(r.get("contact_dim_mm")), _f(r.get("contact_dim2_mm"))
    pitch, gap, stated = _f(r.get("pitch_mm")), _f(r.get("gap_mm")), _f(r.get("contact_area_mm2"))
    # only a shape with one width has a known width towards its neighbour (a line's stated dimension is its length)
    width = dim if dim and re.search(r"disc|disk|circ|round|dot|pin|needle|square", str(r.get("contact_shape") or ""), re.I) \
        else None
    calc = contact_area(r.get("contact_shape"), dim, dim2)
    r["area_mm2"], r["area_source"] = (stated, "reported") if stated else (calc, "from_dimensions" if calc else "")
    r["pitch_source"] = "reported" if pitch else ""
    if not pitch and gap and width and r.get("return_configuration") != "concentric":  # there the gap is contact-to-ring
        pitch, r["pitch_source"] = round(gap + width, 4), "gap_plus_contact"
    r["pitch_used_mm"] = pitch
    r["gap_used_mm"] = gap if gap is not None else round(pitch - width, 4) if pitch and width and pitch > width else None
    r["pitch_to_contact_ratio"] = round(pitch / width, 2) if pitch and width else None
    r["packing_per_cm2"] = round(100 / pitch ** 2, 1) if pitch else None
    r["at_or_below_pitch_floor"] = pitch <= PITCH_FLOOR_MM if pitch else None
    r["sa1_ratio"] = round(pitch / SA1_SPACING_MM, 2) if pitch else None
    return r


def derive_impedance(r):
    lo, hi, a = _f(r.get("Z_ohm_min")), _f(r.get("Z_ohm_max")), _f(r.get("area_mm2"))
    r["Z_ohm"] = z = (lo + hi) / 2 if lo and hi else lo or hi
    r["Z_area_ohm_cm2"] = round(z * a / 100, 1) if z and a else None
    return r


def rows(citekey, ans):
    """(electrode rows, impedance rows) for the dataset. Quotes stay in work/: paper text is never published."""
    def strip(r):
        return {"citekey": citekey, **{k: v for k, v in r.items() if k != "quotes"}}
    return ([derive(strip(r)) for r in ans.get("electrodes", [])],
            [derive_impedance(strip(r)) for r in ans.get("impedances", [])])


def fit_impedance(area_mm2, z_ohm):
    """Z ~ A^b: {n, exponent, r, span of Z*A}. Area normalisation assumes the exponent is -1."""
    import numpy as np
    a, z = np.array(area_mm2, float), np.array(z_ohm, float)
    ok = (a > 0) & (z > 0)
    a, z = a[ok] / 100, z[ok]
    if len(a) < 3:
        return {"n": int(len(a))}
    x, y = np.log10(a), np.log10(z)
    return {"n": int(len(a)), "exponent": round(float(np.polyfit(x, y, 1)[0]), 3),
            "r": round(float(np.corrcoef(x, y)[0, 1]), 3), "span_ZA": round(float((z * a).max() / (z * a).min()), 1)}


def completeness(recs, fields=ELECTRODE_FIELDS):
    """Share of records stating each field; -1, blanks and 'unstated' are not reports."""
    def said(v, kind):
        if kind == "num":
            return _f(v) is not None
        return str(v or "").strip().lower() not in ("", "nan", "none", "unspecified", "unstated", "not stated", "-1")
    return [{"field": k, "n": sum(said(r.get(k), kind) for r in recs), "of": len(recs)} for k, (kind, _) in fields.items()]
