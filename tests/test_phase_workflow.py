from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def checkpoint_row(phase: int, phase_name: str) -> dict:
    return {
        "phase_number": phase,
        "phase_name": phase_name,
        "started_at_utc": "2026-05-28T00:00:00Z",
        "completed_at_utc": "2026-05-28T00:00:00Z",
        "required_artifacts": [],
        "artifacts_verified": [],
        "validation_artifacts": [],
        "validation_passed": True,
        "blockers": [],
        "phase_passed": True,
        "failed_phase_number": None,
        "repair_required": False,
    }


def test_ensure_checkpoint_writes_one_jsonl_line(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ensure_phase_checkpoint.py"),
            "--project",
            "example",
            "--phase",
            "1",
            "--exports",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "phase_passed=True" in result.stdout

    checkpoint = tmp_path / "example-phase-checkpoints.jsonl"
    physical_lines = checkpoint.read_text(encoding="utf-8").splitlines()
    assert len(physical_lines) == 1
    row = json.loads(physical_lines[0])
    assert row["phase_number"] == 1
    assert row["phase_passed"] is True
    assert row["repair_required"] is False
    assert row["blockers"] == []


def test_replace_mode_recovers_from_pretty_printed_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "example-phase-checkpoints.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "phase_number": 1,
                "phase_name": "Ingest ThomsonLint Workflow",
                "phase_passed": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "ensure_phase_checkpoint.py"),
            "--project",
            "example",
            "--phase",
            "1",
            "--exports",
            str(tmp_path),
            "--mode",
            "replace",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    physical_lines = checkpoint.read_text(encoding="utf-8").splitlines()
    assert len(physical_lines) == 1
    assert json.loads(physical_lines[0])["phase_number"] == 1


def test_phase_maps_cover_1_through_22() -> None:
    modules = [
        load_module(ROOT / "scripts" / "write_phase_prompt.py"),
        load_module(ROOT / "scripts" / "ensure_phase_checkpoint.py"),
        load_module(ROOT / "scripts" / "audit_phase.py"),
    ]
    expected = set(range(1, 23))
    phase_maps = [module.PHASES for module in modules]
    for phase_map in phase_maps:
        assert set(phase_map) == expected
    assert phase_maps[0] == phase_maps[1] == phase_maps[2]


def test_phase11_validation_gate_allows_recorded_dfm_violations(tmp_path: Path) -> None:
    ensure = load_module(ROOT / "scripts" / "ensure_phase_checkpoint.py")
    validation = tmp_path / "example-dfm-evidence-inventory-validation.json"
    validation.write_text(
        json.dumps(
            {
                "phase": 11,
                "geometry_helpers_dfm_executed": True,
                "all_required_sections_present": True,
                "overall_pass": False,
                "validation_passed": True,
                "phase_gate_passed": True,
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    ok, blockers = ensure.artifact_passes(validation, 11)

    assert ok is True
    assert blockers == []


def test_phase11_audit_requires_required_dfm_checks(tmp_path: Path) -> None:
    audit = load_module(ROOT / "scripts" / "audit_phase.py")
    exports = tmp_path
    project = "example"
    inventory = exports / f"{project}-dfm-evidence-inventory.json"
    validation = exports / f"{project}-dfm-evidence-inventory-validation.json"
    inventory.write_text(
        json.dumps(
            {
                "phase": 11,
                "phase_name": "Review DFM and Manufacturing Specifications",
                "project": project,
                "geometry_helpers_dfm_results": {
                    "annular_ring": {},
                    "acid_traps": {},
                    "board_edge_clearance": {},
                    "copper_balance": {},
                    "voltage_spacing": {},
                },
                "summary": {
                    "geometry_helpers_dfm_executed": True,
                    "checks_run": [
                        "annular_ring",
                        "acid_traps",
                        "board_edge_clearance",
                        "copper_balance",
                        "voltage_spacing",
                    ],
                    "overall_pass": False,
                    "failing_checks": ["acid_traps"],
                    "total_violations": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    validation.write_text(
        json.dumps(
            {
                "phase": 11,
                "geometry_helpers_dfm_executed": True,
                "overall_pass": False,
                "validation_passed": True,
                "phase_gate_passed": True,
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    audit.audit_phase11_dfm_gate(exports, project)

    data = json.loads(inventory.read_text(encoding="utf-8"))
    del data["geometry_helpers_dfm_results"]["voltage_spacing"]
    inventory.write_text(json.dumps(data), encoding="utf-8")

    try:
        audit.audit_phase11_dfm_gate(exports, project)
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("missing DFM checks should fail Phase 11 audit")


def test_phase11_audit_accepts_validation_execution_gate_without_summary_flag(tmp_path: Path) -> None:
    audit = load_module(ROOT / "scripts" / "audit_phase.py")
    exports = tmp_path
    project = "sunrise"
    inventory = exports / f"{project}-dfm-evidence-inventory.json"
    validation = exports / f"{project}-dfm-evidence-inventory-validation.json"
    inventory.write_text(
        json.dumps(
            {
                "phase": 11,
                "phase_name": "Review DFM and Manufacturing Specifications",
                "project": project,
                "geometry_helpers_dfm_results": {
                    "annular_ring": {},
                    "acid_traps": {},
                    "board_edge_clearance": {},
                    "copper_balance": {},
                    "voltage_spacing": {},
                },
                "summary": {
                    "total_checks_run": 5,
                    "checks_with_violations": ["acid_traps"],
                    "checks_passed": ["annular_ring"],
                },
            }
        ),
        encoding="utf-8",
    )
    validation.write_text(
        json.dumps(
            {
                "phase": 11,
                "phase_gate_passed": True,
                "execution_pass": True,
                "artifact_validation_pass": True,
                "required_checks_executed": True,
                "checks_recorded": True,
                "dfm_compliance_pass": False,
                "violations_found": True,
            }
        ),
        encoding="utf-8",
    )

    audit.audit_phase11_dfm_gate(exports, project)


def test_phase16_audit_allows_recorded_cross_source_discrepancies(tmp_path: Path) -> None:
    audit = load_module(ROOT / "scripts" / "audit_phase.py")
    exports = tmp_path
    project = "sunrise"
    review = exports / f"{project}-cross-source-review.json"
    validation = exports / f"{project}-cross-source-review-validation.json"
    review.write_text(
        json.dumps(
            {
                "phase": 16,
                "phase_name": "Cross-Source Consistency Review",
                "project": project,
                "checks": {
                    "refdes_reconciliation": {"status": "fail"},
                    "package_mismatches": {"status": "pass"},
                    "netlist_integrity": {"status": "fail"},
                    "voltage_derating": {"status": "fail"},
                },
                "cross_source_observations": [{"category": "BOM vs schematic"}],
                "downstream_constraints": ["preserve discrepancy for findings phase"],
                "gate": {"overall_pass": False},
            }
        ),
        encoding="utf-8",
    )
    validation.write_text(
        json.dumps(
            {
                "phase": 16,
                "overall_pass": False,
                "validations": [
                    {"check": "artifact_json_parses", "passed": True},
                    {"check": "top_level_key_findings_absent", "passed": True},
                    {"check": "no_key_finding_anywhere", "passed": True},
                    {"check": "no_key_severity_anywhere", "passed": True},
                    {"check": "no_key_rule_id_anywhere", "passed": True},
                    {"check": "required_checks_executed", "passed": True},
                    {"check": "cross_source_observations_present", "passed": True},
                    {"check": "downstream_constraints_present", "passed": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    audit.audit_phase16_cross_source_gate(exports, project)


def test_phase17_accepts_phase16_execution_pass_with_cross_source_discrepancies(tmp_path: Path) -> None:
    audit = load_module(ROOT / "scripts" / "audit_phase.py")
    exports = tmp_path
    project = "sunrise"

    checkpoints = [
        checkpoint_row(phase, audit.PHASES[phase])
        for phase in range(8, 18)
    ]
    (exports / f"{project}-phase-checkpoints.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in checkpoints),
        encoding="utf-8",
    )
    (exports / f"{project}-cross-source-review.json").write_text(
        json.dumps(
            {
                "phase": 16,
                "phase_name": "Cross-Source Consistency Review",
                "project": project,
                "checks": {
                    "refdes_reconciliation": {"status": "FAIL"},
                    "package_mismatches": {"status": "PASS"},
                    "netlist_integrity": {"status": "FAIL"},
                    "voltage_derating": {"status": "FAIL"},
                },
                "cross_source_observations": [{"category": "BOM vs schematic"}],
                "gate": {"overall_pass": False},
            }
        ),
        encoding="utf-8",
    )
    (exports / f"{project}-cross-source-review-validation.json").write_text(
        json.dumps(
            {
                "phase": 16,
                "overall_pass": False,
                "phase_gate_passed": True,
                "execution_pass": True,
                "cross_source_consistency_pass": False,
                "artifact_validation_pass": True,
            }
        ),
        encoding="utf-8",
    )
    (exports / f"{project}-pre-findings-gate.json").write_text(
        json.dumps(
            {
                "phase": 17,
                "phase_name": "Pre-Findings Gate Check",
                "project": project,
                "blockers": [],
                "overall_gate_pass": True,
            }
        ),
        encoding="utf-8",
    )

    audit.audit_phase17_pre_findings_gate(exports, project)


def test_shell_scripts_do_not_contain_crlf() -> None:
    for path in sorted((ROOT / "scripts").glob("*.sh")):
        data = path.read_bytes()
        assert b"\r\n" not in data, f"{path} contains CRLF line endings"
        assert data.startswith(b"#!/usr/bin/env bash\n"), f"{path} has an invalid shebang"
