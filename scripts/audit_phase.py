#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PHASES = {
    1: "Ingest ThomsonLint Workflow",
    2: "Inspect Inputs and Datasheets",
    3: "Setup and Tool Preflight",
    4: "Run Integrated Converter",
    5: "Inspect Findings Framework",
    6: "Full BOM Datasheet Retrieval",
    7: "Enforce Image Review Gate",
    8: "Review Schematic Evidence FULL",
    9: "Full Board/Layout JSON Evaluation",
    10: "Review Stackup and Manufacturing Evidence FULL",
    11: "Review BOM and Component Evidence FULL",
    12: "Review Image Evidence FULL",
    13: "Review Datasheet Evidence FULL",
    14: "Cross-Source Consistency Review",
    15: "Pre-Findings Gate Check",
    16: "Candidate Finding Development",
    17: "Write Findings JSON",
    18: "Validate and Repair Findings",
    19: "Generate Report",
    20: "Final Summary",
}


def fail(msg: str) -> None:
    print(f"INVALID: {msg}")
    sys.exit(1)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"missing JSON file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON in {path}: {exc}")


def require_file(path: Path) -> None:
    if not path.is_file():
        fail(f"missing file: {path}")


def require_true(path: Path, field: str) -> None:
    data = load_json(path)
    val: Any = data
    for part in field.split("."):
        if not isinstance(val, dict) or part not in val:
            fail(f"{path} missing field {field}")
        val = val[part]
    if val is not True:
        fail(f"{path} field {field} is not true; got {val!r}")


def load_checkpoint_rows(path: Path) -> list[dict[str, Any]]:
    require_file(path)
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:
            fail(f"invalid JSONL in {path} row {i}: {exc}")
    return rows


def audit_checkpoint(exports: Path, project: str, phase: int) -> None:
    path = exports / f"{project}-phase-checkpoints.jsonl"
    rows = load_checkpoint_rows(path)
    matches = [r for r in rows if r.get("phase_number") == phase]

    if len(matches) != 1:
        fail(f"expected exactly one checkpoint row for phase {phase}, found {len(matches)}")

    row = matches[0]
    expected_name = PHASES[phase]
    if row.get("phase_name") != expected_name:
        fail(f"phase {phase} name mismatch: got {row.get('phase_name')!r}, expected {expected_name!r}")

    required_keys = [
        "phase_number",
        "phase_name",
        "started_at_utc",
        "completed_at_utc",
        "required_artifacts",
        "artifacts_verified",
        "validation_artifacts",
        "validation_passed",
        "blockers",
        "phase_passed",
    ]
    for key in required_keys:
        if key not in row:
            fail(f"phase {phase} checkpoint missing key: {key}")

    if row.get("phase_passed") is not True:
        fail(f"phase {phase} checkpoint phase_passed is not true")


def audit_phase(exports: Path, project: str, phase: int) -> None:
    audit_checkpoint(exports, project, phase)

    if phase == 3:
        require_true(exports / "tool-preflight-status.json", "overall_pass")

    elif phase == 4:
        required = [
            exports / f"{project}-bom.json",
            exports / f"{project}-thomson-export-sch.json",
            exports / f"{project}-thomson-export-brd.json",
            exports / f"{project}-thomson-export-stack.json",
        ]
        for path in required:
            data = load_json(path)
            if not isinstance(data, (dict, list)):
                fail(f"{path} did not parse as JSON object/list")

    elif phase == 6:
        path = exports / "datasheets" / "datasheet_manifest_validation.json"
        data = load_json(path)
        for field in [
            "bom_csv_path",
            "bom_raw_row_count",
            "manifest_path",
            "manifest_row_count",
            "covered_bom_row_indexes",
            "uncovered_bom_row_indexes",
            "status_counts",
            "found_rows_missing_local_files",
            "local_file_validation_pass",
            "coverage_pass",
            "overall_pass",
            "datasheet_storage_dir",
            "downloaded_file_count",
            "local_existing_file_count",
            "search_attempted_count",
            "candidate_url_count",
            "download_failed_count",
            "forbidden_statuses_present",
        ]:
            if field not in data:
                fail(f"{path} missing field {field}")

        if data.get("uncovered_bom_row_indexes"):
            fail(f"{path} uncovered_bom_row_indexes is not empty")
        if data.get("found_rows_missing_local_files"):
            fail(f"{path} found_rows_missing_local_files is not empty")
        if data.get("forbidden_statuses_present"):
            fail(f"{path} forbidden_statuses_present is not empty: {data.get('forbidden_statuses_present')}")

        require_true(path, "coverage_pass")
        require_true(path, "local_file_validation_pass")

        # Phase 6 policy:
        # Ambiguous/missing datasheets are allowed when they are honestly
        # reported and candidate URLs/search attempts are recorded. The hard
        # gate is coverage of all BOM rows, no forbidden statuses, and verified
        # local PDFs for rows marked found/local. Do not require validation
        # overall_pass here because older validation artifacts may set it false
        # for report-only unresolved datasheet rows.
        if data.get("forbidden_statuses_present"):
            fail(f"{path} forbidden_statuses_present is not empty: {data.get('forbidden_statuses_present')}")

        # Strict external datasheet audit. This catches fake found PDFs,
        # HTML saved as .pdf, and found rows whose PDF text does not contain
        # the selected MPN or approved equivalent/family match.
        result = subprocess.run(
            ["python3", "scripts/audit_phase6_datasheets.py"],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            fail("strict Phase 6 datasheet audit failed")

        manifest_path = Path(data["manifest_path"])
        if not manifest_path.is_file():
            fail(f"Phase 6 manifest_path does not exist: {manifest_path}")

        allowed = {"local", "found", "ambiguous", "missing", "error", "not_applicable_generic"}
        bom_count = data["bom_raw_row_count"]
        rows = []
        with manifest_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:
                    fail(f"invalid JSONL in {manifest_path} row {line_no}: {exc}")
                rows.append(row)

        if len(rows) != bom_count:
            fail(f"manifest row count {len(rows)} does not equal bom_raw_row_count {bom_count}")

        seen_indexes = set()
        for row in rows:
            idx = row.get("bom_row_index")
            if idx in seen_indexes:
                fail(f"duplicate bom_row_index in manifest: {idx}")
            seen_indexes.add(idx)

            status = row.get("status")
            if status not in allowed:
                fail(f"invalid Phase 6 status for row {idx}: {status!r}")

            if status in {"found", "local"}:
                local_path = row.get("local_saved_path")
                if not local_path:
                    fail(f"row {idx} status={status} missing local_saved_path")
                lp = Path(local_path)
                if not lp.is_file():
                    fail(f"row {idx} status={status} local_saved_path does not exist: {lp}")
                normalized_parts = tuple(lp.parts)
                path_text = str(lp)
                allowed_datasheet_path = (
                    path_text.startswith("datasheets/")
                    or "/exports/datasheets/" in path_text
                    or path_text.startswith("exports/datasheets/")
                )
                if not allowed_datasheet_path:
                    fail(f"row {idx} local_saved_path must be under datasheets/ or exports/datasheets/: {lp}")
                if row.get("local_file_exists") is not True:
                    fail(f"row {idx} status={status} local_file_exists is not true")

    elif phase in (7, 12):
        img = exports / f"{project}-image-evidence-inventory.json"
        data = load_json(img)
        if not isinstance(data, dict):
            fail(f"{img} must be a JSON object, not a list")
        require_true(img, "overall_pass")
        for field in [
            "pdf_sources",
            "conversion_tool",
            "total_pages_expected",
            "total_pages_rendered",
            "output_files",
            "schematic_pngs",
            "layout_pngs",
            "pages_inspected",
        ]:
            if field not in data:
                fail(f"{img} missing field {field}")

    elif phase == 9:
        require_file(exports / f"{project}-board-evidence-inventory.json")
        require_true(exports / f"{project}-board-evidence-inventory-validation.json", "overall_pass")

    elif phase == 15:
        require_true(exports / f"{project}-pre-findings-gate.json", "overall_gate_pass")

    elif phase == 17:
        require_file(exports / f"{project}-findings.json")

    elif phase == 18:
        findings = exports / f"{project}-findings.json"
        require_file(findings)
        result = subprocess.run(
            ["python3", "tools/validate_findings.py", str(findings)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            fail("tools/validate_findings.py failed")

    elif phase == 19:
        require_file(exports / f"{project}-review.html")
        require_true(exports / f"{project}-report-generation-validation.json", "overall_pass")

    elif phase == 20:
        for p in range(1, 21):
            audit_checkpoint(exports, project, p)
        require_true(exports / "tool-preflight-status.json", "overall_pass")
        # Phase 6 policy is audited by the strict external audit.
        # Do not require manifest validation overall_pass here because unresolved
        # ambiguous/missing rows may be report-only if coverage and local PDF
        # validation pass.
        result = subprocess.run(
            ["python3", "scripts/audit_phase6_datasheets.py"],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            fail("strict Phase 6 datasheet audit failed during Phase 20")
        require_true(exports / f"{project}-board-evidence-inventory-validation.json", "overall_pass")
        require_true(exports / f"{project}-image-evidence-inventory.json", "overall_pass")
        require_true(exports / f"{project}-pre-findings-gate.json", "overall_gate_pass")
        require_file(exports / f"{project}-review.html")
        require_true(exports / f"{project}-report-generation-validation.json", "overall_pass")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="example")
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--exports", default="exports")
    args = parser.parse_args()

    if args.phase not in PHASES:
        fail(f"unknown phase {args.phase}")

    audit_phase(Path(args.exports), args.project, args.phase)
    print(f"PASS: phase {args.phase} — {PHASES[args.phase]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
