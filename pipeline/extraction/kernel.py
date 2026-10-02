"""Helpers for extracting stimulation parameters and dose from a PDF corpus."""
import os
import re
import math

ETD_SIGNAL_PATTERN = r"""(
 \b\d+(?:\.\d+)?\s*(?:m\s?A|\u00b5A|uA|\u03bcA|mA/cm|A/cm)
|\b\d+(?:\.\d+)?\s*(?:\u00b5s|us|\u03bcs|ms|msec)\b
|\b\d+(?:\.\d+)?\s*(?:Hz|kHz|pps|pulses\s*per\s*second)\b
|\b\d+(?:\.\d+)?\s*(?:\u00b5C|uC|\u03bcC|nC|mC)\b
|charge[ -]?(?:density|per\s*phase|balanced)|current[ -]?density
|\b(?:bi|mono)phasic\b|interphase|interpulse|\b(?:cathod|anod)(?:al|ic)\b
|pulse\s*(?:width|duration|train|rate|amplitude)
|electrode\s*(?:diameter|size|area|radius|spacing|geometry)
|\b\d+(?:\.\d+)?\s*mm(?:\s*(?:in\s*)?diameter|\u00b2|\^?2)?\b
|\bactive\s*(?:area|electrode)\b|constant[ -]current|compliance\s*voltage
|(?:sensation|detection|pain|discomfort)\s*threshold|impedance
|\b\d+(?:\.\d+)?\s*(?:V|volt)\b
)"""

ETD_HIGH_VALUE = (
 r"\d+(?:\.\d+)?\s*(?:m\s?A|\u00b5A|uA|\u03bcA)\b",
 r"\d+(?:\.\d+)?\s*(?:\u00b5s|us|\u03bcs|ms|msec)\b",
 r"\d+(?:\.\d+)?\s*(?:Hz|kHz|pps)\b",
 r"\d+(?:\.\d+)?\s*(?:\u00b5C|uC|\u03bcC|nC)\b",
 r"electrode\s*(?:diameter|size|area|radius|spacing)",
 r"\d+(?:\.\d+)?\s*mm(?:\u00b2|\^?2|\s*diameter)",
 r"(?:bi|mono)phasic|interphase|charge[- ]balanc",
 r"charge\s*(?:density|per\s*phase)|current\s*density",
 r"\d+(?:\.\d+)?\s*V\b",
 r"constant[- ]current|compliance\s*voltage",
)

ETD_SYSTEM = ("You extract electrical-stimulation parameters from haptics and neurophysiology "
 "papers for a quantitative meta-analysis. Report ONLY values present in the supplied text. "
 "Never infer a plausible number from field knowledge; use -1 for anything not reported. Units: "
 "current in mA (convert uA), pulse width in microseconds (convert ms), frequency in Hz. If a "
 "range across participants or conditions is reported, give the extremes. Distinguish detection "
 "threshold from working range from device compliance limits. Distinguish pulse repetition rate "
 "from carrier frequency and from instrumentation bandwidth. If the paper is a review or reports "
 "no stimulation parameters, set the parameter fields to -1 and mark confidence sparse_or_absent.")

ETD_AUDIT_SYSTEM = ("Audit one paper's stimulation dose. Report only values the supplied text "
 "states, with verbatim quotes. Never report a device maximum rating as a delivered current. "
 "Distinguish pulse repetition rate from sampling/clock/carrier frequency and from amplifier "
 "bandwidth. Use -1 when a value is absent.")


def etd_extract_pdf_text(root, out_dir="text"):
    """Extract text from every PDF under `root` into `out_dir`; return per-file metadata."""
    import pathlib
    import pypdfium2 as pdfium
    out = pathlib.Path(out_dir)
    out.mkdir(exist_ok=True, parents=True)
    meta = []
    for p in sorted(pathlib.Path(root).rglob("*.pdf")):
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", p.stem)[:120]
        dest = out / (stem + ".txt")
        try:
            doc = pdfium.PdfDocument(str(p))
            parts = []
            for i in range(len(doc)):
                page = doc[i]
                tp = page.get_textpage()
                parts.append(tp.get_text_range())
                tp.close()
                page.close()
            npg = len(doc)
            doc.close()
            txt = "\n\n".join(parts)
            dest.write_text(txt, encoding="utf-8")
            meta.append({"file": p.name, "stem": stem, "txt": str(dest), "pages": npg,
                         "chars": len(txt), "scanned": len(txt) < 3000})
        except Exception as exc:
            meta.append({"file": p.name, "stem": stem, "txt": None,
                         "error": "%s: %s" % (type(exc).__name__, exc)})
    return meta


def etd_parameter_excerpts(text, budget=18000, win=300):
    """Condense `text` to parameter-bearing windows, ranked by distinct signal types."""
    pat = re.compile(ETD_SIGNAL_PATTERN, re.I | re.X)
    high = [re.compile(h, re.I) for h in ETD_HIGH_VALUE]
    spans = []
    for m in pat.finditer(text):
        a = max(0, m.start() - win)
        b = min(len(text), m.end() + win)
        if spans and a <= spans[-1][1] + 80:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    scored = []
    for a, b in spans:
        seg = text[a:b]
        scored.append((sum(1 for h in high if h.search(seg)), a, seg))
    scored.sort(key=lambda r: (-r[0], r[1]))
    keep, tot = [], 0
    for _score, a, seg in scored:
        if tot + len(seg) > budget:
            continue
        keep.append((a, seg))
        tot += len(seg)
    keep.sort()
    return " [...] ".join(s for _a, s in keep)


def etd_extraction_tool():
    """Forced-tool schema for per-paper parameter extraction."""
    enum_study = ["stimulator_hardware", "electrode_or_impedance", "psychophysics",
                  "interface_application", "neurophysiology", "safety_or_model",
                  "review_or_survey", "methods_guidance"]
    enum_app = ["fingertip_display", "vr_ar_contact_rendering", "texture_rendering",
                "sensory_substitution", "prosthetic_sensory_feedback", "wearable_wrist_forearm",
                "affective_ct_targeted", "nociception_selective_fiber", "telemanipulation",
                "generic_platform", "not_applicable"]
    num = {"type": "number"}
    props = {
        "title": {"type": "string"}, "first_author": {"type": "string"},
        "year": {"type": "integer"}, "venue": {"type": "string"},
        "doi": {"type": "string", "description": "DOI if present in the text, else empty"},
        "study_type": {"type": "string", "enum": enum_study},
        "application_class": {"type": "string", "enum": enum_app},
        "body_site": {"type": "string"},
        "source_mode": {"type": "string", "enum": ["constant_current", "constant_voltage",
            "charge_controlled", "hybrid_or_adaptive", "not_reported", "not_applicable"]},
        "waveform_polarity": {"type": "string", "enum": ["monophasic", "biphasic_symmetric",
            "biphasic_asymmetric", "mixed_or_multiple", "sinusoidal_or_ac", "not_reported",
            "not_applicable"]},
        "waveform_detail": {"type": "string", "description":
            "Leading polarity, pulse shape, interphase gap, burst structure. <=45 words."},
        "current_mA_min": dict(num, description="Lowest current used, mA. -1 if absent."),
        "current_mA_max": dict(num, description="Highest current used, mA. -1 if absent."),
        "current_basis": {"type": "string", "enum": ["detection_threshold",
            "working_or_comfortable_range", "pain_or_max_tolerable", "device_compliance_limit",
            "mixed", "not_reported"]},
        "voltage_V_max": dict(num, description="Compliance/output voltage, V. -1 if absent."),
        "pulse_width_us_min": dict(num, description="Phase width, microseconds. -1 if absent."),
        "pulse_width_us_max": num,
        "frequency_Hz_min": dict(num, description="Pulse repetition rate, Hz. -1 if absent."),
        "frequency_Hz_max": num,
        "frequency_kind": {"type": "string", "enum": ["pulse_repetition_rate",
            "carrier_frequency", "instrument_bandwidth", "not_reported"]},
        "n_channels": {"type": "integer", "description": "Independent channels. -1 if absent."},
        "electrode_material": {"type": "string"},
        "electrode_diameter_mm": dict(num, description="Active electrode diameter, mm. -1 if absent."),
        "electrode_area_mm2": dict(num, description=
            "Active area in mm2 only if stated; leave -1 if only a diameter is given."),
        "electrode_spacing_mm": num,
        "electrode_config": {"type": "string", "enum": ["concentric",
            "monopolar_with_remote_return", "bipolar_pair", "matrix_array", "interleaved_array",
            "not_reported", "not_applicable"]},
        "charge_per_phase_uC_reported": dict(num, description="Only if stated. -1 otherwise."),
        "charge_density_reported": {"type": "string", "description":
            "Verbatim value and units if any per-area density is reported, else empty."},
        "safety_limit_invoked": {"type": "string", "description":
            "Safety criterion or standard cited (Shannon, McCreery, IEC 60601, k value)."},
        "key_design_claim": {"type": "string", "description":
            "The finding or design rule that constrains interface design. 1-2 sentences."},
        "parameter_confidence": {"type": "string",
            "enum": ["explicit_in_text", "partly_inferred", "sparse_or_absent"]},
    }
    req = ["title", "first_author", "year", "study_type", "application_class", "source_mode",
           "waveform_polarity", "current_mA_min", "current_mA_max", "current_basis",
           "pulse_width_us_min", "frequency_Hz_min", "frequency_kind", "electrode_diameter_mm",
           "electrode_area_mm2", "key_design_claim", "parameter_confidence"]
    return {"name": "record_stimulation_parameters",
            "description": "Record stimulation parameters and design claims from one paper.",
            "input_schema": {"type": "object", "properties": props, "required": req}}


def etd_audit_tool():
    """Forced-tool schema for re-verifying an outlier dose record against source text."""
    props = {
        "pulse_width_us": {"type": "number", "description":
            "Per-phase pulse width in microseconds used for stimulation. -1 if not stated."},
        "pulse_width_quote": {"type": "string", "description": "Verbatim clause, <=25 words"},
        "pulse_rate_Hz": {"type": "number", "description":
            "PULSE REPETITION rate in Hz, not sampling/carrier/bandwidth/clock. -1 if absent."},
        "pulse_rate_quote": {"type": "string"},
        "current_used_mA_max": {"type": "number", "description":
            "Highest current actually delivered to a participant, NOT a device rating."},
        "current_quote": {"type": "string"},
        "electrode_active_area_mm2": {"type": "number", "description": "Active area, mm2, or -1"},
        "area_quote": {"type": "string"},
        "regime": {"type": "string", "enum": ["surface_tactile_display", "large_pad_tens",
            "intraneural_or_microneurography", "transcutaneous_nerve_trunk", "kHz_nerve_block",
            "bench_electrode_characterisation", "other"]},
        "note": {"type": "string", "description":
            "<=25 words on any mismatch between device rating and delivered dose"},
    }
    return {"name": "confirm_stimulation_dose",
            "description": "Re-verify one paper's dose parameters with verbatim quotes.",
            "input_schema": {"type": "object", "properties": props,
                             "required": ["pulse_width_us", "pulse_rate_Hz",
                                          "current_used_mA_max", "electrode_active_area_mm2",
                                          "regime"]}}


def etd_extraction_system():
    """System prompt for the extraction fan-out."""
    return ETD_SYSTEM


def etd_audit_system():
    """System prompt for the outlier audit pass."""
    return ETD_AUDIT_SYSTEM


def etd_shannon_limit(charge_per_phase_uC, k=1.5):
    """Shannon charge-density limit in uC/cm2: log D = k - log Q. Implant-derived reference."""
    return (10.0 ** k) / charge_per_phase_uC


def etd_derive_dose(df, carrier_cutoff_Hz=20000.0):
    """Add area, dose and band columns to a records DataFrame. Returns a copy.

    Expects columns current_mA_min/max, pulse_width_us_min/max, frequency_Hz_min/max,
    electrode_diameter_mm, electrode_area_mm2. Sentinel -1 and 0 are treated as missing.
    """
    import numpy as np
    import pandas as pd
    d = df.copy()
    cols = ["current_mA_min", "current_mA_max", "voltage_V_max", "pulse_width_us_min",
            "pulse_width_us_max", "frequency_Hz_min", "frequency_Hz_max",
            "electrode_diameter_mm", "electrode_area_mm2", "electrode_spacing_mm",
            "charge_per_phase_uC_reported", "n_channels"]
    for c in cols:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").replace(-1, np.nan)
            d.loc[d[c] == 0, c] = np.nan
    dia = d.get("electrode_diameter_mm")
    d["area_mm2"] = d["electrode_area_mm2"].fillna(math.pi * (dia / 2.0) ** 2)
    d["area_source"] = np.where(d["electrode_area_mm2"].notna(), "reported",
                                np.where(dia.notna(), "from_diameter", "unknown"))
    d["area_cm2"] = d["area_mm2"] / 100.0
    d["I_hi"] = d["current_mA_max"].fillna(d["current_mA_min"])
    d["pw_us"] = d["pulse_width_us_max"].fillna(d["pulse_width_us_min"])
    f = d["frequency_Hz_max"].fillna(d["frequency_Hz_min"])
    d["freq_kind"] = np.where(f.isna(), "none",
                       np.where(f <= carrier_cutoff_Hz, "pulse_repetition_rate",
                                "carrier_or_instrument_bandwidth"))
    d["prr_Hz"] = np.where(d["freq_kind"] == "pulse_repetition_rate", f, np.nan)
    d["f_carrier_Hz"] = np.where(d["freq_kind"] != "pulse_repetition_rate", f, np.nan)
    d["J_peak_mA_cm2"] = d["I_hi"] / d["area_cm2"]
    d["Q_uC"] = d["I_hi"] * d["pw_us"] / 1000.0
    d["D_uC_cm2"] = d["Q_uC"] / d["area_cm2"]
    d["Javg_mA_cm2"] = d["I_hi"] * (d["pw_us"] * 1e-6) * d["prr_Hz"] / d["area_cm2"]
    d["shannon_k1.5_uC_cm2"] = (10.0 ** 1.5) / d["Q_uC"]
    d["frac_of_shannon_k1.5"] = d["D_uC_cm2"] / d["shannon_k1.5_uC_cm2"]
    d["density_band"] = pd.cut(d["D_uC_cm2"], [-np.inf, 10, 100, np.inf],
                               labels=["I_low_density_large_area", "II_display_scale",
                                       "III_point_contact"])
    d["dose_audit_flag"] = ((d["Q_uC"] > 20) | (d["pw_us"] > 5000) | (f > 5000)
                            | (d["D_uC_cm2"] > 1000))
    return d

ETD_CLASSIFY_SYSTEM = (
    "You classify papers for a meta-analysis of electrical stimulation of skin and separate two things "
    "authors often state side by side: what a device is RATED to do, and what was actually DELIVERED to "
    "human participants. Put ratings in env_* fields and delivered values in del_* fields; never copy a "
    "rating into a del_* field. Report only values present in the text; use -1 for absent numbers and empty "
    "strings for absent text. Units: mA, microseconds, Hz, mm2. Pulse rate means pulse repetition rate, never "
    "a sampling rate, carrier frequency or amplifier bandwidth; put those in env_bandwidth_or_carrier_Hz. For "
    "matrix or multi-pad electrodes, del_electrode_area_mm2 is the area of ONE active pad, not the array "
    "footprint, because the pad is what sets current density. A paper that only models, reviews or measures "
    "without stimulating a person has delivers_stimulus_to_humans=false."
)

ETD_ENVELOPE_AUDIT_SYSTEM = (
    "Audit one stimulator paper's RATED output specifications. Report only values the text states, each with a "
    "verbatim quote. The most common error is reporting an amplifier bandwidth, carrier frequency, sampling "
    "rate or clock rate as a pulse repetition rate: put those in bandwidth_or_carrier_Hz and use -1 for the "
    "pulse rate if no true repetition rate is stated. Pulse width means one phase of a pulse, not a burst or "
    "train duration."
)

ETD_CONTRIBUTION_CLASSES = (
    "stimulator_hardware_electronics",
    "electrode_and_skin_interface",
    "perceptual_psychophysics_skin",
    "interface_and_application",
    "peripheral_neurophysiology",
    "safety_dosimetry_model",
    "review_survey_methodology",
    "ac_instrumentation_not_stimulation",
)

ETD_REGIMES = (
    "surface_skin_display",
    "large_pad_or_tens",
    "transcutaneous_nerve_trunk",
    "intraneural_or_microneurography",
    "khz_nerve_block",
    "bench_or_phantom_only",
    "no_stimulus_delivered",
)

ETD_NONDISPLAY_REGIMES = (
    "large_pad_or_tens",
    "transcutaneous_nerve_trunk",
    "intraneural_or_microneurography",
    "khz_nerve_block",
)


def etd_classification_system():
    """System prompt for the contribution / obligation classification pass."""
    return ETD_CLASSIFY_SYSTEM


def etd_envelope_audit_system():
    """System prompt for re-verifying implausible stimulator envelope specs."""
    return ETD_ENVELOPE_AUDIT_SYSTEM


def etd_classification_tool():
    """Forced-tool schema: classify one paper and split device envelope from delivered dose."""
    num = {"type": "number"}
    props = {
        "contribution_class": {"type": "string", "enum": list(ETD_CONTRIBUTION_CLASSES), "description":
            "Primary object of study. electrode_and_skin_interface covers contact materials, geometry, "
            "impedance measurement and equivalent-circuit models. ac_instrumentation_not_stimulation covers "
            "sinusoidal current sources for bioimpedance, EIT or impedance cardiography, electrosurgical RF "
            "generators, and power-electronics studies whose output is never used to elicit sensation."},
        "secondary_class": {"type": "string", "enum": list(ETD_CONTRIBUTION_CLASSES) + ["none"]},
        "stimulation_regime": {"type": "string", "enum": list(ETD_REGIMES)},
        "delivers_stimulus_to_humans": {"type": "boolean", "description":
            "True only if a stimulus was delivered to human participants in THIS paper."},
        "n_participants": {"type": "integer", "description": "Humans stimulated. -1 if none or not stated."},
        "has_device_envelope": {"type": "boolean", "description":
            "True if instrument capability is specified (max output, compliance, programmable ranges)."},
        "del_current_mA_min": dict(num, description="Current DELIVERED to participants, mA, low end. -1 if none."),
        "del_current_mA_max": dict(num, description="Current DELIVERED to participants, mA, high end. -1 if none."),
        "del_pulse_width_us": dict(num, description="Pulse width used with participants, us. -1 if none."),
        "del_pulse_rate_Hz": dict(num, description="Pulse REPETITION rate used with participants, Hz. -1 if none."),
        "del_electrode_area_mm2": dict(num, description="Area of ONE active pad used with participants, mm2, "
            "only if stated. Never the array footprint. -1 otherwise."),
        "del_electrode_diameter_mm": dict(num, description="Diameter of one active pad, mm. -1 if absent."),
        "del_waveform_polarity": {"type": "string", "enum": ["monophasic", "biphasic_symmetric",
            "biphasic_asymmetric", "sinusoidal_or_ac", "mixed_or_multiple", "not_reported", "no_delivery"]},
        "del_body_site": {"type": "string"},
        "env_current_max_mA": dict(num, description="Maximum RATED output current of the device, mA. -1 if absent."),
        "env_compliance_V": dict(num, description="Compliance or supply voltage rating, V. -1 if absent."),
        "env_pulse_width_us_min": num,
        "env_pulse_width_us_max": num,
        "env_pulse_rate_Hz_min": num,
        "env_pulse_rate_Hz_max": num,
        "env_n_channels": {"type": "integer", "description": "Independent output channels or pads. -1 if absent."},
        "env_output_impedance_Mohm": dict(num, description="Output impedance of the source, Mohm. -1 if absent."),
        "env_load_tested": {"type": "boolean", "description":
            "True if performance was measured against a stated test load or skin model."},
        "env_bandwidth_or_carrier_Hz": dict(num, description="Any amplifier bandwidth, RF carrier or sampling "
            "rate stated, so it is not confused with a pulse rate. -1 if absent."),
        "iface_impedance_reported": {"type": "string", "description":
            "Verbatim electrode-skin impedance value or model parameters if reported, else empty."},
        "iface_measurement_freq_Hz": dict(num, description="Frequency at which impedance was measured, Hz. -1 if absent."),
        "iface_electrode_material": {"type": "string"},
        "title": {"type": "string"},
        "first_author": {"type": "string", "description": "Surname only"},
        "year": {"type": "integer"},
        "venue": {"type": "string"},
        "doi": {"type": "string", "description": "DOI if present in the text, else empty"},
        "key_design_claim": {"type": "string", "description":
            "The one design-relevant finding, 40 words or fewer, grounded in the text."},
        "obligation_rationale": {"type": "string", "description":
            "One sentence: what this paper owes a reader in stimulation parameters, and why."},
    }
    required = ["contribution_class", "stimulation_regime", "delivers_stimulus_to_humans",
                "has_device_envelope", "first_author", "year", "title", "del_current_mA_max",
                "del_pulse_width_us", "del_pulse_rate_Hz", "del_electrode_area_mm2",
                "del_electrode_diameter_mm", "del_waveform_polarity", "env_current_max_mA",
                "env_compliance_V", "key_design_claim", "obligation_rationale"]
    return {"name": "classify_and_split",
            "description": "Classify one paper by contribution and separate its device envelope from any dose "
                           "delivered to humans.",
            "input_schema": {"type": "object", "properties": props, "required": required}}


def etd_source_kind_tool():
    """Forced-tool schema: decide whether a hardware paper's output stage stimulates tissue at all."""
    return {"name": "classify_source",
        "description": "Decide what kind of electrical output stage a hardware paper describes.",
        "input_schema": {"type": "object", "properties": {
            "output_kind": {"type": "string", "enum": ["pulsed_stimulator_for_tissue_stimulation",
                "ac_sinusoidal_instrumentation_source", "electrosurgical_rf_generator",
                "both_pulsed_and_ac", "other"], "description":
                "Pulsed stimulator = discrete charge-balanced or monophasic pulses intended to excite nerve, "
                "muscle or skin. AC instrumentation = continuous sinusoidal excitation for impedance "
                "measurement (EIS, EIT, ICG). Electrosurgical = high-power RF for cutting or coagulation."},
            "intended_use": {"type": "string", "description": "15 words or fewer, verbatim-grounded"},
            "evidence_quote": {"type": "string", "description": "Verbatim clause, 25 words or fewer"},
            "used_for_tactile_or_sensory_stimulation": {"type": "boolean", "description":
                "True only if the device is applied to elicit sensation or stimulate nerve or skin."}},
            "required": ["output_kind", "intended_use", "evidence_quote",
                         "used_for_tactile_or_sensory_stimulation"]}}


def etd_envelope_audit_tool():
    """Forced-tool schema: re-verify a stimulator's rated specs with verbatim quotes."""
    num = {"type": "number"}
    return {"name": "confirm_envelope",
        "description": "Re-verify a stimulator's rated output specifications with verbatim quotes.",
        "input_schema": {"type": "object", "properties": {
            "rated_current_max_mA": dict(num, description="Maximum rated OUTPUT CURRENT, mA. -1 if absent."),
            "current_quote": {"type": "string", "description": "Verbatim clause, 25 words or fewer"},
            "rated_pulse_width_max_us": dict(num, description="Longest programmable per-phase PULSE WIDTH, us. "
                "Not a train duration, not a sampling period. -1 if absent."),
            "pulse_width_quote": {"type": "string"},
            "rated_pulse_rate_max_Hz": dict(num, description="Highest programmable PULSE REPETITION rate, Hz. "
                "NOT amplifier bandwidth, carrier, sampling or clock rate. -1 if only a bandwidth is stated."),
            "pulse_rate_quote": {"type": "string"},
            "bandwidth_or_carrier_Hz": dict(num, description="Any bandwidth, carrier or sampling frequency "
                "stated, so it is not confused with pulse rate. -1 if absent."),
            "compliance_V": dict(num, description="Compliance or supply voltage rating, V. -1 if absent."),
            "note": {"type": "string", "description": "25 words or fewer on anything ambiguous"}},
            "required": ["rated_current_max_mA", "rated_pulse_width_max_us", "rated_pulse_rate_max_Hz",
                         "bandwidth_or_carrier_Hz", "compliance_V"]}}


def etd_assign_tier(contribution_class, stimulation_regime, delivers_to_humans, has_device_envelope):
    """Dose-reporting obligation tier for one paper. See the tier table in SKILL.md."""
    if contribution_class == "review_survey_methodology":
        return "D5_aggregate_envelope"
    if contribution_class == "ac_instrumentation_not_stimulation":
        return "D2i_ac_instrument_envelope"
    if delivers_to_humans and stimulation_regime == "surface_skin_display":
        return "D1_full_dose"
    if delivers_to_humans and stimulation_regime in ETD_NONDISPLAY_REGIMES:
        return "D1n_nondisplay_dose"
    if contribution_class == "electrode_and_skin_interface":
        return "D3_interface_characterisation"
    if contribution_class == "stimulator_hardware_electronics" and has_device_envelope:
        return "D2_instrument_envelope"
    return "D4_no_dose_obligation"


def etd_split_records(classifications):
    """Expand classification dicts into delivered / envelope / interface records.

    One paper can yield several records: a hardware paper that also ran a human demonstration
    contributes both an envelope record and a delivered record, scored against different
    obligations. Returns a pandas DataFrame with a record_type column.
    """
    import math
    import pandas as pd
    rows = []
    for x in (classifications.values() if hasattr(classifications, "values") else classifications):
        val = lambda k: (None if x.get(k) in (None, "", -1, -1.0) else x.get(k))
        cc = x.get("contribution_class")
        rg = x.get("stimulation_regime")
        tier = etd_assign_tier(cc, rg, bool(x.get("delivers_stimulus_to_humans")),
                               bool(x.get("has_device_envelope")))
        base = {"stem": x.get("stem"), "first_author": x.get("first_author"), "year": x.get("year"),
                "doi": x.get("doi", ""), "contribution_class": cc,
                "secondary_class": x.get("secondary_class", "none"), "stimulation_regime": rg,
                "paper_tier": tier}
        if tier in ("D1_full_dose", "D1n_nondisplay_dose"):
            area = val("del_electrode_area_mm2")
            dia = val("del_electrode_diameter_mm")
            if area is None and dia is not None:
                area = math.pi * (dia / 2.0) ** 2
            rows.append(dict(base, record_type="delivered", tier=tier,
                             n_participants=val("n_participants"), body_site=x.get("del_body_site", ""),
                             waveform_polarity=x.get("del_waveform_polarity", ""),
                             current_mA_min=val("del_current_mA_min"), current_mA_max=val("del_current_mA_max"),
                             pulse_width_us=val("del_pulse_width_us"), pulse_rate_Hz=val("del_pulse_rate_Hz"),
                             area_mm2=area,
                             area_source=("reported" if val("del_electrode_area_mm2") is not None
                                          else "from_diameter" if dia is not None else "unknown"),
                             dose_group=("fibre_selective_on_skin" if cc == "peripheral_neurophysiology"
                                         else "tactile_display")))
        if x.get("has_device_envelope") and cc in ("stimulator_hardware_electronics",
                                                   "ac_instrumentation_not_stimulation"):
            rows.append(dict(base, record_type="envelope",
                             tier=("D2i_ac_instrument_envelope"
                                   if cc == "ac_instrumentation_not_stimulation" else "D2_instrument_envelope"),
                             current_mA_max=val("env_current_max_mA"), compliance_V=val("env_compliance_V"),
                             pulse_width_us_min=val("env_pulse_width_us_min"),
                             pulse_width_us_max=val("env_pulse_width_us_max"),
                             pulse_rate_Hz_min=val("env_pulse_rate_Hz_min"),
                             pulse_rate_Hz_max=val("env_pulse_rate_Hz_max"),
                             bandwidth_or_carrier_Hz=val("env_bandwidth_or_carrier_Hz"),
                             n_channels=val("env_n_channels"),
                             output_impedance_Mohm=val("env_output_impedance_Mohm"),
                             load_tested=x.get("env_load_tested")))
        if str(x.get("iface_impedance_reported", "") or "").strip():
            rows.append(dict(base, record_type="interface", tier=tier,
                             impedance_reported=x.get("iface_impedance_reported", ""),
                             measurement_freq_Hz=val("iface_measurement_freq_Hz"),
                             electrode_material=x.get("iface_electrode_material", ""),
                             area_mm2=val("del_electrode_area_mm2"),
                             interface_contribution=(cc == "electrode_and_skin_interface"
                                 or x.get("secondary_class") == "electrode_and_skin_interface")))
    return pd.DataFrame(rows)


def etd_obligation_fields():
    """Per-tier expected field sets: {tier: [(label, column, kind), ...]}, kind in num/text/bool.

    Scoring a physiology paper on electrode area, or a stimulator datasheet on body site, produces a
    meaningless completeness figure. Each tier is scored only against what a paper of that kind owes.
    """
    dose = [("Body site", "body_site", "text"), ("Current amplitude", "current_mA_max", "num"),
            ("Pulse width", "pulse_width_us", "num"), ("Pulse repetition rate", "pulse_rate_Hz", "num"),
            ("Waveform polarity", "waveform_polarity", "text"),
            ("Electrode area or diameter", "area_mm2", "num")]
    return {
        "D1_full_dose": dose,
        "D1n_nondisplay_dose": dose,
        "D2_instrument_envelope": [
            ("Compliance voltage", "compliance_V", "num"), ("Max output current", "current_mA_max", "num"),
            ("Channel count", "n_channels", "num"), ("Tested against a load", "load_tested", "bool"),
            ("Pulse rate range", "pulse_rate_Hz_max", "num"), ("Pulse width range", "pulse_width_us_max", "num"),
            ("Output impedance", "output_impedance_Mohm", "num")],
        "D2i_ac_instrument_envelope": [
            ("Max output current", "current_mA_max", "num"), ("Supply voltage", "compliance_V", "num"),
            ("Bandwidth or carrier", "bandwidth_or_carrier_Hz", "num"),
            ("Output impedance", "output_impedance_Mohm", "num")],
        "D3_interface_characterisation": [
            ("Impedance value or model", "impedance_reported", "text"),
            ("Electrode material", "electrode_material", "text"),
            ("Electrode area or diameter", "area_mm2", "num"),
            ("Measurement frequency", "measurement_freq_Hz", "num")],
    }


def etd_reporting_completeness(records, interface_contribution_only=True):
    """Per-tier reporting completeness, scored against each tier's own field set.

    `records` is the DataFrame from etd_split_records. D3 is restricted to papers whose primary or
    secondary contribution is interface work, so that reporting an impedance value is a measurement
    rather than the record's own inclusion criterion. Returns a long DataFrame.
    """
    import pandas as pd
    placeholders = ("", "not_reported", "not_applicable", "no_delivery", "none", "nan", "None")
    out = []
    for tier, fields in etd_obligation_fields().items():
        if tier.endswith("envelope") and tier.startswith("D2"):
            sub = records[(records["record_type"] == "envelope") & (records["tier"] == tier)]
        elif tier == "D3_interface_characterisation":
            sub = records[records["record_type"] == "interface"]
            if interface_contribution_only and "interface_contribution" in sub.columns:
                sub = sub[sub["interface_contribution"].fillna(False).astype(bool)]
        else:
            sub = records[(records["record_type"] == "delivered") & (records["tier"] == tier)]
        if not len(sub):
            continue
        for label, col, kind in fields:
            if col not in sub.columns:
                present = pd.Series(False, index=sub.index)
            elif kind == "num":
                present = pd.to_numeric(sub[col], errors="coerce").notna()
            elif kind == "bool":
                present = sub[col].map(lambda v: bool(v) and v == v).fillna(False).astype(bool)
            else:
                present = ~sub[col].astype("string").fillna("").str.strip().isin(placeholders)
            out.append({"tier": tier, "field": label, "n_records": int(len(sub)),
                        "n_reporting": int(present.sum()), "pct": round(100.0 * present.mean(), 1)})
    return pd.DataFrame(out)

