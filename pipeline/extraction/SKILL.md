---
name: electrotactile-dose-extraction
description: "Extract stimulation parameters (current, pulse width, pulse rate, waveform, electrode geometry) from a corpus of electrotactile, electrocutaneous, TENS or neurostimulation PDFs and compute charge per phase, charge density and current density per paper, then classify configurations into dose bands. Use when asked to survey or meta-analyse stimulation parameters, build a dose/current-density table across papers, benchmark a stimulator against the literature, or audit what a reference collection reports."
metadata:
  authored_via: "claude-science"
  published_by: "agent"
  published_at: "2026-09-17T16:24:45.485Z"
  authored_by: "agent"
  authored_at: "2026-09-15T18:23:54.963Z"
  authoring_session: "1f5735c6-aa74-439f-8a36-9000e7668a38"
  last_modified_by: "agent"
  last_modified_at: "2026-09-17T16:24:45.441Z"
---

# Electrotactile dose extraction

Turns a folder of stimulation papers into a per-paper parameter table with derived dose
metrics (charge per phase, charge density per phase, peak and time-averaged current
density), then classifies configurations into density bands. Built for electrotactile and
electrocutaneous work; the same pipeline applies to TENS, FES and surface neurostimulation.

`kernel.py` is auto-loaded with this skill. Helpers are prefixed `etd_`.

## Why the derived metrics matter

Charge per phase is the conserved perceptual variable across this literature; charge
*density* is not, because electrode area is the free variable and it is the least-reported
parameter. A table of currents alone is not comparable across papers. Always carry the
dose triple: charge per phase Q (µC), active area A (mm²), and density Q/A (µC cm⁻²).

## Classify before you compare

A reference collection assembled for relevance to a programme is not parametrically comparable. Ask
whether an electrode area is reported and a microneurography paper, an impedance model and a stimulator
datasheet all score badly for reasons that have nothing in common: the first has no skin electrode, the
second elicits no percept, and only the third was ever obliged to state one. Scoring every paper against
one checklist produces a number that means nothing and understates the field. Classify on two axes first.

**Axis 1, contribution class** — what the paper's object of study is: `stimulator_hardware_electronics`,
`electrode_and_skin_interface`, `perceptual_psychophysics_skin`, `interface_and_application`,
`peripheral_neurophysiology`, `safety_dosimetry_model`, `review_survey_methodology`,
`ac_instrumentation_not_stimulation`.

**Axis 2, dose-reporting obligation** — what a paper of that kind owes a reader. `etd_assign_tier` derives
it from the class, the stimulation regime and whether a human was actually stimulated:

| Tier | Obligation | What it owes |
|---|---|---|
| **D1** | Full dose | Current, pulse width, pulse rate, waveform, electrode geometry |
| **D1n** | Non-display dose | Same fields, but TENS, nerve-trunk, intraneural or kHz-block geometry |
| **D2** | Stimulator envelope | Compliance, output impedance, programmable ranges, channels |
| **D2i** | AC instrument envelope | Output current, bandwidth, output impedance; no percept involved |
| **D3** | Interface characterisation | Electrode area, material, measurement conditions |
| **D4** | None | Mechanism and physiology; parameters appear only incidentally |
| **D5** | Aggregate envelope | Ranges across a literature, not configurations that were run |

Only D1 enters the dose landscape and the density bands. D1n is reported alongside but never pooled.
D2 and D2i are capability, not dose. On a mixed collection of this kind, expect fewer than half the
papers to be D1 at all.

## Workflow

1. **Extract text.** `etd_extract_pdf_text(root)` writes one `.txt` per PDF into `text/`
   and returns per-file page and character counts. Files returning under ~3000 characters
   are image-only scans: they contribute bibliographic metadata only, and you must say so
   rather than silently dropping them.
2. **Build parameter excerpts.** `etd_parameter_excerpts(text)` returns a density-ranked
   condensation (default 18 kB) of only the passages carrying a parameter signal, scored by
   how many distinct signal types each window contains. Sending whole papers to the model
   wastes tokens and dilutes accuracy; sending the first N matches in document order misses
   methods sections in long papers.
3. **Classify and split.** Fan out one request per paper with
   `host.llm([...], max_concurrency=8)` using `etd_classification_tool()` as the forced tool and
   `etd_classification_system()` as the system prompt, at `model=host.reasoning_model()`. Pass front
   matter (first ~2600 chars) plus the excerpt. This pass assigns both axes and, critically, separates
   what a device is *rated* to do (`env_*`) from what was *delivered* to participants (`del_*`), because
   authors state the two side by side. Then `etd_split_records(classifications)` expands each paper into
   delivered, envelope and interface records: a hardware paper with a human demonstration yields one of
   each, scored against different obligations. It returns no rows for D4 and D5 papers, so take
   paper-level counts from the classification table, not from the records.

   `etd_extraction_tool()` and `etd_extraction_system()` remain available for the narrower job of pulling
   one flat parameter record per paper, but the split schema is what makes the dose statistics
   defensible. Unit conversion is instructed in both system prompts: mA, µs, Hz, mm².
4. **Audit the outliers.** `etd_derive_dose` sets `dose_audit_flag` on any record where
   charge per phase exceeds 20 µC, pulse width exceeds 5 ms, reported frequency exceeds
   5 kHz, or charge density exceeds 1000 µC cm⁻². The flag fires on the raw parameters
   whether or not density is computable, so expect roughly a quarter of records. Re-verify
   those with `etd_audit_tool()` and `etd_audit_system()`, which demand verbatim quotes;
   on a mixed corpus this pass corrects about a third of the fields it re-reads, mostly
   compliance ratings and amplifier bandwidths.
5. **Derive dose and bands.** `etd_derive_dose(df)` adds the derived columns and the band
   assignment. It converts diameter to area assuming a circular contact and records
   `area_source` so the assumption stays visible. It assigns a band to *every* row with a
   computable density, including bench and intraneural records: mask to the surface-tactile
   regime before reporting band statistics, since the bands are only meaningful there.

6. **Score reporting per tier.** `etd_reporting_completeness(records)` scores each tier against its own
   field set from `etd_obligation_fields()` and returns a long table. Never score one checklist across
   the whole collection. D3 is restricted to papers whose primary or secondary contribution is interface
   work, so that reporting an impedance value is a measurement rather than the record's own inclusion
   criterion.
7. **Resolve citations.** Load the `literature-review` skill and use `crossref_lookup`
   per record plus `verify_dois` on the set you intend to cite. Prefer the published DOI
   over a preprint DOI when both exist, and label a preprint as one.

## Five extraction errors this pipeline exists to prevent

**Frequency is three different quantities.** Pulse repetition rate, carrier frequency and
instrumentation bandwidth all appear as "Hz". Values above ~20 kHz are almost always an
amplifier bandwidth (Howland current-source papers characterise to 0.2–3.7 MHz), a
bioimpedance sweep, or a kHz conduction-block carrier. `etd_derive_dose` splits these into
`prr_Hz` and `f_carrier_Hz` with a `freq_kind` label; never pool them. The 20 kHz cutoff is
a fallback, not the authority: when the extraction schema's `frequency_kind` field says
`pulse_repetition_rate`, honour it and move the value back to `prr_Hz`. Parameterised
stimulator platforms do legitimately specify repetition rates to 25 kHz, and those are
device envelopes rather than delivered doses (check `current_basis`).

**A review's parameter range is not a configuration.** Reviews and methods papers report
envelopes drawn across many studies, so taking max current times max pulse width produces a
dose no one ever delivered. Mark those rows (`study_type` in `review_or_survey`,
`methods_guidance`) as review envelopes, exclude them from band statistics and from every
quoted median, and plot them with a distinct open marker. On a corpus of this kind the
distinction moved the dose set by more than 20%.

**A device rating is not a delivered dose.** Compliance voltage and maximum output current
are instrument specifications. Papers state them next to human data, and extraction
conflates the two. The record schema carries `current_basis` for exactly this reason;
treat `device_compliance_limit` rows as hardware envelopes, not stimulation parameters.

**Electrode area is usually absent, never inferable, and ambiguous for arrays.** Only about
two-thirds of the papers that actually delivered a dose report an area or diameter, and barely
40% of the whole collection does. Compute area from diameter when only diameter is given, flag
it, and leave the rest missing. Do not substitute a typical value. For a matrix or multi-pad
electrode, the area that sets density is **one active pad**, not the array footprint — a 30-pad
thigh array of 10 mm pads is 78.5 mm², not 2400 mm². Getting this wrong moves a point by more
than an order of magnitude, so state the convention in the caption and check it whenever a
paper describes an array.

**Not every hardware paper is a stimulator.** Collections like this accumulate current-source
papers that share a circuit topology with stimulators but were never applied to elicit
sensation: sinusoidal Howland sources for bioimpedance, EIT or impedance cardiography,
electrosurgical RF generators, switching-converter control studies. They report accuracy and
output impedance in the same language a stimulator paper would, and pooling them inflates the
hardware statistics while their bandwidths contaminate the pulse-rate distribution. Run
`etd_source_kind_tool()` over every paper classed as hardware, class the ones that fail as
`ac_instrumentation_not_stimulation`, and cite their figures of merit as current-source
engineering benchmarks rather than as electrotactile platforms. On one 100-paper collection
this moved 8 of 28 apparent hardware papers.

**Stimulation regimes are not comparable.** Surface tactile displays, large-pad TENS,
intraneural microstimulation, kHz nerve block and bench electrode characterisation occupy
different geometry regimes by orders of magnitude. Classify with `regime` and compute band
statistics on the surface-tactile subset only; plot the others as visually distinct
excluded markers.

## Density bands

Computed on charge density per phase, D1 tactile-display configurations only. Band membership is set
almost entirely by electrode area, because charge per phase barely varies: on one 19-configuration set
the band medians of charge per phase were 0.60, 0.50 and 0.76 µC while density spanned three orders of
magnitude. Large-pad array work concentrates in Band I, so a collection that gains multi-pad papers
gains Band I members without shifting the charge-per-phase centre.

| Band | Q/A per phase | Typical area | Character |
|---|---|---|---|
| I — low-density, large-area | < 10 µC cm⁻² | > 20 mm² | Diffuse percept, high absolute current |
| II — display-scale | 10–100 µC cm⁻² | 0.6–11 mm² | Small-electrode matrix displays |
| III — point-contact | > 100 µC cm⁻² | < 1 mm² | Rising threshold, narrow comfort margin |

## Safety criteria: reference scale, not limit

The Shannon relation (log D = k − log Q, `etd_shannon_limit`) and the 30 µC cm⁻² McCreery
figure were derived for implanted electrodes in neural tissue. Surface configurations
routinely plot above the k = 1.5 isocline, which indicates the absence of a skin-specific
criterion rather than a violation: skin fails by erythema, electroporation, pain and
contact electrochemistry, not cortical injury. Draw the isoclines as an external reference
and say in the caption what they are. Report time-averaged current density alongside peak,
since that is the thermal and irritation-relevant quantity.

## Outputs to produce

A record-level CSV carrying raw and derived fields plus any audit note; a paper-level
classification table carrying both axes and a one-line rationale per obligation assignment, which is
what makes the tier assignments auditable; a band-statistics table on the D1 display set; and a
charge-per-phase against charge-density scatter on log axes, where iso-area lines run at slope +1 and
Shannon isoclines at slope −1, with non-display and fibre-selective records drawn as open markers.

Report reporting-completeness as a figure in its own right, one panel per obligation tier: the share
of papers supplying each parameter is a finding, not metadata, and per-tier scoring turns it from a
blanket indictment into a specific and actionable one. Expect each tier to have its own single gap —
electrode geometry in D1, output impedance in D2 (reported by roughly one paper in eight, against
compliance voltage in nearly all of them), measurement frequency in D3. Also worth a panel: delivered
dose against rated capability, which on one collection showed stimulators carrying only 2–3× headroom
over the parameters studies actually use.
