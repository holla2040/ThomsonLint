#!/usr/bin/env python3
"""Mechanical coverage validator for ThomsonLint findings JSON.

Runs after the agent writes findings.json and before the HTML report is generated.
Removes "agent forgot" as a failure mode by checking, mechanically, that every
input the reviewer consumed is cited in the findings.

Checks performed:

1. Schema validation against tests/findings_schema.json.
2. Source-document coverage: every PDF, schematic/board/stackup JSON export, and
   layer-image / silkscreen / schematic-sheet PNG (or JPG) in the findings
   file's directory must be cited in at least one finding's evidence[].source.
   Uncited inputs are reported as gaps.
3. source_documents[] consistency: every declared source_documents entry must
   appear in some evidence.source; every evidence.source that names a file
   should appear in source_documents (warning, not hard failure).
4. Field completeness: issues must have severity, description, and at least
   one recommended_action; every evidence row must have a non-empty source.
5. Ontology rule citation summary: which ontology rule_ids are cited and which
   are not. Advisory only — many rules legitimately won't apply to any given
   design.

Exit code 0 if all hard checks pass, 1 otherwise. Soft warnings do not fail.
"""

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "tests" / "findings_schema.json"
ONTOLOGY_PATH = REPO_ROOT / "ontology" / "ontology.json"

DESIGN_INPUT_SUFFIXES = (
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    "-thomson-export-sch.json",
    "-thomson-export-brd.json",
    "-thomson-export-stack.json",
)


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def schema_validate(findings, hard_errors):
    try:
        import jsonschema
    except ImportError:
        hard_errors.append("jsonschema not installed; run: pip install jsonschema")
        return
    try:
        schema = load_json(SCHEMA_PATH)
        jsonschema.validate(findings, schema)
    except Exception as e:
        hard_errors.append(f"Schema validation failed: {e}")


def iter_findings(findings):
    """Yield (section_name, finding) for every finding across all three arrays."""
    for section in ("issues", "verified_checks", "cross_checks"):
        for f in findings.get(section, []) or []:
            yield section, f


def collect_evidence_sources(findings):
    """Return a set of every evidence.source string used anywhere."""
    sources = set()
    for _, f in iter_findings(findings):
        for ev in f.get("evidence", []) or []:
            src = (ev.get("source") or "").strip()
            if src:
                sources.add(src)
    return sources


def list_design_inputs(findings_dir: Path):
    """List candidate input files in the findings file's directory."""
    if not findings_dir.is_dir():
        return []
    inputs = []
    for child in sorted(findings_dir.iterdir()):
        if not child.is_file():
            continue
        name = child.name
        if any(name.lower().endswith(suf) for suf in DESIGN_INPUT_SUFFIXES):
            inputs.append(child)
    return inputs


def check_input_coverage(findings, findings_dir: Path, hard_errors, warnings):
    """Every PDF / sch / brd export in findings_dir must be cited."""
    inputs = list_design_inputs(findings_dir)
    if not inputs:
        warnings.append(f"No design inputs (PDF / sch+brd+stack JSON / layer images) found in {findings_dir} — nothing to cross-reference.")
        return [], []

    sources = collect_evidence_sources(findings)
    cited = []
    uncited = []
    for path in inputs:
        # Cited if the filename or path appears in any evidence.source string.
        rel = os.path.relpath(path, REPO_ROOT)
        if any(path.name in s or rel in s for s in sources):
            cited.append(path)
        else:
            uncited.append(path)

    if uncited:
        hard_errors.append(
            f"{len(uncited)} design input(s) present but not cited in any evidence.source: "
            + ", ".join(p.name for p in uncited)
            + ". Either add a finding/verified_check/cross_check that cites the file, or "
            "add an Informational entry stating why it is not in scope."
        )
    return cited, uncited


def check_source_documents_consistency(findings, warnings):
    declared = {sd.get("path") for sd in (findings.get("source_documents") or []) if sd.get("path")}
    cited = collect_evidence_sources(findings)

    if not declared:
        warnings.append("source_documents[] is empty. Recommended: declare every input you consumed so coverage is explicit.")

    declared_uncited = []
    for d in sorted(declared):
        if not any(d in c or os.path.basename(d) in c for c in cited):
            declared_uncited.append(d)
    if declared_uncited:
        warnings.append(
            "Declared in source_documents[] but never cited in any evidence.source: "
            + ", ".join(declared_uncited)
        )


def check_field_completeness(findings, hard_errors, warnings):
    for i, issue in enumerate(findings.get("issues", []) or []):
        ctx = f"issues[{i}] ({issue.get('rule_id', '?')})"
        if not issue.get("severity"):
            hard_errors.append(f"{ctx}: missing severity.")
        if not (issue.get("description") or "").strip():
            hard_errors.append(f"{ctx}: missing description.")
        if not (issue.get("recommended_actions") or []):
            hard_errors.append(f"{ctx}: missing recommended_actions (issues must propose corrective action).")
        if not (issue.get("evidence") or []):
            warnings.append(f"{ctx}: no evidence[] rows. Issues backed by datasheet reads or measurements should cite evidence.")
        for j, ev in enumerate(issue.get("evidence", []) or []):
            if not (ev.get("source") or "").strip():
                hard_errors.append(f"{ctx}.evidence[{j}]: missing source.")

    for section in ("verified_checks", "cross_checks"):
        for i, entry in enumerate(findings.get(section, []) or []):
            ctx = f"{section}[{i}] ({entry.get('rule_id', '?')})"
            if not (entry.get("evidence") or []):
                warnings.append(f"{ctx}: no evidence[] rows — what was actually checked?")
            for j, ev in enumerate(entry.get("evidence", []) or []):
                if not (ev.get("source") or "").strip():
                    hard_errors.append(f"{ctx}.evidence[{j}]: missing source.")


def collect_cited_rule_ids(findings):
    cited = set()
    for _, f in iter_findings(findings):
        rid = f.get("rule_id")
        if isinstance(rid, str):
            cited.add(rid)
        elif isinstance(rid, list):
            cited.update(rid)
    return cited


def ontology_coverage_summary(findings):
    """Advisory: report which ontology rules are cited vs. uncited."""
    if not ONTOLOGY_PATH.exists():
        return None
    try:
        ontology = load_json(ONTOLOGY_PATH)
    except Exception:
        return None
    all_rule_ids = {r.get("id") for r in (ontology.get("rules") or []) if r.get("id")}
    cited = collect_cited_rule_ids(findings) & all_rule_ids
    uncited = sorted(all_rule_ids - cited)
    return {
        "total_rules": len(all_rule_ids),
        "cited_rules": len(cited),
        "uncited_rules": uncited,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Mechanical coverage validator for ThomsonLint findings.")
    p.add_argument("findings_path", help="Path to <project>-findings.json")
    p.add_argument("--show-uncited-rules", action="store_true",
                   help="Print the full list of ontology rules not cited (default: summary count only).")
    args = p.parse_args(argv)

    findings_path = Path(args.findings_path).resolve()
    if not findings_path.is_file():
        print(f"ERROR: findings file not found: {findings_path}", file=sys.stderr)
        return 2

    findings = load_json(findings_path)
    findings_dir = findings_path.parent

    hard_errors = []
    warnings = []

    schema_validate(findings, hard_errors)
    cited_inputs, uncited_inputs = check_input_coverage(findings, findings_dir, hard_errors, warnings)
    check_source_documents_consistency(findings, warnings)
    check_field_completeness(findings, hard_errors, warnings)

    print(f"\n=== ThomsonLint findings coverage report — {findings_path.name} ===\n")

    counts = {s: len(findings.get(s, []) or []) for s in ("issues", "verified_checks", "cross_checks")}
    print(f"Findings: {counts['issues']} issues, {counts['verified_checks']} verified_checks, {counts['cross_checks']} cross_checks")

    print(f"\nDesign-input citation:")
    print(f"  cited:   {len(cited_inputs)} file(s)")
    for p_ in cited_inputs:
        print(f"    + {p_.name}")
    print(f"  uncited: {len(uncited_inputs)} file(s)")
    for p_ in uncited_inputs:
        print(f"    - {p_.name}")

    coverage = ontology_coverage_summary(findings)
    if coverage:
        print(f"\nOntology rule citation: {coverage['cited_rules']}/{coverage['total_rules']} rules cited.")
        if args.show_uncited_rules and coverage["uncited_rules"]:
            print("Uncited rules:")
            for rid in coverage["uncited_rules"]:
                print(f"  - {rid}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    if hard_errors:
        print(f"\nERRORS ({len(hard_errors)}):")
        for e in hard_errors:
            print(f"  X {e}")
        print("\nResult: FAIL — review is incomplete; address the errors above before generating the HTML report.")
        return 1

    print("\nResult: PASS — coverage checks satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
