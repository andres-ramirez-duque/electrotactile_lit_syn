// Reporting checker. Everything here runs in the visitor's browser: the manuscript is read with pdf.js from a
// local File object and searched with regular expressions. No network request carries any of its text.
// The patterns follow the extraction kernel's parameter signals (pipeline/extraction/kernel.py); they find
// statements, they do not judge them, so every hit is shown with its sentence for the author to confirm.
"use strict";

(() => {
  const $ = (s) => document.querySelector(s);
  const NUM = String.raw`\d+(?:[.,]\d+)?`;
  const R = (s, f = "i") => new RegExp(s, f);
  const DETECT = {
    "Body site": R(String.raw`\b(fingertips?|fingers?|finger pads?|palms?|hands?|wrists?|forearms?|upper arms?|thighs?|calf|calves|legs?|feet|foot|lower back|back|abdomen|torso|trunk|tongue|lips?|face|neck|shoulders?|chest|glabrous skin|hairy skin)\b`),
    "Current amplitude": R(String.raw`\b${NUM}\s?(?:mA|µA|μA|uA)\b`, ""),
    "Pulse width": R(String.raw`(?:pulse|phase)[ -](?:width|duration)[^.]{0,60}?${NUM}\s?(?:µs|μs|us|ms)\b|\b${NUM}\s?(?:µs|μs)\b`),
    "Pulse repetition rate": R(String.raw`(?:rate|frequency|repetition)[^.]{0,40}?\b${NUM}\s?(?:Hz|pps)\b|\b${NUM}\s?(?:Hz|pps)\b[^.]{0,30}(?:rate|pulses?)`),
    "Waveform polarity": R(String.raw`\b(?:bi|mono)-?phasic\b|charge[- ]balanced|\b(?:cathod|anod)(?:ic|al)[- ](?:first|leading|pulse|phase)|\bsymmetric(?:al)? (?:square|rectangular)`),
    "Electrode area or diameter": R(String.raw`\b${NUM}\s?(?:mm|cm)\s?(?:²|\^?2\b)|diameter[^.]{0,40}?${NUM}\s?(?:mm|cm|µm|μm)\b|\b${NUM}\s?(?:mm|cm|µm|μm)\s?(?:in )?diameter|\b${NUM}\s?[x×]\s?${NUM}\s?(?:mm|cm)\b`),
    "Compliance voltage": R(String.raw`compliance[^.]{0,40}?${NUM}\s?k?V\b|\b${NUM}\s?k?V\b[^.]{0,30}compliance`),
    "Max output current": R(String.raw`(?:max(?:imum)?|up to|peak|full[- ]scale)[^.]{0,40}?${NUM}\s?(?:mA|µA|μA|uA|A)\b`),
    "Channel count": R(String.raw`\b${NUM}[- ]channels?\b|\b(?:two|four|eight|sixteen|thirty-two|sixty-four)[- ]channels?\b|\bchannels?\b[^.]{0,20}\b${NUM}`),
    "Tested against a load": R(String.raw`(?:resistive|test|dummy|RC|resistor[- ]capacitor)\s+loads?|load (?:of|resistance)[^.]{0,30}\d|\b${NUM}\s?k?(?:Ω|ohms?)\b[^.]{0,40}load`),
    "Pulse rate range": R(String.raw`${NUM}\s?(?:–|-|to)\s?${NUM}\s?(?:Hz|kHz|pps)\b`),
    "Pulse width range": R(String.raw`${NUM}\s?(?:–|-|to)\s?${NUM}\s?(?:µs|μs|us|ms)\b`),
    "Output impedance": R(String.raw`output impedance`),
    "Supply voltage": R(String.raw`supply voltage|±\s?${NUM}\s?V\b|\b${NUM}\s?V\s(?:supply|rail)`),
    "Bandwidth or carrier": R(String.raw`bandwidth|carrier|\b${NUM}\s?(?:kHz|MHz)\b`),
    "Impedance value or model": R(String.raw`impedance[^.]{0,80}?${NUM}\s?(?:k|M)?(?:Ω|ohms?)|\bCole\b|equivalent circuit|constant phase element`),
    "Electrode material": R(String.raw`Ag\s?\/\s?AgCl|\bsilver\b|\bgold\b|platinum|stainless steel|\bcarbon\b|hydrogel|conductive (?:rubber|gel|fabric|textile|ink|polymer)|titanium|PEDOT`),
    "Measurement frequency": R(String.raw`(?:at|@)\s?${NUM}\s?(?:Hz|kHz|MHz)\b|frequenc(?:y|ies) of\s?${NUM}`),
  };
  const CHOICES = [
    ["D1_full_dose", ["D1_full_dose"]],
    ["D1n_nondisplay_dose", ["D1n_nondisplay_dose"]],
    ["D2_instrument_envelope", ["D2_instrument_envelope"]],
    ["D2+D1", ["D2_instrument_envelope", "D1_full_dose"]],
    ["D2i_ac_instrument_envelope", ["D2i_ac_instrument_envelope"]],
    ["D3_interface_characterisation", ["D3_interface_characterisation"]],
  ];
  let text = "", lastResult = null;

  function init() {
    const { TIERS } = window.ETS;
    $("#tier").innerHTML = CHOICES.map(([v, ts]) => `<option value="${v}">${v === "D2+D1"
      ? "D2 + D1 · Stimulator with a human demonstration" : TIERS[v][0] + " · " + TIERS[v][1]}</option>`).join("");
    const desc = () => {
      const v = $("#tier").value;
      $("#tier-desc").textContent = v === "D2+D1" ? "Describes a stimulator and also uses it on participants: owes both the device envelope and the delivered dose." : TIERS[v][2];
    };
    $("#tier").addEventListener("change", desc);
    desc();
  }

  async function readPdf(file) {
    if (!window.pdfjsLib) throw new Error("The PDF reader did not load; paste the text instead.");
    pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
    const doc = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    const pages = [];
    for (let i = 1; i <= doc.numPages; i++) {
      const c = await (await doc.getPage(i)).getTextContent();
      pages.push(c.items.map((it) => it.str).join(" "));
    }
    return pages.join("\n");
  }

  const clean = (t) => t.replace(/(\w)-\s+(\w)/g, "$1$2").replace(/\s+/g, " ").replace(/μ/g, "µ");
  const sentences = (t) => t.split(/(?<=[.!?])\s+(?=[A-Z(])/);
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function check() {
    const { DATA, TIERS } = window.ETS;
    const body = clean(text || $("#paste").value);
    if (body.length < 200) {
      $("#out").innerHTML = `<p>Add a PDF or paste at least the methods section first.</p>`;
      $("#out-step").hidden = false;
      return;
    }
    const sents = sentences(body);
    const tiers = CHOICES.find(([v]) => v === $("#tier").value)[1];
    const groups = tiers.map((t) => ({
      tier: t,
      fields: DATA.standard[t].map(({ label }) => {
        const re = DETECT[label];
        const hit = sents.find((s) => re.test(s));
        let ev = "";
        if (hit) {
          const m = hit.match(re), s = hit.length > 260 ? hit.slice(Math.max(0, m.index - 110), m.index + 150) : hit;
          ev = esc(s).replace(esc(m[0]), `<mark>${esc(m[0])}</mark>`);
        }
        return { label, found: !!hit, ev };
      }),
    }));
    const all = groups.flatMap((g) => g.fields), got = all.filter((f) => f.found).length;
    const field = (f) => `<li class="${f.found ? "ok" : "no"}"><div class="head"><span class="mark">${f.found ? "✓" : "✗"}</span>` +
      `<span>${esc(f.label)}</span><span class="muted" style="margin-left:auto">${f.found ? "found" : "not found"}</span></div>` +
      (f.ev ? `<div class="ev">“…${f.ev}…”</div>` : "") + `</li>`;
    $("#out").innerHTML = `<p class="score">${got} of ${all.length} expected parameters found</p>` +
      groups.map((g) => `<h3 style="margin-top:14px">${TIERS[g.tier][0]} · ${TIERS[g.tier][1]}</h3><ul class="fields">${g.fields.map(field).join("")}</ul>`).join("") +
      benchmark(tiers, all);
    lastResult = { checked: new Date().toISOString().slice(0, 10), paper_type: $("#tier").value,
      fields: groups.flatMap((g) => g.fields.map((f) => ({ tier: g.tier, field: f.label, found: f.found }))) };
    $("#out-step").hidden = false;
    $("#out-step").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function benchmark(tiers, all) {
    // how the published literature does on the same fields: context, not a grade
    const rows = window.ETS.DATA.completeness.filter((c) => tiers.includes(c.tier));
    const missing = all.filter((f) => !f.found).map((f) => f.label);
    const lit = rows.filter((r) => missing.includes(r.field));
    if (!lit.length) return `<p class="secondary" style="margin-top:12px">Every expected field was found.</p>`;
    return `<p class="secondary" style="margin-top:12px">For comparison, in the published corpus: ` +
      lit.map((r) => `${r.field.toLowerCase()} is reported by ${Math.round(r.pct)}% of ${window.ETS.TIERS[r.tier][0]} records`).join("; ") + ".</p>";
  }

  async function onFile(file) {
    if (!file) return;
    $("#drop").querySelector("p").textContent = `Reading ${file.name}…`;
    try {
      text = await readPdf(file);
      $("#drop").querySelector("p").textContent = `${file.name}: ${text.length.toLocaleString()} characters read on this computer.`;
      check();
    } catch (e) {
      $("#drop").querySelector("p").textContent = e.message;
    }
  }

  document.addEventListener("ets:data", init);
  $("#file").addEventListener("change", (e) => onFile(e.target.files[0]));
  const drop = $("#drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); onFile(e.dataTransfer.files[0]); });
  $("#paste").addEventListener("input", () => { text = ""; });
  $("#run").addEventListener("click", check);
  $("#dl").addEventListener("click", () => {
    if (!lastResult) return;
    const blob = new Blob([JSON.stringify(lastResult, null, 1)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: "reporting-checklist.json" });
    a.click();
    URL.revokeObjectURL(a.href);
  });
})();
