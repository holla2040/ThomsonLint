#!/usr/bin/env python3
"""Generate a self-contained HTML review report from ThomsonLint findings JSON.

The report renders three sections:
- Issues — interactive Open/Accept/Ignore triage, persisted in browser localStorage.
- Verified checks — read-only list of analyses confirmed OK.
- Cross checks — read-only list of design-wide multi-rule analyses.

Per-entry evidence[] rows render as a proper HTML table (parameter comparisons)
with free-form notes as a bulleted list below.
"""

import argparse
import json
import os
import sys

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ThomsonLint Review — {{PROJECT_NAME}}</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f5f6f8; color: #1a1a1a; line-height: 1.5; }
.container { max-width: 1040px; margin: 0 auto; padding: 16px; }
header { background: #fff; border-bottom: 3px solid #2563eb; padding: 20px 24px; margin-bottom: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
header h1 { font-size: 1.4rem; color: #1e293b; }
header .meta { font-size: .85rem; color: #64748b; margin-top: 4px; }
.stats { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.stat { padding: 6px 14px; border-radius: 6px; font-size: .85rem; font-weight: 600; background: #f1f5f9; }
.stat.critical { background: #fef2f2; color: #991b1b; }
.stat.major { background: #fff7ed; color: #9a3412; }
.stat.minor { background: #fefce8; color: #854d0e; }
.stat.advisory { background: #eff6ff; color: #1e40af; }
.stat.verified { background: #ecfdf5; color: #065f46; }
.stat.cross { background: #f5f3ff; color: #5b21b6; }
.toolbar { background: #fff; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.toolbar label { font-size: .8rem; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: .03em; }
.toolbar select { padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: .85rem; background: #fff; }
.toolbar-right { margin-left: auto; display: flex; gap: 8px; }
.btn-sm { padding: 5px 12px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; font-size: .8rem; cursor: pointer; font-weight: 500; }
.btn-sm:hover { background: #f1f5f9; }
.section { margin-top: 28px; }
.section-header { font-size: 1.1rem; padding: 10px 0; border-bottom: 2px solid #cbd5e1; margin-bottom: 12px; color: #1e293b; }
.section-intro { font-size: .85rem; color: #64748b; margin-bottom: 8px; }
.severity-group { margin-bottom: 20px; }
.severity-group h2 { font-size: 1rem; padding: 8px 0; border-bottom: 2px solid #e2e8f0; margin-bottom: 8px; color: #334155; }
.card { background: #fff; border-radius: 8px; padding: 14px 18px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.06); border-left: 4px solid #94a3b8; }
.card.severity-Critical { border-left-color: #dc2626; }
.card.severity-Major { border-left-color: #ea580c; }
.card.severity-Minor { border-left-color: #ca8a04; }
.card.severity-Advisory { border-left-color: #2563eb; }
.card.kind-verified { border-left-color: #10b981; }
.card.kind-cross { border-left-color: #7c3aed; }
.card.status-Accept { opacity: .55; }
.card.status-Ignore { opacity: .35; }
.card-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 700; text-transform: uppercase; color: #fff; }
.badge.Critical { background: #dc2626; }
.badge.Major { background: #ea580c; }
.badge.Minor { background: #ca8a04; }
.badge.Advisory { background: #2563eb; }
.badge.Informational { background: #64748b; }
.badge.Verified { background: #10b981; }
.badge.Cross { background: #7c3aed; }
.rule-id { font-family: monospace; font-size: .82rem; color: #475569; }
.domain-tag { font-size: .72rem; background: #e2e8f0; color: #475569; padding: 1px 7px; border-radius: 3px; }
.card-summary { margin-top: 6px; font-size: .92rem; }
.card-details { margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0; font-size: .85rem; color: #475569; display: none; }
.card-details.open { display: block; }
.card-details dt { font-weight: 600; margin-top: 10px; color: #334155; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }
.card-details dd { margin-left: 0; margin-top: 4px; }
.card-details dd p { margin-bottom: 4px; }
.card-details ul { margin-left: 24px; margin-top: 4px; }
.evidence-table { width: 100%; border-collapse: collapse; margin-top: 4px; font-size: .82rem; background: #fafbfc; border: 1px solid #e2e8f0; border-radius: 4px; overflow: hidden; }
.evidence-table th { background: #f1f5f9; text-align: left; padding: 5px 10px; font-weight: 600; color: #334155; font-size: .76rem; text-transform: uppercase; letter-spacing: .03em; border-bottom: 1px solid #e2e8f0; }
.evidence-table td { padding: 5px 10px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
.evidence-table tr:last-child td { border-bottom: none; }
.evidence-table .verdict { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: .72rem; font-weight: 600; text-transform: uppercase; }
.evidence-table .verdict-ok { background: #dcfce7; color: #166534; }
.evidence-table .verdict-marginal { background: #fef3c7; color: #92400e; }
.evidence-table .verdict-fail { background: #fee2e2; color: #991b1b; }
.evidence-table .verdict-unverified { background: #e0e7ff; color: #3730a3; }
.evidence-table .verdict-na { background: #f1f5f9; color: #64748b; }
.evidence-table .source { color: #64748b; font-size: .78rem; font-family: monospace; }
.evidence-notes { margin-top: 6px; }
.evidence-notes li { margin-left: 18px; font-size: .82rem; }
.evidence-notes .source { color: #64748b; font-size: .76rem; font-family: monospace; }
.evidence-thumb { max-width: 200px; max-height: 160px; display: block; margin: 4px 0; border: 1px solid #cbd5e1; border-radius: 3px; cursor: zoom-in; }
.source-docs .evidence-thumb { max-width: 80px; max-height: 60px; display: inline-block; margin: 2px 6px -4px 0; vertical-align: middle; }
.toggle-details { background: none; border: none; color: #2563eb; cursor: pointer; font-size: .8rem; margin-top: 4px; padding: 0; }
.toggle-details:hover { text-decoration: underline; }
.actions { display: flex; gap: 4px; margin-left: auto; }
.actions button { padding: 3px 10px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; font-size: .78rem; cursor: pointer; font-weight: 500; }
.actions button:hover { background: #f1f5f9; }
.actions button.active-Open { background: #dbeafe; border-color: #93c5fd; color: #1e40af; }
.actions button.active-Accept { background: #dcfce7; border-color: #86efac; color: #166534; }
.actions button.active-Ignore { background: #f1f5f9; border-color: #94a3b8; color: #64748b; }
.empty { text-align: center; padding: 40px; color: #94a3b8; font-size: .95rem; }
.summary-table { width: 100%; border-collapse: collapse; margin-bottom: 16px; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); font-size: .85rem; }
.summary-table th { background: #f1f5f9; text-align: left; padding: 8px 12px; font-weight: 600; color: #334155; border-bottom: 2px solid #e2e8f0; }
.summary-table td { padding: 6px 12px; border-bottom: 1px solid #e2e8f0; }
.summary-table tr:last-child td { border-bottom: none; }
.summary-table .sev-badge { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: .75rem; font-weight: 700; text-transform: uppercase; color: #fff; }
.summary-table .sev-badge.Critical { background: #dc2626; }
.summary-table .sev-badge.Major { background: #ea580c; }
.summary-table .sev-badge.Minor { background: #ca8a04; }
.summary-table .sev-badge.Advisory { background: #2563eb; }
.summary-table .mono { font-family: monospace; font-size: .82rem; color: #475569; }
.source-docs { background: #fff; padding: 10px 16px; border-radius: 8px; margin-bottom: 16px; font-size: .82rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.source-docs h3 { font-size: .82rem; text-transform: uppercase; letter-spacing: .03em; color: #64748b; margin-bottom: 6px; }
.source-docs ul { list-style: none; }
.source-docs li { padding: 2px 0; font-family: monospace; color: #334155; }
.source-docs .kind { display: inline-block; min-width: 100px; color: #64748b; font-size: .75rem; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>ThomsonLint Review — <span id="projectName"></span></h1>
    <div class="meta">Review date: <span id="reviewDate"></span></div>
    <div class="stats" id="stats"></div>
  </header>
  <div id="sourceDocs"></div>
  <div id="summaryTable"></div>
  <div class="toolbar">
    <label>Domain</label>
    <select id="filterDomain"><option value="">All</option></select>
    <label>Severity</label>
    <select id="filterSeverity"><option value="">All</option></select>
    <label>Status</label>
    <select id="filterStatus"><option value="">All</option><option>Open</option><option>Accept</option><option>Ignore</option></select>
    <div class="toolbar-right">
      <button class="btn-sm" id="btnReset">Reset All</button>
      <button class="btn-sm" id="btnExport">Export Summary</button>
    </div>
  </div>
  <div id="findings"></div>
  <div id="verifiedSection"></div>
  <div id="crossSection"></div>
</div>
<script>
const FINDINGS_DATA = {{FINDINGS_JSON}};
const ISSUES = FINDINGS_DATA.issues || [];
const VERIFIED = FINDINGS_DATA.verified_checks || [];
const CROSS = FINDINGS_DATA.cross_checks || [];
const SOURCES = FINDINGS_DATA.source_documents || [];

const SEVERITY_ORDER = ["Critical", "Major", "Minor", "Advisory", "Informational"];
const storageKey = "thomsonlint-review-" + FINDINGS_DATA.project_name;

function loadStatuses() {
  try { return JSON.parse(localStorage.getItem(storageKey)) || {}; } catch(e) { return {}; }
}
function saveStatuses(s) { localStorage.setItem(storageKey, JSON.stringify(s)); }
let statuses = loadStatuses();

function findingKey(issue, idx) { return (issue.rule_id || "_") + ":" + idx; }

function init() {
  document.getElementById("projectName").textContent = FINDINGS_DATA.project_name;
  document.getElementById("reviewDate").textContent = FINDINGS_DATA.review_date || "N/A";

  // Source documents block
  if (SOURCES.length) {
    const html = '<div class="source-docs"><h3>Source documents (' + SOURCES.length + ')</h3><ul>' +
      SOURCES.map(s => {
        const href = imageHrefFromSource(s.path);
        const thumb = href ? renderImageThumb(href, s.label || s.path) : '';
        return '<li><span class="kind">' + esc(s.kind || "—") + '</span>' + thumb + esc(s.path) + (s.label ? ' — ' + esc(s.label) : '') + '</li>';
      }).join("") +
      '</ul></div>';
    document.getElementById("sourceDocs").innerHTML = html;
  }

  // Populate domain filter (across all sections)
  const domains = [...new Set([...ISSUES, ...VERIFIED, ...CROSS].map(i => i.domain).filter(Boolean))].sort();
  const domainSel = document.getElementById("filterDomain");
  domains.forEach(d => { const o = document.createElement("option"); o.value = d; o.textContent = d; domainSel.appendChild(o); });

  // Populate severity filter
  const sevSel = document.getElementById("filterSeverity");
  SEVERITY_ORDER.forEach(s => { const o = document.createElement("option"); o.value = s; o.textContent = s; sevSel.appendChild(o); });

  render();

  domainSel.addEventListener("change", render);
  sevSel.addEventListener("change", render);
  document.getElementById("filterStatus").addEventListener("change", render);
  document.getElementById("btnReset").addEventListener("click", () => { if(confirm("Reset all statuses to Open?")) { statuses = {}; saveStatuses(statuses); render(); } });
  document.getElementById("btnExport").addEventListener("click", exportSummary);
}

function getStatus(key) { return statuses[key] || "Open"; }

function render() {
  const domainF = document.getElementById("filterDomain").value;
  const sevF = document.getElementById("filterSeverity").value;
  const statusF = document.getElementById("filterStatus").value;

  const container = document.getElementById("findings");
  container.innerHTML = "";

  const counts = {total: 0, Critical: 0, Major: 0, Minor: 0, Advisory: 0, Informational: 0, Open: 0, Accept: 0, Ignore: 0};

  const grouped = {};
  SEVERITY_ORDER.forEach(s => grouped[s] = []);

  ISSUES.forEach((issue, idx) => {
    const key = findingKey(issue, idx);
    const st = getStatus(key);
    counts.total++;
    counts[issue.severity] = (counts[issue.severity] || 0) + 1;
    counts[st]++;

    if (domainF && issue.domain !== domainF) return;
    if (sevF && issue.severity !== sevF) return;
    if (statusF && st !== statusF) return;

    grouped[issue.severity || "Informational"].push({issue, idx, key, status: st});
  });

  // Stats
  const statsEl = document.getElementById("stats");
  statsEl.innerHTML =
    `<span class="stat">Issues: ${counts.total}</span>` +
    SEVERITY_ORDER.filter(s => counts[s]).map(s => `<span class="stat ${s.toLowerCase()}">${s}: ${counts[s]}</span>`).join("") +
    `<span class="stat">Open: ${counts.Open}</span>` +
    `<span class="stat">Accepted: ${counts.Accept}</span>` +
    `<span class="stat">Ignored: ${counts.Ignore}</span>` +
    (VERIFIED.length ? `<span class="stat verified">Verified checks: ${VERIFIED.length}</span>` : "") +
    (CROSS.length ? `<span class="stat cross">Cross checks: ${CROSS.length}</span>` : "");

  // Summary table (issues only)
  const tableEl = document.getElementById("summaryTable");
  let thtml = '<table class="summary-table"><thead><tr><th>#</th><th>Severity</th><th>Rule ID</th><th>Summary</th></tr></thead><tbody>';
  let rowNum = 0;
  SEVERITY_ORDER.forEach(sev => {
    ISSUES.forEach((issue, idx) => {
      if (issue.severity !== sev) return;
      const key = findingKey(issue, idx);
      const st = getStatus(key);
      if (domainF && issue.domain !== domainF) return;
      if (sevF && issue.severity !== sevF) return;
      if (statusF && st !== statusF) return;
      rowNum++;
      thtml += `<tr><td>${rowNum}</td><td><span class="sev-badge ${issue.severity}">${issue.severity}</span></td><td class="mono">${esc(ruleIdStr(issue.rule_id))}</td><td>${esc(issue.summary)}</td></tr>`;
    });
  });
  thtml += '</tbody></table>';
  tableEl.innerHTML = rowNum ? thtml : '';

  let anyVisible = false;
  SEVERITY_ORDER.forEach(sev => {
    const items = grouped[sev];
    if (!items.length) return;
    anyVisible = true;

    const section = document.createElement("div");
    section.className = "severity-group";
    section.innerHTML = `<h2>${sev} (${items.length})</h2>`;

    items.forEach(({issue, idx, key, status}) => {
      const card = document.createElement("div");
      card.className = `card severity-${issue.severity} status-${status}`;
      card.innerHTML = buildIssueCard(issue, key, status);
      section.appendChild(card);
      attachCardHandlers(card, key);
    });

    container.appendChild(section);
  });

  if (!anyVisible && rowNum === 0) container.innerHTML = '<div class="empty">No issues match the current filters.</div>';

  // Static sections (verified_checks, cross_checks) — not filtered
  document.getElementById("verifiedSection").innerHTML = renderStaticSection(
    "Verified checks",
    "Analyses the reviewer performed where the result was OK. Read-only.",
    VERIFIED, "verified"
  );
  document.getElementById("crossSection").innerHTML = renderStaticSection(
    "Cross-cutting checks",
    "Design-wide analyses spanning multiple ontology rules. Read-only.",
    CROSS, "cross"
  );
}

function attachCardHandlers(card, key) {
  const toggleBtn = card.querySelector(".toggle-details");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", function() {
      const det = card.querySelector(".card-details");
      det.classList.toggle("open");
      this.textContent = det.classList.contains("open") ? "Hide details" : "Show details";
    });
  }
  card.querySelectorAll(".actions button").forEach(btn => {
    btn.addEventListener("click", () => {
      statuses[key] = btn.dataset.status;
      saveStatuses(statuses);
      render();
    });
  });
}

function renderStaticSection(title, intro, items, kind) {
  if (!items.length) return "";
  const cards = items.map((it, idx) => {
    const inner = buildStaticCard(it, kind);
    return `<div class="card kind-${kind}">${inner}</div>`;
  }).join("");
  const html =
    `<div class="section"><div class="section-header">${esc(title)} (${items.length})</div>` +
    `<div class="section-intro">${esc(intro)}</div>` +
    cards + `</div>`;
  // Attach toggle handlers after insertion via setTimeout
  setTimeout(() => {
    document.querySelectorAll(`.card.kind-${kind} .toggle-details`).forEach(btn => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function() {
        const det = this.parentElement.querySelector(".card-details");
        det.classList.toggle("open");
        this.textContent = det.classList.contains("open") ? "Hide details" : "Show details";
      });
    });
  }, 0);
  return html;
}

function ruleIdStr(rid) {
  if (!rid) return "";
  if (Array.isArray(rid)) return rid.join(", ");
  return rid;
}

function imageHrefFromSource(s) {
  if (!s) return null;
  const m = String(s).match(/(\S+\.(?:png|jpe?g|svg))/i);
  if (!m) return null;
  let href = m[1];
  // The HTML report is generated alongside the PNGs in exports/, so paths
  // written as "exports/foo.png" (per the schema's repo-root convention)
  // need their leading "exports/" segment stripped to resolve correctly
  // against the report's own location.
  if (href.indexOf("exports/") === 0) href = href.substring("exports/".length);
  return href;
}

function renderImageThumb(href, alt) {
  return `<a href="${esc(href)}" target="_blank"><img src="${esc(href)}" class="evidence-thumb" loading="lazy" alt="${esc(alt || href)}"></a>`;
}

function renderSourceCell(s) {
  const href = imageHrefFromSource(s);
  if (!href) return esc(s || "");
  return `${renderImageThumb(href, s)}<div class="source">${esc(s)}</div>`;
}

function buildEvidenceHtml(evidence) {
  if (!evidence || !evidence.length) return "";
  const paramRows = evidence.filter(e => e.label && (e.datasheet || e.design || e.margin || e.verdict));
  const noteRows = evidence.filter(e => !(e.label && (e.datasheet || e.design || e.margin || e.verdict)));

  let html = "";
  if (paramRows.length) {
    html += '<table class="evidence-table"><thead><tr><th>Parameter</th><th>Datasheet / spec</th><th>Design</th><th>Margin</th><th>Verdict</th><th>Source</th></tr></thead><tbody>';
    paramRows.forEach(r => {
      const verdictKey = (r.verdict || "").replace("/", "");
      const verdictHtml = r.verdict ? `<span class="verdict verdict-${verdictKey}">${esc(r.verdict)}</span>` : "";
      const labelCell = esc(r.label) + (r.note ? `<br><span class="source">${esc(r.note)}</span>` : "");
      html += `<tr><td>${labelCell}</td><td>${esc(r.datasheet || "")}</td><td>${esc(r.design || "")}</td><td>${esc(r.margin || "")}</td><td>${verdictHtml}</td><td class="source">${renderSourceCell(r.source)}</td></tr>`;
    });
    html += '</tbody></table>';
  }
  if (noteRows.length) {
    html += '<ul class="evidence-notes">';
    noteRows.forEach(r => {
      const txt = r.note || r.label || "";
      const srcStr = r.source || "";
      const href = imageHrefFromSource(srcStr);
      const thumbHtml = href ? renderImageThumb(href, srcStr) : "";
      html += `<li>${esc(txt)} <span class="source">[${esc(srcStr)}]</span>${thumbHtml}</li>`;
    });
    html += '</ul>';
  }
  return html;
}

function buildDetails(item) {
  let details = "";
  if (item.description) details += `<dt>Description</dt><dd>${esc(item.description)}</dd>`;
  const evHtml = buildEvidenceHtml(item.evidence);
  if (evHtml) details += `<dt>Evidence</dt><dd>${evHtml}</dd>`;
  if (item.component_id && item.component_id.length) details += `<dt>Components</dt><dd>${item.component_id.map(esc).join(", ")}</dd>`;
  if (item.net_id && item.net_id.length) details += `<dt>Nets</dt><dd>${item.net_id.map(esc).join(", ")}</dd>`;
  if (item.recommended_actions && item.recommended_actions.length) details += `<dt>Recommended Actions</dt><dd><ul>${item.recommended_actions.map(a => "<li>" + esc(a) + "</li>").join("")}</ul></dd>`;
  if (item.kb_references && item.kb_references.length) details += `<dt>KB References</dt><dd>${item.kb_references.map(esc).join(", ")}</dd>`;
  return details;
}

function buildIssueCard(issue, key, status) {
  const details = buildDetails(issue);
  const hasDetails = details.length > 0;
  return `<div class="card-header">
    <span class="badge ${issue.severity}">${esc(issue.severity || "")}</span>
    <span class="rule-id">${esc(ruleIdStr(issue.rule_id))}</span>
    <span class="domain-tag">${esc(issue.domain || "")}</span>
    <div class="actions">
      <button data-status="Open" class="${status === 'Open' ? 'active-Open' : ''}">Open</button>
      <button data-status="Accept" class="${status === 'Accept' ? 'active-Accept' : ''}">Accept</button>
      <button data-status="Ignore" class="${status === 'Ignore' ? 'active-Ignore' : ''}">Ignore</button>
    </div>
  </div>
  <div class="card-summary">${esc(issue.summary || "")}</div>
  ${hasDetails ? '<button class="toggle-details">Show details</button>' : ''}
  <dl class="card-details">${details}</dl>`;
}

function buildStaticCard(item, kind) {
  const details = buildDetails(item);
  const hasDetails = details.length > 0;
  const badgeLabel = kind === "verified" ? "Verified" : "Cross";
  return `<div class="card-header">
    <span class="badge ${badgeLabel}">${badgeLabel}</span>
    <span class="rule-id">${esc(ruleIdStr(item.rule_id))}</span>
    <span class="domain-tag">${esc(item.domain || "")}</span>
  </div>
  <div class="card-summary">${esc(item.summary || "")}</div>
  ${hasDetails ? '<button class="toggle-details">Show details</button>' : ''}
  <dl class="card-details">${details}</dl>`;
}

function esc(s) { if (s === undefined || s === null) return ""; const d = document.createElement("div"); d.textContent = String(s); return d.innerHTML; }

function exportSummary() {
  let lines = [`ThomsonLint Review Summary — ${FINDINGS_DATA.project_name}`, `Date: ${FINDINGS_DATA.review_date || "N/A"}`, ""];
  SEVERITY_ORDER.forEach(sev => {
    const items = ISSUES.map((issue, idx) => ({issue, key: findingKey(issue, idx)})).filter(x => x.issue.severity === sev);
    if (!items.length) return;
    lines.push(`## ${sev}`);
    items.forEach(({issue, key}) => {
      const st = getStatus(key);
      lines.push(`[${st}] ${ruleIdStr(issue.rule_id)}: ${issue.summary}`);
    });
    lines.push("");
  });
  if (VERIFIED.length) {
    lines.push("## Verified checks");
    VERIFIED.forEach(v => lines.push(`- ${ruleIdStr(v.rule_id) || "(no rule)"}: ${v.summary}`));
    lines.push("");
  }
  if (CROSS.length) {
    lines.push("## Cross checks");
    CROSS.forEach(c => lines.push(`- ${ruleIdStr(c.rule_id) || "(no rule)"}: ${c.summary}`));
    lines.push("");
  }
  navigator.clipboard.writeText(lines.join("\n")).then(() => alert("Summary copied to clipboard."), () => alert("Failed to copy to clipboard."));
}

init();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate an HTML review report from ThomsonLint findings JSON.")
    parser.add_argument("findings_json", help="Path to the findings JSON file.")
    parser.add_argument("--output", default="exports/", help="Output directory (default: exports/).")
    args = parser.parse_args()

    try:
        with open(args.findings_json) as f:
            findings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {args.findings_json}: {e}", file=sys.stderr)
        sys.exit(1)

    if "project_name" not in findings:
        print("Error: findings JSON must contain 'project_name'.", file=sys.stderr)
        sys.exit(1)
    if "issues" not in findings or not isinstance(findings["issues"], list):
        print("Error: findings JSON must contain an 'issues' array.", file=sys.stderr)
        sys.exit(1)

    try:
        import jsonschema
        schema_path = os.path.join(os.path.dirname(__file__), "..", "tests", "findings_schema.json")
        if os.path.exists(schema_path):
            with open(schema_path) as f:
                schema = json.load(f)
            jsonschema.validate(instance=findings, schema=schema)
            print("Findings JSON validated against schema.")
    except ImportError:
        pass
    except jsonschema.exceptions.ValidationError as e:
        print(f"Schema validation error: {e.message}", file=sys.stderr)
        sys.exit(1)

    findings_json_str = json.dumps(findings, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("{{PROJECT_NAME}}", findings["project_name"])
    html = html.replace("{{FINDINGS_JSON}}", findings_json_str)

    os.makedirs(args.output, exist_ok=True)
    safe_name = findings["project_name"].replace(" ", "_")
    for ch in r'/\:*?"<>|':
        safe_name = safe_name.replace(ch, "_")
    out_name = safe_name + "-review.html"
    out_path = os.path.join(args.output, out_name)
    with open(out_path, "w") as f:
        f.write(html)

    print(f"Report generated: {out_path}")


if __name__ == "__main__":
    main()
