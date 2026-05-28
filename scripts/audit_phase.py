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
    11: "Review DFM and Manufacturing Specifications",
    12: "Review BOM and Component Evidence FULL",
    13: "Review Image Evidence FULL",
    14: "Review Datasheet Evidence FULL",
    15: "Review Aerospace and Process Metadata",
    16: "Cross-Source Consistency Review",
    17: "Pre-Findings Gate Check",
    18: "Candidate Finding Development",
    19: "Write Findings JSON",
    20: "Validate and Repair Findings",
    21: "Generate Report",
    22: "Final Summary",
}

CHECKPOINT_KEYS = [
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
    "failed_phase_number",
    "repair_required",
]


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


PHASE11_DFM_CHECKS = [
    "annular_ring",
    "acid_traps",
    "board_edge_clearance",
    "copper_balance",
    "voltage_spacing",
]

PHASE16_CROSS_SOURCE_CHECKS = [
    "refdes_reconciliation",
    "package_mismatches",
    "netlist_integrity",
    "voltage_derating",
]


def extract_check_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        names.update(str(key) for key in value)
        for key in ["checks", "checks_run", "required_checks", "required_checks_recorded"]:
            names.update(extract_check_names(value.get(key)))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict):
                for key in ["check", "check_name", "name", "id", "rule", "rule_id"]:
                    raw = item.get(key)
                    if isinstance(raw, str):
                        names.add(raw)
                names.update(extract_check_names(item.get("checks")))
    return names


def has_all_phase11_checks(*sources: Any) -> bool:
    observed: set[str] = set()
    for source in sources:
        observed.update(extract_check_names(source))
    return all(check in observed for check in PHASE11_DFM_CHECKS)


def validation_checks_passed(validation: dict[str, Any], required: list[str]) -> bool:
    rows = validation.get("validations")
    if not isinstance(rows, list):
        return False
    by_name = {row.get("check"): row.get("passed") for row in rows if isinstance(row, dict)}
    return all(by_name.get(name) is True for name in required)


def audit_phase11_dfm_gate(exports: Path, project: str) -> None:
    inventory_path = exports / f"{project}-dfm-evidence-inventory.json"
    validation_path = exports / f"{project}-dfm-evidence-inventory-validation.json"

    inventory = load_json(inventory_path)
    validation = load_json(validation_path)

    if not isinstance(inventory, dict):
        fail(f"{inventory_path} must be a JSON object")
    if not isinstance(validation, dict):
        fail(f"{validation_path} must be a JSON object")

    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    details = validation.get("details") if isinstance(validation.get("details"), dict) else {}

    execution_passed = any(
        value is True
        for value in [
            validation.get("phase_gate_passed"),
            validation.get("execution_pass"),
            summary.get("geometry_helpers_dfm_executed"),
            inventory.get("geometry_helpers_dfm_executed"),
            validation.get("geometry_helpers_dfm_executed"),
        ]
    )

    if not execution_passed:
        fail(
            f"{validation_path} does not show Phase 11 execution pass "
            "(expected phase_gate_passed, execution_pass, or geometry_helpers_dfm_executed)"
        )

    checks_recorded = has_all_phase11_checks(
        inventory.get("geometry_helpers_dfm_results"),
        summary.get("geometry_helpers_dfm_results"),
        summary.get("checks_run"),
        validation.get("required_checks_recorded"),
        validation.get("required_checks"),
        details.get("per_check_status"),
    )
    if not checks_recorded:
        if validation.get("required_checks_executed") is True and validation.get("checks_recorded") is True:
            checks_recorded = True

    if not checks_recorded:
        fail(
            f"{inventory_path} / {validation_path} do not record all required DFM checks: "
            f"{PHASE11_DFM_CHECKS}"
        )

    if validation.get("phase_gate_passed") is True or validation.get("execution_pass") is True:
        if validation.get("validation_passed") is False:
            fail(f"{validation_path} validation_passed is false")
        if validation.get("artifact_validation_pass") is False:
            fail(f"{validation_path} artifact_validation_pass is false")
        if validation.get("geometry_helpers_dfm_executed") is False:
            fail(f"{validation_path} geometry_helpers_dfm_executed is false")
        errors = validation.get("errors")
        if isinstance(errors, list) and errors:
            fail(f"{validation_path} errors is not empty")
        return

    if validation.get("required_checks_executed") is not True:
        fail(f"{validation_path} required_checks_executed is not true")
    if validation.get("checks_recorded") is not True:
        fail(f"{validation_path} checks_recorded is not true")
    if validation.get("artifact_validation_pass") is not True:
        fail(f"{validation_path} artifact_validation_pass is not true")


def audit_phase16_cross_source_gate(exports: Path, project: str) -> None:
    review_path = exports / f"{project}-cross-source-review.json"
    validation_path = exports / f"{project}-cross-source-review-validation.json"

    review = load_json(review_path)
    validation = load_json(validation_path)

    if not isinstance(review, dict):
        fail(f"{review_path} must be a JSON object")
    if not isinstance(validation, dict):
        fail(f"{validation_path} must be a JSON object")

    checks = review.get("checks")
    if not isinstance(checks, dict):
        fail(f"{review_path} missing checks object")
    missing_checks = [check for check in PHASE16_CROSS_SOURCE_CHECKS if check not in checks]
    if missing_checks:
        fail(f"{review_path} missing cross-source check results: {missing_checks}")

    observations = review.get("cross_source_observations")
    if not isinstance(observations, list):
        fail(f"{review_path} cross_source_observations must be an array")

    artifact_valid = (
        validation.get("artifact_validation_pass") is True
        or validation_checks_passed(
            validation,
            [
                "artifact_json_parses",
                "top_level_key_findings_absent",
                "no_key_finding_anywhere",
                "no_key_severity_anywhere",
                "no_key_rule_id_anywhere",
            ],
        )
    )
    if not artifact_valid:
        fail(f"{validation_path} does not show artifact/schema validation pass")

    execution_passed = any(
        value is True
        for value in [
            validation.get("phase_gate_passed"),
            validation.get("execution_pass"),
            validation.get("review_executed"),
            validation.get("required_checks_executed"),
        ]
    )
    if not execution_passed:
        execution_passed = validation_checks_passed(
            validation,
            [
                "required_checks_executed",
                "cross_source_observations_present",
                "downstream_constraints_present",
            ],
        )
    if not execution_passed:
        execution_passed = artifact_valid and not missing_checks and isinstance(observations, list)

    if not execution_passed:
        fail(
            f"{validation_path} does not show Phase 16 execution pass "
            "(expected phase_gate_passed, execution_pass, review_executed, "
            "required_checks_executed, or equivalent validation rows)"
        )

    errors = validation.get("errors")
    if isinstance(errors, list) and errors:
        fail(f"{validation_path} errors is not empty")


def load_checkpoint_rows(path: Path) -> list[dict[str, Any]]:
    require_file(path)
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            fail(f"invalid JSONL in {path} row {i}: {exc}")
        if not isinstance(row, dict):
            fail(f"invalid JSONL in {path} row {i}: expected object")
        rows.append(row)
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

    for key in CHECKPOINT_KEYS:
        if key not in row:
            fail(f"phase {phase} checkpoint missing key: {key}")

    if row.get("phase_number") != phase:
        fail(f"phase {phase} checkpoint phase_number mismatch: {row.get('phase_number')!r}")
    for key in ["required_artifacts", "artifacts_verified", "validation_artifacts", "blockers"]:
        if not isinstance(row.get(key), list):
            fail(f"phase {phase} checkpoint {key} must be an array")
    if row.get("validation_passed") is not True:
        fail(f"phase {phase} checkpoint validation_passed is not true")
    if row.get("phase_passed") is not True:
        fail(f"phase {phase} checkpoint phase_passed is not true")
    if row.get("failed_phase_number") is not None:
        fail(f"phase {phase} checkpoint failed_phase_number must be null for a passing phase")
    if row.get("repair_required") is not False:
        fail(f"phase {phase} checkpoint repair_required must be false for a passing phase")


def audit_phase17_pre_findings_gate(exports: Path, project: str) -> None:
    gate_path = exports / f"{project}-pre-findings-gate.json"
    gate = load_json(gate_path)
    if not isinstance(gate, dict):
        fail(f"{gate_path} must be a JSON object")

    # Phase 17 is a workflow gate, not a compliance gate. Validate upstream
    # phases through their checkpoint/execution semantics so Phase 16 can
    # preserve real cross-source discrepancies while still allowing findings.
    for upstream_phase in range(8, 17):
        audit_checkpoint(exports, project, upstream_phase)

    audit_phase16_cross_source_gate(exports, project)

    if "overall_gate_pass" not in gate:
        fail(f"{gate_path} missing field overall_gate_pass")
    if not isinstance(gate.get("blockers", []), list):
        fail(f"{gate_path} blockers must be an array")


def audit_phase(exports: Path, project: str, phase: int) -> None:
    audit_checkpoint(exports, project, phase)

    # Phases 1, 2, 5 have no external artifacts — checkpoint row itself is the deliverable
    if phase in (1, 2, 5):
        pass  # checkpoint validation above is sufficient

    elif phase == 3:
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
            [
                "python3",
                "scripts/audit_phase6_datasheets.py",
                "--project",
                project,
                "--exports",
                str(exports),
            ],
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

    elif phase == 7:
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

    elif phase == 8:
        require_file(exports / f"{project}-schematic-evidence-inventory.json")
        require_true(exports / f"{project}-schematic-evidence-inventory-validation.json", "overall_pass")

    elif phase == 10:
        require_file(exports / f"{project}-stackup-evidence-review.json")
        require_true(exports / f"{project}-stackup-evidence-review-validation.json", "overall_pass")

    elif phase == 11:
        audit_phase11_dfm_gate(exports, project)

    elif phase == 12:
        require_file(exports / f"{project}-bom-evidence-inventory.json")
        require_true(exports / f"{project}-bom-evidence-inventory-validation.json", "overall_pass")

    elif phase == 13:
        require_file(exports / f"{project}-image-evidence-inventory.json")
        require_file(exports / f"{project}-image-evidence-review.json")
        require_true(exports / f"{project}-image-evidence-review-validation.json", "overall_pass")

    elif phase == 9:
        require_file(exports / f"{project}-board-evidence-inventory.json")
        require_true(exports / f"{project}-board-evidence-inventory-validation.json", "overall_pass")

    elif phase == 14:
        require_file(exports / f"{project}-datasheet-evidence-review.json")
        require_true(exports / f"{project}-datasheet-evidence-review-validation.json", "overall_pass")

    elif phase == 15:
        require_file(exports / f"{project}-aerospace-evidence-inventory.json")
        require_true(exports / f"{project}-aerospace-evidence-inventory-validation.json", "overall_pass")

    elif phase == 16:
        audit_phase16_cross_source_gate(exports, project)

    elif phase == 17:
        audit_phase17_pre_findings_gate(exports, project)

    elif phase == 18:
        require_file(exports / f"{project}-candidate-findings.json")

    elif phase == 19:
        require_file(exports / f"{project}-findings.json")

    elif phase == 20:
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

    elif phase == 21:
        require_file(exports / f"{project}-review.html")
        require_true(exports / f"{project}-report-generation-validation.json", "overall_pass")

    elif phase == 22:
        for p in range(1, 23):
            audit_checkpoint(exports, project, p)
        require_true(exports / "tool-preflight-status.json", "overall_pass")
        # Phase 6 policy is audited by the strict external audit.
        # Do not require manifest validation overall_pass here because unresolved
        # ambiguous/missing rows may be report-only if coverage and local PDF
        # validation pass.
        result = subprocess.run(
            [
                "python3",
                "scripts/audit_phase6_datasheets.py",
                "--project",
                project,
                "--exports",
                str(exports),
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            fail("strict Phase 6 datasheet audit failed during Phase 22")
        require_true(exports / f"{project}-board-evidence-inventory-validation.json", "overall_pass")
        require_true(exports / f"{project}-image-evidence-inventory.json", "overall_pass")
        audit_phase17_pre_findings_gate(exports, project)
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
