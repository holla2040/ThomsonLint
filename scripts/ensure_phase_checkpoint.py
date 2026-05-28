#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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

PHASE_ARTIFACTS = {
    # Phases 1, 2, 5: No external artifact — checkpoint row itself is the deliverable
    1: [],
    2: [],
    3: ["exports/tool-preflight-status.json"],
    4: [
        "exports/{project}-bom.json",
        "exports/{project}-thomson-export-sch.json",
        "exports/{project}-thomson-export-brd.json",
        "exports/{project}-thomson-export-stack.json",
    ],
    5: [],
    6: [
        "exports/datasheets/datasheet_manifest.jsonl",
        "exports/datasheets/datasheet_manifest_validation.json",
    ],
    7: ["exports/{project}-image-evidence-inventory.json"],
    8: [
        "exports/{project}-schematic-evidence-inventory.json",
        "exports/{project}-schematic-evidence-inventory-validation.json"
    ],
    9: [
        "exports/{project}-board-evidence-inventory.json",
        "exports/{project}-board-evidence-inventory-validation.json",
    ],
    10: [
        "exports/{project}-stackup-evidence-review.json",
        "exports/{project}-stackup-evidence-review-validation.json",
    ],
    11: [
        "exports/{project}-dfm-evidence-inventory.json",
        "exports/{project}-dfm-evidence-inventory-validation.json"
    ],
    12: [
        "exports/{project}-bom-evidence-inventory.json",
        "exports/{project}-bom-evidence-inventory-validation.json"
    ],
    13: [
        "exports/{project}-image-evidence-inventory.json",
        "exports/{project}-image-evidence-review.json",
        "exports/{project}-image-evidence-review-validation.json"
    ],
    14: [
        "exports/{project}-datasheet-evidence-review.json",
        "exports/{project}-datasheet-evidence-review-validation.json"
    ],
    15: [
        "exports/{project}-aerospace-evidence-inventory.json",
        "exports/{project}-aerospace-evidence-inventory-validation.json"
    ],
    16: [
        "exports/{project}-cross-source-review.json",
        "exports/{project}-cross-source-review-validation.json"
    ],
    17: ["exports/{project}-pre-findings-gate.json"],
    18: ["exports/{project}-candidate-findings.json"],
    19: ["exports/{project}-findings.json"],
    20: ["exports/{project}-findings.json"],
    21: [
        "exports/{project}-review.html",
        "exports/{project}-report-generation-validation.json",
    ],
    22: [
        "exports/{project}-review.html",
        "exports/{project}-report-generation-validation.json",
        "exports/{project}-phase-checkpoints.jsonl",
    ],
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

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def render(paths: list[str], project: str) -> list[str]:
    return [p.format(project=project) for p in paths]

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

def checkpoint_jsonl_line(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"

def write_checkpoint_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(checkpoint_jsonl_line(row) for row in rows), encoding="utf-8")

def load_rows(path: Path, *, recover: bool = False) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            if recover:
                print(f"WARNING: skipping invalid JSONL row {line_no} in {path}: {exc}", file=sys.stderr)
                continue
            raise SystemExit(f"invalid JSONL row {line_no} in {path}: {exc}")
        if not isinstance(row, dict):
            if recover:
                print(f"WARNING: skipping non-object JSONL row {line_no} in {path}", file=sys.stderr)
                continue
            raise SystemExit(f"invalid JSONL row {line_no} in {path}: expected object")
        rows.append(row)
    return rows

def phase11_artifacts_pass(inventory_path: Path, validation_path: Path) -> tuple[bool, list[str], list[str]]:
    blockers: list[str] = []
    verified: list[str] = []

    if not inventory_path.exists():
        blockers.append(f"missing artifact: {inventory_path}")
    if not validation_path.exists():
        blockers.append(f"missing artifact: {validation_path}")
    if blockers:
        return False, verified, blockers

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, verified, [f"invalid JSON artifact {inventory_path}: {exc}"]
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, verified, [f"invalid JSON artifact {validation_path}: {exc}"]

    if not isinstance(inventory, dict):
        blockers.append(f"{inventory_path} must be a JSON object")
    if not isinstance(validation, dict):
        blockers.append(f"{validation_path} must be a JSON object")
    if blockers:
        return False, verified, blockers

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
        blockers.append(
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
        blockers.append(
            f"{inventory_path} / {validation_path} do not record all required DFM checks: "
            f"{PHASE11_DFM_CHECKS}"
        )

    if validation.get("validation_passed") is False:
        blockers.append(f"{validation_path} validation_passed is false")
    if validation.get("artifact_validation_pass") is False:
        blockers.append(f"{validation_path} artifact_validation_pass is false")
    errors = validation.get("errors")
    if isinstance(errors, list) and errors:
        blockers.append(f"{validation_path} errors is not empty")

    if not blockers:
        verified = [str(inventory_path), str(validation_path)]
    return not blockers, verified, blockers

def phase16_artifacts_pass(review_path: Path, validation_path: Path) -> tuple[bool, list[str], list[str]]:
    blockers: list[str] = []
    verified: list[str] = []

    if not review_path.exists():
        blockers.append(f"missing artifact: {review_path}")
    if not validation_path.exists():
        blockers.append(f"missing artifact: {validation_path}")
    if blockers:
        return False, verified, blockers

    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, verified, [f"invalid JSON artifact {review_path}: {exc}"]
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, verified, [f"invalid JSON artifact {validation_path}: {exc}"]

    if not isinstance(review, dict):
        blockers.append(f"{review_path} must be a JSON object")
    if not isinstance(validation, dict):
        blockers.append(f"{validation_path} must be a JSON object")
    if blockers:
        return False, verified, blockers

    checks = review.get("checks")
    if not isinstance(checks, dict):
        blockers.append(f"{review_path} missing checks object")
    else:
        missing_checks = [check for check in PHASE16_CROSS_SOURCE_CHECKS if check not in checks]
        if missing_checks:
            blockers.append(f"{review_path} missing cross-source check results: {missing_checks}")

    if not isinstance(review.get("cross_source_observations"), list):
        blockers.append(f"{review_path} cross_source_observations must be an array")

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
        blockers.append(f"{validation_path} does not show artifact/schema validation pass")

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
        execution_passed = artifact_valid and isinstance(checks, dict) and not missing_checks and isinstance(
            review.get("cross_source_observations"), list
        )
    if not execution_passed:
        blockers.append(
            f"{validation_path} does not show Phase 16 execution pass "
            "(expected phase_gate_passed, execution_pass, review_executed, "
            "required_checks_executed, or equivalent validation rows)"
        )

    errors = validation.get("errors")
    if isinstance(errors, list) and errors:
        blockers.append(f"{validation_path} errors is not empty")

    if not blockers:
        verified = [str(review_path), str(validation_path)]
    return not blockers, verified, blockers

def checkpoint_phase_blockers(rows: list[dict[str, Any]], phase: int) -> list[str]:
    matches = [row for row in rows if row.get("phase_number") == phase]
    if len(matches) != 1:
        return [f"expected exactly one checkpoint row for phase {phase}, found {len(matches)}"]

    row = matches[0]
    blockers: list[str] = []
    if row.get("phase_name") != PHASES[phase]:
        blockers.append(
            f"phase {phase} checkpoint phase_name mismatch: "
            f"got {row.get('phase_name')!r}, expected {PHASES[phase]!r}"
        )
    if row.get("validation_passed") is not True:
        blockers.append(f"phase {phase} checkpoint validation_passed is not true")
    if row.get("phase_passed") is not True:
        blockers.append(f"phase {phase} checkpoint phase_passed is not true")
    if row.get("repair_required") is not False:
        blockers.append(f"phase {phase} checkpoint repair_required is not false")
    return blockers

def phase17_artifacts_pass(
    gate_path: Path,
    exports: Path,
    project: str,
    checkpoint_rows: list[dict[str, Any]],
) -> tuple[bool, list[str], list[str]]:
    blockers: list[str] = []
    verified: list[str] = []

    if not gate_path.exists():
        return False, verified, [f"missing artifact: {gate_path}"]

    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, verified, [f"invalid JSON artifact {gate_path}: {exc}"]
    if not isinstance(gate, dict):
        return False, verified, [f"{gate_path} must be a JSON object"]

    for upstream_phase in range(8, 17):
        blockers.extend(checkpoint_phase_blockers(checkpoint_rows, upstream_phase))

    phase16_ok, _, phase16_blockers = phase16_artifacts_pass(
        exports / f"{project}-cross-source-review.json",
        exports / f"{project}-cross-source-review-validation.json",
    )
    if not phase16_ok:
        blockers.extend(phase16_blockers)

    if "overall_gate_pass" not in gate:
        blockers.append(f"{gate_path} missing field overall_gate_pass")
    if not isinstance(gate.get("blockers", []), list):
        blockers.append(f"{gate_path} blockers must be an array")

    if not blockers:
        verified = [str(gate_path)]
    return not blockers, verified, blockers

def artifact_passes(path: Path, phase: int) -> tuple[bool, list[str]]:
    blockers: list[str] = []

    if not path.exists():
        return False, [f"missing artifact: {path}"]

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, [f"invalid JSON artifact {path}: {exc}"]

        # Phase 3: tool-preflight-status.json uses overall_pass at top level
        if phase == 3 and path.name == "tool-preflight-status.json":
            if data.get("overall_pass") is not True:
                blockers.append(f"{path} overall_pass is not true")
            return not blockers, blockers

        if phase == 11 and path.name.endswith("-dfm-evidence-inventory-validation.json"):
            if data.get("phase_gate_passed") is True or data.get("execution_pass") is True:
                if data.get("validation_passed") is False or data.get("artifact_validation_pass") is False:
                    blockers.append(f"{path} execution gate passed but artifact validation failed")
                if data.get("geometry_helpers_dfm_executed") is False:
                    blockers.append(f"{path} geometry_helpers_dfm_executed is false")
                errors = data.get("errors")
                if isinstance(errors, list) and errors:
                    blockers.append(f"{path} errors is not empty")
                return not blockers, blockers

            required_checks = data.get("required_checks_executed")
            checks_recorded = data.get("checks_recorded")
            if required_checks is not True:
                blockers.append(f"{path} required_checks_executed is not true")
            if checks_recorded is not True:
                blockers.append(f"{path} checks_recorded is not true")
            if data.get("artifact_validation_pass") is not True:
                blockers.append(f"{path} artifact_validation_pass is not true")
            return not blockers, blockers

        # Universal rule: any -validation.json must have overall_pass=true at the top level.
        # Exception: pre-findings-gate.json uses overall_gate_pass (different semantic).
        if path.name.endswith("-validation.json") and data.get("overall_pass") is not True:
            blockers.append(f"{path} overall_pass is not true (expected top-level bool true)")
        if path.name.endswith("-pre-findings-gate.json") and data.get("overall_gate_pass") is not True:
            blockers.append(f"{path} overall_gate_pass is not true")
        # Phase 7: image-evidence-inventory.json (no separate validation artifact) uses overall_pass
        if phase == 7 and path.name.endswith("-image-evidence-inventory.json") and data.get("overall_pass") is not True:
            blockers.append(f"{path} overall_pass is not true")

    return not blockers, blockers

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="example")
    ap.add_argument("--phase", type=int, required=True)
    ap.add_argument("--exports", default="exports")
    ap.add_argument("--mode", choices=["append-if-missing", "replace"], default="append-if-missing")
    args = ap.parse_args()

    if args.phase not in PHASES:
        raise SystemExit(f"unknown phase: {args.phase}")

    exports = Path(args.exports)
    checkpoint = exports / f"{args.project}-phase-checkpoints.jsonl"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    rows = load_rows(checkpoint, recover=args.mode == "replace")
    existing = [r for r in rows if r.get("phase_number") == args.phase]

    if existing and args.mode == "append-if-missing":
        print(f"checkpoint already exists for phase {args.phase}; leaving unchanged")
        return 0

    artifact_templates = PHASE_ARTIFACTS.get(args.phase, [])
    artifacts = render(artifact_templates, args.project)

    blockers: list[str] = []
    verified: list[str] = []
    if args.phase == 11:
        ok, verified, blockers = phase11_artifacts_pass(
            exports / f"{args.project}-dfm-evidence-inventory.json",
            exports / f"{args.project}-dfm-evidence-inventory-validation.json",
        )
    elif args.phase == 16:
        ok, verified, blockers = phase16_artifacts_pass(
            exports / f"{args.project}-cross-source-review.json",
            exports / f"{args.project}-cross-source-review-validation.json",
        )
    elif args.phase == 17:
        ok, verified, blockers = phase17_artifacts_pass(
            exports / f"{args.project}-pre-findings-gate.json",
            exports,
            args.project,
            rows,
        )
    else:
        for artifact in artifacts:
            ok, artifact_blockers = artifact_passes(Path(artifact), args.phase)
            if ok:
                verified.append(artifact)
            blockers.extend(artifact_blockers)

    now = utc_now()
    phase_passed = not blockers
    row = {
        "phase_number": args.phase,
        "phase_name": PHASES[args.phase],
        "started_at_utc": now,
        "completed_at_utc": now,
        "required_artifacts": artifacts,
        "artifacts_verified": verified,
        "validation_artifacts": artifacts,
        "validation_passed": phase_passed,
        "blockers": blockers,
        "phase_passed": phase_passed,
        "failed_phase_number": None if phase_passed else args.phase,
        "repair_required": not phase_passed,
    }

    if args.mode == "replace":
        rows = [r for r in rows if r.get("phase_number") != args.phase]

    rows.append(row)
    write_checkpoint_rows(checkpoint, rows)

    print(f"wrote checkpoint for phase {args.phase}: phase_passed={row['phase_passed']}")
    if blockers:
        for b in blockers:
            print(f"BLOCKER: {b}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
