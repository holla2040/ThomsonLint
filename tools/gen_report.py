#!/usr/bin/env python3
"""Generate a self-contained HTML review report from ThomsonLint findings JSON."""

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
.container { max-width: 960px; margin: 0 auto; padding: 16px; }
header { background: #fff; border-bottom: 3px solid #2563eb; padding: 20px 24px; margin-bottom: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
header h1 { font-size: 1.4rem; color: #1e293b; }
header .meta { font-size: .85rem; color: #64748b; margin-top: 4px; }
.stats { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
.stat { padding: 6px 14px; border-radius: 6px; font-size: .85rem; font-weight: 600; background: #f1f5f9; }
.stat.critical { background: #fef2f2; color: #991b1b; }
.stat.major { background: #fff7ed; color: #9a3412; }
.stat.minor { background: #fefce8; color: #854d0e; }
.stat.advisory { background: #eff6ff; color: #1e40af; }
.toolbar { background: #fff; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.toolbar label { font-size: .8rem; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: .03em; }
.toolbar select { padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: .85rem; background: #fff; }
.toolbar-right { margin-left: auto; display: flex; gap: 8px; }
.btn-sm { padding: 5px 12px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; font-size: .8rem; cursor: pointer; font-weight: 500; }
.btn-sm:hover { background: #f1f5f9; }
.severity-group { margin-bottom: 20px; }
.severity-group h2 { font-size: 1rem; padding: 8px 0; border-bottom: 2px solid #e2e8f0; margin-bottom: 8px; color: #334155; }
.card { background: #fff; border-radius: 8px; padding: 14px 18px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.06); border-left: 4px solid #94a3b8; }
.card.severity-Critical { border-left-color: #dc2626; }
.card.severity-Major { border-left-color: #ea580c; }
.card.severity-Minor { border-left-color: #ca8a04; }
.card.severity-Advisory { border-left-color: #2563eb; }
.card.status-Accept { opacity: .55; }
.card.status-Ignore { opacity: .35; }
.card-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: .75rem; font-weight: 700; text-transform: uppercase; color: #fff; }
.badge.Critical { background: #dc2626; }
.badge.Major { background: #ea580c; }
.badge.Minor { background: #ca8a04; }
.badge.Advisory { background: #2563eb; }
.rule-id { font-family: monospace; font-size: .82rem; color: #475569; }
.domain-tag { font-size: .72rem; background: #e2e8f0; color: #475569; padding: 1px 7px; border-radius: 3px; }
.card-summary { margin-top: 6px; font-size: .92rem; }
.card-details { margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0; font-size: .85rem; color: #475569; display: none; }
.card-details.open { display: block; }
.card-details dt { font-weight: 600; margin-top: 8px; color: #334155; }
.card-details dd { margin-left: 12px; margin-top: 2px; }
.card-details ul { margin-left: 24px; }
.toggle-details { background: none; border: none; color: #2563eb; cursor: pointer; font-size: .8rem; margin-top: 4px; padding: 0; }
.toggle-details:hover { text-decoration: underline; }
.actions { display: flex; gap: 4px; margin-left: auto; }
.actions button { padding: 3px 10px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; font-size: .78rem; cursor: pointer; font-weight: 500; }
.actions button:hover { background: #f1f5f9; }
.actions button.active-Open { background: #dbeafe; border-color: #93c5fd; color: #1e40af; }
.actions button.active-Accept { background: #dcfce7; border-color: #86efac; color: #166534; }
.actions button.active-Ignore { background: #f1f5f9; border-color: #94a3b8; color: #64748b; }
.empty { text-align: center; padding: 40px; color: #94a3b8; font-size: .95rem; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>ThomsonLint Review — <span id="projectName"></span></h1>
    <div class="meta">Review date: <span id="reviewDate"></span></div>
    <div class="stats" id="stats"></div>
  </header>
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
</div>
<script>
const FINDINGS_DATA = {{FINDINGS_JSON}};

const SEVERITY_ORDER = ["Critical", "Major", "Minor", "Advisory"];
const storageKey = "thomsonlint-review-" + FINDINGS_DATA.project_name;

function loadStatuses() {
  try { return JSON.parse(localStorage.getItem(storageKey)) || {}; } catch(e) { return {}; }
}
function saveStatuses(s) { localStorage.setItem(storageKey, JSON.stringify(s)); }
let statuses = loadStatuses();

function findingKey(issue, idx) { return issue.rule_id + ":" + idx; }

function init() {
  document.getElementById("projectName").textContent = FINDINGS_DATA.project_name;
  document.getElementById("reviewDate").textContent = FINDINGS_DATA.review_date || "N/A";

  // Populate domain filter
  const domains = [...new Set(FINDINGS_DATA.issues.map(i => i.domain))].sort();
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

  const counts = {total: 0, Critical: 0, Major: 0, Minor: 0, Advisory: 0, Open: 0, Accept: 0, Ignore: 0};

  const grouped = {};
  SEVERITY_ORDER.forEach(s => grouped[s] = []);

  FINDINGS_DATA.issues.forEach((issue, idx) => {
    const key = findingKey(issue, idx);
    const st = getStatus(key);
    counts.total++;
    counts[issue.severity] = (counts[issue.severity] || 0) + 1;
    counts[st]++;

    if (domainF && issue.domain !== domainF) return;
    if (sevF && issue.severity !== sevF) return;
    if (statusF && st !== statusF) return;

    grouped[issue.severity].push({issue, idx, key, status: st});
  });

  // Stats
  const statsEl = document.getElementById("stats");
  statsEl.innerHTML =
    `<span class="stat">Total: ${counts.total}</span>` +
    SEVERITY_ORDER.filter(s => counts[s]).map(s => `<span class="stat ${s.toLowerCase()}">${s}: ${counts[s]}</span>`).join("") +
    `<span class="stat">Open: ${counts.Open}</span>` +
    `<span class="stat">Accepted: ${counts.Accept}</span>` +
    `<span class="stat">Ignored: ${counts.Ignore}</span>`;

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
      card.innerHTML = buildCard(issue, key, status);
      section.appendChild(card);

      card.querySelector(".toggle-details").addEventListener("click", function() {
        const det = card.querySelector(".card-details");
        det.classList.toggle("open");
        this.textContent = det.classList.contains("open") ? "Hide details" : "Show details";
      });

      card.querySelectorAll(".actions button").forEach(btn => {
        btn.addEventListener("click", () => {
          statuses[key] = btn.dataset.status;
          saveStatuses(statuses);
          render();
        });
      });
    });

    container.appendChild(section);
  });

  if (!anyVisible) container.innerHTML = '<div class="empty">No findings match the current filters.</div>';
}

function buildCard(issue, key, status) {
  let details = "";
  if (issue.description) details += `<dt>Description</dt><dd>${esc(issue.description)}</dd>`;
  if (issue.component_id && issue.component_id.length) details += `<dt>Components</dt><dd>${issue.component_id.map(esc).join(", ")}</dd>`;
  if (issue.net_id && issue.net_id.length) details += `<dt>Nets</dt><dd>${issue.net_id.map(esc).join(", ")}</dd>`;
  if (issue.recommended_actions && issue.recommended_actions.length) details += `<dt>Recommended Actions</dt><dd><ul>${issue.recommended_actions.map(a => "<li>" + esc(a) + "</li>").join("")}</ul></dd>`;
  if (issue.kb_references && issue.kb_references.length) details += `<dt>KB References</dt><dd>${issue.kb_references.map(esc).join(", ")}</dd>`;

  const hasDetails = details.length > 0;

  return `<div class="card-header">
    <span class="badge ${issue.severity}">${issue.severity}</span>
    <span class="rule-id">${esc(issue.rule_id)}</span>
    <span class="domain-tag">${esc(issue.domain)}</span>
    <div class="actions">
      <button data-status="Open" class="${status === 'Open' ? 'active-Open' : ''}">Open</button>
      <button data-status="Accept" class="${status === 'Accept' ? 'active-Accept' : ''}">Accept</button>
      <button data-status="Ignore" class="${status === 'Ignore' ? 'active-Ignore' : ''}">Ignore</button>
    </div>
  </div>
  <div class="card-summary">${esc(issue.summary)}</div>
  ${hasDetails ? '<button class="toggle-details">Show details</button>' : ''}
  <dl class="card-details">${details}</dl>`;
}

function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function exportSummary() {
  let lines = [`ThomsonLint Review Summary — ${FINDINGS_DATA.project_name}`, `Date: ${FINDINGS_DATA.review_date || "N/A"}`, ""];
  SEVERITY_ORDER.forEach(sev => {
    const items = FINDINGS_DATA.issues.map((issue, idx) => ({issue, key: findingKey(issue, idx)})).filter(x => x.issue.severity === sev);
    if (!items.length) return;
    lines.push(`## ${sev}`);
    items.forEach(({issue, key}) => {
      const st = getStatus(key);
      lines.push(`[${st}] ${issue.rule_id}: ${issue.summary}`);
    });
    lines.push("");
  });
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

    # Read and parse findings JSON
    try:
        with open(args.findings_json) as f:
            findings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {args.findings_json}: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate required fields
    if "project_name" not in findings:
        print("Error: findings JSON must contain 'project_name'.", file=sys.stderr)
        sys.exit(1)
    if "issues" not in findings or not isinstance(findings["issues"], list):
        print("Error: findings JSON must contain an 'issues' array.", file=sys.stderr)
        sys.exit(1)

    # Optional schema validation
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

    # Build HTML
    findings_json_str = json.dumps(findings, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("{{PROJECT_NAME}}", findings["project_name"])
    html = html.replace("{{FINDINGS_JSON}}", findings_json_str)

    # Write output
    os.makedirs(args.output, exist_ok=True)
    # Sanitise project name for use as a filename (remove path separators, etc.)
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
