// Overview charts, library and routing. Plain SVG, no chart library: the three charts are small and fixed,
// and the site should keep working if a CDN is down (only the checker's PDF reader needs one).
"use strict";

const CLASSES = {
  stimulator_hardware_electronics: "Stimulator hardware & electronics",
  interface_and_application: "Interfaces & applications",
  peripheral_neurophysiology: "Peripheral neurophysiology",
  review_survey_methodology: "Reviews, surveys & methodology",
  perceptual_psychophysics_skin: "Perception & psychophysics",
  electrode_and_skin_interface: "Electrode & skin interface",
  safety_dosimetry_model: "Safety & dosimetry models",
  ac_instrumentation_not_stimulation: "AC instrumentation (non-stimulating)",
};
const TIERS = {
  D1_full_dose: ["D1", "Full dose", "Delivers stimulation to human skin (tactile display, haptic interface, psychophysics)"],
  D1n_nondisplay_dose: ["D1n", "Non-display dose", "Delivers stimulation to humans through TENS pads, nerve trunk, intraneural or kHz-block geometry"],
  D2_instrument_envelope: ["D2", "Stimulator envelope", "Describes a stimulator: what the device can deliver"],
  D2i_ac_instrument_envelope: ["D2i", "AC instrument envelope", "Describes a sinusoidal current source used for measurement, not to elicit sensation"],
  D3_interface_characterisation: ["D3", "Interface characterisation", "Characterises electrodes or the skin-electrode interface"],
  D4_no_dose_obligation: ["D4", "None", "Mechanism or physiology; parameters only incidental"],
  D5_aggregate_envelope: ["D5", "Aggregate envelope", "Review or survey: ranges across a literature"],
};
window.ETS = { CLASSES, TIERS };

const $ = (s, r = document) => r.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fmt = (x, d = 2) => (x == null ? "–" : Math.abs(x) >= 100 ? Math.round(x).toLocaleString() : (+x.toPrecision(3)).toString());
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- tooltip ----------
const tip = $("#tip");
function showTip(html, ev) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + w > innerWidth - 8) x = ev.clientX - w - pad;
  if (y + h > innerHeight - 8) y = ev.clientY - h - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
const hideTip = () => (tip.hidden = true);

// ---------- routing & theme ----------
function route() {
  const page = (location.hash || "#overview").slice(1);
  for (const s of document.querySelectorAll("section.page")) s.hidden = s.id !== "p-" + page;
  for (const a of document.querySelectorAll("header nav a")) a.toggleAttribute("aria-current", a.getAttribute("href") === "#" + page);
  window.scrollTo(0, 0);
}
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch (e) { /* private mode */ }
  drawCharts();
});
// charts read colours from CSS at draw time, so an OS theme change needs a redraw
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => drawCharts());
try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }

// ---------- data ----------
let DATA = null;
async function load() {
  // Pages caches for 10 min; revalidate so a freshly published dataset shows at once (unchanged files stay 304)
  const get = (n) => fetch(`data/${n}.json`, { cache: "no-cache" }).then((r) => r.json());
  const [papers, records, completeness, standard] = await Promise.all(["papers", "records", "completeness", "standard"].map(get));
  DATA = { papers, records, completeness, standard, byKey: Object.fromEntries(papers.map((p) => [p.citekey, p])) };
  window.ETS.DATA = DATA;
  renderStats();
  drawCharts();
  initLibrary();
  renderMethod();
  document.dispatchEvent(new Event("ets:data"));
}

function renderStats() {
  const { papers, records, completeness } = DATA;
  const d1 = records.filter((r) => r.record_type === "delivered" && r.tier === "D1_full_dose");
  const area = completeness.find((c) => c.tier === "D1_full_dose" && c.field === "Electrode area or diameter");
  const dose = d1.filter((r) => r.D_uC_cm2 != null).length;
  const tiles = [
    [papers.length, "papers classified"],
    [records.length, "parameter records"],
    [`${dose} / ${d1.length}`, "skin doses with a recoverable charge density"],
    [`${Math.round(area.pct)}%`, "of skin-dose records state electrode size"],
  ];
  $("#stats").innerHTML = tiles.map(([v, l]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
  const years = papers.map((p) => +p.year).filter(Boolean);
  $("#updated").textContent = `${papers.length} papers, ${Math.min(...years)}–${Math.max(...years)}`;
}

// ---------- charts ----------
function drawCharts() {
  if (!DATA) return;
  drawDose();
  drawCompleteness();
  drawMap();
}

const log10 = Math.log10;
function logScale(d0, d1, r0, r1) {
  const a = log10(d0), b = log10(d1);
  return (v) => r0 + ((log10(v) - a) / (b - a)) * (r1 - r0);
}

function drawDose() {
  const box = $("#dose-chart");
  box.innerHTML = "";
  const groups = [
    { id: "display", label: "Tactile display (D1)", color: "--series-1", open: false,
      test: (r) => r.tier === "D1_full_dose" && r.dose_group !== "fibre_selective_on_skin" },
    { id: "fibre", label: "Fibre-selective protocols on skin", color: "--series-2", open: false,
      test: (r) => r.dose_group === "fibre_selective_on_skin" },
    { id: "nondisplay", label: "Non-display: TENS, nerve trunk, intraneural (D1n)", color: "--series-3", open: true,
      test: (r) => r.tier === "D1n_nondisplay_dose" && r.dose_group !== "fibre_selective_on_skin" },
  ];
  const pts = DATA.records.filter((r) => r.record_type === "delivered" && r.Q_uC > 0 && r.D_uC_cm2 > 0)
    .map((r) => ({ r, g: groups.find((g) => g.test(r)) })).filter((p) => p.g);
  $("#dose-legend").innerHTML = groups.map((g) =>
    `<span class="k"><span class="sw${g.open ? " open" : ""}" style="${g.open ? "border-color" : "background"}:var(${g.color})"></span>${g.label} (${pts.filter((p) => p.g === g).length})</span>`
  ).join("") + `<span class="k"><span class="line"></span>Shannon k = 1.5</span>`;

  const W = 880, H = 440, m = { t: 12, r: 64, b: 46, l: 64 };
  const xs = pts.map((p) => p.r.Q_uC), ys = pts.map((p) => p.r.D_uC_cm2);
  const x0 = 10 ** Math.floor(log10(Math.min(...xs))), x1 = 10 ** Math.ceil(log10(Math.max(...xs)));
  const y0 = 10 ** Math.floor(log10(Math.min(...ys))), y1 = 10 ** Math.ceil(log10(Math.max(...ys)));
  const X = logScale(x0, x1, m.l, W - m.r), Y = logScale(y0, y1, H - m.b, m.t);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Scatter of charge per phase against charge density, log scales" }, box);
  svg.style.font = `12px ${css("--font")}`;

  // density bands, labelled at the right edge
  [[y0, 10, "I"], [10, 100, "II"], [100, y1, "III"]].forEach(([a, b, lab], i) => {
    const ya = Y(Math.max(a, y0)), yb = Y(Math.min(b, y1));
    if (i % 2 === 0) el("rect", { x: m.l, y: yb, width: W - m.l - m.r, height: ya - yb, fill: css("--band") }, svg);
    const t = el("text", { x: W - m.r + 8, y: (ya + yb) / 2 + 4, fill: css("--ink-2") }, svg);
    t.textContent = `Band ${lab}`;
  });
  // decade grid + ticks
  for (let e = log10(x0); e <= log10(x1); e++) {
    el("line", { x1: X(10 ** e), x2: X(10 ** e), y1: m.t, y2: H - m.b, stroke: css("--grid") }, svg);
    el("text", { x: X(10 ** e), y: H - m.b + 18, "text-anchor": "middle", fill: css("--muted") }, svg).textContent = fmt(10 ** e);
  }
  for (let e = log10(y0); e <= log10(y1); e++) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(10 ** e), y2: Y(10 ** e), stroke: css("--grid") }, svg);
    el("text", { x: m.l - 8, y: Y(10 ** e) + 4, "text-anchor": "end", fill: css("--muted") }, svg).textContent = fmt(10 ** e);
  }
  el("text", { x: (m.l + W - m.r) / 2, y: H - 8, "text-anchor": "middle", fill: css("--ink-2") }, svg).textContent = "Charge per phase, µC";
  const yl = el("text", { x: 16, y: (m.t + H - m.b) / 2, "text-anchor": "middle", fill: css("--ink-2"),
    transform: `rotate(-90 16 ${(m.t + H - m.b) / 2})` }, svg);
  yl.textContent = "Charge density per phase, µC cm⁻²";

  // Shannon k=1.5: log D = 1.5 - log Q, clipped to the plot
  const sh = [];
  for (let i = 0; i <= 60; i++) {
    const q = 10 ** (log10(x0) + (i / 60) * (log10(x1) - log10(x0))), d = 10 ** 1.5 / q;
    if (d >= y0 && d <= y1) sh.push(`${X(q).toFixed(1)},${Y(d).toFixed(1)}`);
  }
  if (sh.length > 1) el("polyline", { points: sh.join(" "), fill: "none", stroke: css("--muted"), "stroke-width": 1.5, "stroke-dasharray": "5 4" }, svg);

  // points: >=8px markers with a 2px surface ring; hit target larger than the mark
  const surface = css("--surface");
  for (const { r, g } of pts) {
    const cx = X(r.Q_uC), cy = Y(r.D_uC_cm2), c = css(g.color);
    el("circle", g.open ? { cx, cy, r: 4.5, fill: surface, stroke: c, "stroke-width": 2 }
      : { cx, cy, r: 5, fill: c, stroke: surface, "stroke-width": 2 }, svg);
    const hit = el("circle", { cx, cy, r: 10, fill: "transparent", tabindex: 0 }, svg);
    const p = DATA.byKey[r.citekey] || {};
    const html = `<b>${esc(p.first_author || r.citekey)} ${esc(p.year || "")}</b><br>${esc(g.label)}<br>` +
      `Q ${fmt(r.Q_uC)} µC · D ${fmt(r.D_uC_cm2)} µC cm⁻²<br>${fmt(r.current_mA_max ?? r.current_mA_min)} mA · ` +
      `${fmt(r.pulse_width_us)} µs · ${fmt(r.area_mm2)} mm²${r.area_source === "from_diameter" ? " (from diameter)" : ""}` +
      (r.body_site ? `<br>${esc(r.body_site)}` : "");
    hit.addEventListener("mousemove", (ev) => showTip(html, ev));
    hit.addEventListener("mouseleave", hideTip);
    hit.addEventListener("focus", () => { const b = hit.getBoundingClientRect(); showTip(html, { clientX: b.right, clientY: b.bottom }); });
    hit.addEventListener("blur", hideTip);
  }
}

function drawCompleteness() {
  const box = $("#comp-chart");
  box.innerHTML = "";
  const tiers = Object.keys(TIERS).filter((t) => DATA.completeness.some((c) => c.tier === t));
  const rows = [];
  for (const t of tiers) {
    rows.push({ head: t });
    for (const c of DATA.completeness.filter((c) => c.tier === t)) rows.push(c);
  }
  const W = 880, rowH = 26, headH = 34, lw = 230, vw = 96;
  const H = rows.reduce((h, r) => h + (r.head ? headH : rowH), 8);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Reporting completeness per tier and field" }, box);
  svg.style.font = `12.5px ${css("--font")}`;
  const bx = lw, bw = W - lw - vw;
  let y = 4;
  for (const r of rows) {
    if (r.head) {
      const [code, name] = TIERS[r.head];
      const n = DATA.completeness.find((c) => c.tier === r.head).n_records;
      const t = el("text", { x: 0, y: y + 22, fill: css("--ink"), "font-weight": 600 }, svg);
      t.textContent = `${code} · ${name}`;
      el("text", { x: bx, y: y + 22, fill: css("--muted") }, svg).textContent = `${n} records`;
      y += headH;
      continue;
    }
    el("text", { x: 12, y: y + 17, fill: css("--ink-2") }, svg).textContent = r.field;
    el("line", { x1: bx, x2: bx + bw, y1: y + 13, y2: y + 13, stroke: css("--grid") }, svg);
    const w = Math.max(2, (r.pct / 100) * bw);
    // 12px bar, 4px rounded data-end, square at the baseline
    el("path", { d: `M${bx},${y + 7}h${w - 4}a4,4 0 0 1 4,4v4a4,4 0 0 1 -4,4h${-(w - 4)}z`, fill: css("--series-1") }, svg);
    el("text", { x: bx + bw + 10, y: y + 17, fill: css("--ink-2"), "font-variant-numeric": "tabular-nums" }, svg)
      .textContent = `${Math.round(r.pct)}%  (${r.n_reporting}/${r.n_records})`;
    y += rowH;
  }
  const d1 = DATA.completeness.filter((c) => c.tier === "D1_full_dose");
  const low = Math.min(...d1.map((c) => c.pct)), least = d1.filter((c) => c.pct === low).map((c) => c.field.toLowerCase());
  $("#comp-caption").textContent = `Least-reported D1 ${least.length > 1 ? "fields" : "field"}: ${least.join(" and ")} ` +
    `(${Math.round(low)}%${least.length > 1 ? " each" : ""}). D3 is scored over papers whose primary or secondary contribution is interface work.`;
}

function drawMap() {
  const box = $("#map-chart");
  box.innerHTML = "";
  const tiers = Object.keys(TIERS), classes = Object.keys(CLASSES);
  const count = (c, t) => DATA.papers.filter((p) => p.contribution_class === c && p.tier === t).length;
  const max = Math.max(...classes.flatMap((c) => tiers.map((t) => count(c, t))));
  const W = 880, lw = 250, cw = (W - lw - 60) / tiers.length, ch = 30, H = 40 + classes.length * ch;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Papers by contribution class and tier" }, box);
  svg.style.font = `12.5px ${css("--font")}`;
  tiers.forEach((t, j) => {
    el("text", { x: lw + j * cw + cw / 2, y: 22, "text-anchor": "middle", fill: css("--ink-2"), "font-weight": 600 }, svg).textContent = TIERS[t][0];
  });
  el("text", { x: W - 30, y: 22, "text-anchor": "middle", fill: css("--muted") }, svg).textContent = "Total";
  const steps = ["--seq-1", "--seq-2", "--seq-3", "--seq-4", "--seq-5"].map(css);
  classes.forEach((c, i) => {
    const y = 34 + i * ch;
    el("text", { x: 0, y: y + 19, fill: css("--ink-2") }, svg).textContent = CLASSES[c];
    let tot = 0;
    tiers.forEach((t, j) => {
      const n = count(c, t);
      tot += n;
      if (!n) return;
      const k = Math.min(4, Math.floor((n / max) * 5 - 1e-9));
      const rect = el("rect", { x: lw + j * cw + 1, y: y + 1, width: cw - 2, height: ch - 2, rx: 4, fill: steps[k] }, svg);
      const txt = el("text", { x: lw + j * cw + cw / 2, y: y + 19, "text-anchor": "middle",
        fill: k >= 3 ? "#ffffff" : css("--ink"), "font-variant-numeric": "tabular-nums" }, svg);
      txt.textContent = n;
      const html = `<b>${n} paper${n > 1 ? "s" : ""}</b><br>${esc(CLASSES[c])}<br>${TIERS[t][0]} · ${TIERS[t][1]}`;
      for (const node of [rect, txt]) {
        node.addEventListener("mousemove", (ev) => showTip(html, ev));
        node.addEventListener("mouseleave", hideTip);
      }
    });
    el("text", { x: W - 30, y: y + 19, "text-anchor": "middle", fill: css("--muted"), "font-variant-numeric": "tabular-nums" }, svg).textContent = tot;
  });
}

// ---------- library ----------
const state = { q: "", cls: new Set(), tier: new Set() };
function initLibrary() {
  const facet = (id, key, labels, set) => {
    const counts = {};
    for (const p of DATA.papers) counts[p[key]] = (counts[p[key]] || 0) + 1;
    $(id).innerHTML = Object.keys(labels).filter((k) => counts[k]).map((k) =>
      `<label><input type="checkbox" value="${k}"> ${esc(Array.isArray(labels[k]) ? labels[k][0] + " · " + labels[k][1] : labels[k])}<span class="n">${counts[k]}</span></label>`).join("");
    $(id).addEventListener("change", (e) => { e.target.checked ? set.add(e.target.value) : set.delete(e.target.value); renderResults(); });
  };
  facet("#f-class", "contribution_class", CLASSES, state.cls);
  facet("#f-tier", "tier", TIERS, state.tier);
  $("#q").addEventListener("input", (e) => { state.q = e.target.value.toLowerCase(); renderResults(); });
  renderResults();
}

function renderResults() {
  const list = DATA.papers.filter((p) =>
    (!state.cls.size || state.cls.has(p.contribution_class)) && (!state.tier.size || state.tier.has(p.tier)) &&
    (!state.q || [p.title, p.first_author, p.doi, p.venue, p.citekey, p.year].join(" ").toLowerCase().includes(state.q)))
    .sort((a, b) => (b.year || 0) - (a.year || 0) || a.citekey.localeCompare(b.citekey));
  $("#count").textContent = `${list.length} of ${DATA.papers.length} papers`;
  $("#results").innerHTML = list.map((p) => `
    <article class="result">
      <div class="meta">${[p.year, p.venue].filter(Boolean).map(esc).join(" · ")}</div>
      <button class="title" type="button" aria-expanded="false" data-k="${esc(p.citekey)}">${esc(p.title)}</button>
      <div class="secondary">${esc(p.first_author)} et al.${p.doi ? ` · <a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">doi:${esc(p.doi)}</a>` : ""}</div>
      <div class="chips"><span class="chip">${esc(CLASSES[p.contribution_class] || p.contribution_class)}</span>
        <span class="chip">${esc(TIERS[p.tier] ? TIERS[p.tier][0] + " · " + TIERS[p.tier][1] : p.tier)}</span>
        ${p.secondary_class && p.secondary_class !== "none" ? `<span class="chip">also: ${esc(CLASSES[p.secondary_class])}</span>` : ""}</div>
      <div class="detail" hidden></div>
    </article>`).join("");
}

$("#results").addEventListener("click", (e) => {
  const b = e.target.closest("button.title");
  if (!b) return;
  const d = b.parentElement.querySelector(".detail");
  const open = d.hidden;
  b.setAttribute("aria-expanded", open);
  if (open && !d.innerHTML) d.innerHTML = detailHtml(DATA.byKey[b.dataset.k]);
  d.hidden = !open;
});

const SHOW = [["current_mA_min", "Current min, mA"], ["current_mA_max", "Current max, mA"], ["pulse_width_us", "Pulse width, µs"],
  ["pulse_rate_Hz", "Pulse rate, Hz"], ["area_mm2", "Electrode area, mm²"], ["Q_uC", "Charge per phase, µC"],
  ["D_uC_cm2", "Charge density, µC cm⁻²"], ["density_band", "Density band"], ["body_site", "Body site"],
  ["waveform_polarity", "Waveform"], ["compliance_V", "Compliance, V"], ["n_channels", "Channels"],
  ["pulse_rate_Hz_max", "Max pulse rate, Hz"], ["pulse_width_us_max", "Max pulse width, µs"],
  ["output_impedance_Mohm", "Output impedance, MΩ"], ["impedance_reported", "Impedance"], ["measurement_freq_Hz", "Measured at, Hz"],
  ["electrode_material", "Electrode material"]];
function detailHtml(p) {
  const recs = DATA.records.filter((r) => r.citekey === p.citekey);
  const parts = [];
  if (p.key_design_claim) parts.push(`<p><b>Design claim.</b> ${esc(p.key_design_claim)}</p>`);
  if (p.obligation_rationale) parts.push(`<p class="secondary">${esc(p.obligation_rationale)}</p>`);
  for (const r of recs) {
    const rows = SHOW.filter(([k]) => r[k] != null && r[k] !== "").map(([k, l]) =>
      `<tr><th>${l}</th><td${typeof r[k] === "number" ? ' class="num"' : ""}>${typeof r[k] === "number" ? fmt(r[k]) : esc(r[k])}</td></tr>`);
    parts.push(`<h3 style="margin-top:12px">${{ delivered: "Delivered to participants", envelope: "Device envelope (rated)", interface: "Electrode-skin interface" }[r.record_type]}</h3>` +
      (rows.length ? `<table>${rows.join("")}</table>` : `<p class="muted">No parameters reported.</p>`));
  }
  if (!recs.length) parts.push(`<p class="muted">No parameter record: this kind of paper carries no dose obligation.</p>`);
  return parts.join("");
}

// ---------- method ----------
function renderMethod() {
  $("#tier-table tbody").innerHTML = Object.entries(TIERS).map(([t, [code, name, desc]]) =>
    `<tr><td><b>${code}</b></td><td>${name}<div class="muted" style="font-size:.85rem">${desc}</div></td>` +
    `<td>${(DATA.standard[t] || []).map((f) => esc(f.label)).join(", ") || '<span class="muted">none</span>'}</td></tr>`).join("");
}

addEventListener("hashchange", route);
route();
load();
