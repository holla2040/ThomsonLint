from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "part_info_validate.py"
SCHEMA = ROOT / "schemas" / "part_info_schema.json"
EXAMPLE = ROOT / "examples" / "part_info_examples" / "buck_regulator.json"
PASSIVE_EXAMPLE = ROOT / "examples" / "part_info_examples" / "passive_capacitor.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_fixture(tmp_path: Path, data: dict, name: str = "fixture.json") -> Path:
    part_dir = tmp_path / "part_info"
    part_dir.mkdir(parents=True)
    path = part_dir / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_example(path: Path = EXAMPLE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifact(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_examples_validate_successfully(tmp_path: Path) -> None:
    out = tmp_path / "part-info-validation.json"
    missing_dir = tmp_path / "missing_exports_part_info"

    result = run_validator(
        "--project",
        "examples",
        "--part-info-dir",
        str(missing_dir),
        "--schema",
        str(SCHEMA),
        "--examples",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = load_artifact(out)
    assert artifact["execution_pass"] is True
    assert artifact["artifact_validation_pass"] is True
    assert artifact["overall_pass"] is True
    assert artifact["files_checked"] == 5
    assert artifact["invalid_files"] == 0


def test_dangling_evidence_ref_fails_deterministically(tmp_path: Path) -> None:
    data = load_example(PASSIVE_EXAMPLE)
    data["voltage_limits"][0]["evidence_ref"] = "missing:evidence"
    path = write_fixture(tmp_path, data)
    out = tmp_path / "validation.json"

    result = run_validator("--part-info-dir", str(path.parent), "--schema", str(SCHEMA), "--out", str(out))

    assert result.returncode == 1
    artifact = load_artifact(out)
    assert artifact["invalid_files"] == 1
    assert any("dangling evidence_ref" in err for err in artifact["errors"])
    assert artifact["files"][0]["status"] == "invalid"


def test_board_specific_topology_fields_are_rejected(tmp_path: Path) -> None:
    data = load_example(PASSIVE_EXAMPLE)
    data["load_behavior"]["refdes"] = "U1"
    path = write_fixture(tmp_path, data)
    out = tmp_path / "validation.json"

    result = run_validator("--part-info-dir", str(path.parent), "--schema", str(SCHEMA), "--out", str(out))

    assert result.returncode == 1
    artifact = load_artifact(out)
    assert artifact["invalid_files"] == 1
    assert any("forbidden board topology field" in err for err in artifact["errors"])


def test_low_confidence_marks_human_review_needed(tmp_path: Path) -> None:
    data = load_example(PASSIVE_EXAMPLE)
    data["confidence"]["overall"] = 0.5
    path = write_fixture(tmp_path, data)
    out = tmp_path / "validation.json"

    result = run_validator("--part-info-dir", str(path.parent), "--schema", str(SCHEMA), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = load_artifact(out)
    assert artifact["invalid_files"] == 0
    assert artifact["human_review_needed"] == 1
    assert artifact["low_confidence_files"] == 1
    assert artifact["files"][0]["status"] == "human_review_needed"


def test_missing_current_is_unresolved_and_zero_current_is_strict_failure(tmp_path: Path) -> None:
    data = load_example()
    path = write_fixture(tmp_path, data)
    out = tmp_path / "validation.json"

    result = run_validator("--part-info-dir", str(path.parent), "--schema", str(SCHEMA), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = load_artifact(out)
    assert artifact["missing_or_unresolved_current_models"] == 1
    assert artifact["files"][0]["human_review_needed"] is True
    assert not any("zero current" in warning for warning in artifact["warnings"])

    data["power_behavior"]["quiescent_current_a"] = {
        "value": 0,
        "unit": "A",
        "condition": "current value copied from table",
        "evidence_ref": "ds:p6:iq",
        "confidence": 0.8,
    }
    strict_path = write_fixture(tmp_path / "strict", data)
    strict_out = tmp_path / "strict-validation.json"

    strict_result = run_validator(
        "--part-info-dir",
        str(strict_path.parent),
        "--schema",
        str(SCHEMA),
        "--out",
        str(strict_out),
        "--strict",
    )

    assert strict_result.returncode == 1
    strict_artifact = load_artifact(strict_out)
    assert any("zero current" in warning for warning in strict_artifact["warnings"])
    assert strict_artifact["files"][0]["status"] == "invalid"


def test_validator_writes_expected_output_artifact_shape(tmp_path: Path) -> None:
    data = load_example(PASSIVE_EXAMPLE)
    path = write_fixture(tmp_path, data)
    out = tmp_path / "validation.json"

    result = run_validator(
        "--project",
        "shape",
        "--part-info-dir",
        str(path.parent),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = load_artifact(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "part_info_dir",
        "schema_path",
        "files_checked",
        "valid_files",
        "invalid_files",
        "human_review_needed",
        "missing_or_unresolved_current_models",
        "low_confidence_files",
        "files",
        "errors",
        "warnings",
        "execution_pass",
        "artifact_validation_pass",
        "overall_pass",
    }
    assert expected.issubset(artifact)
    assert artifact["project"] == "shape"
    assert artifact["files_checked"] == 1
    assert artifact["files"][0]["path"].endswith("fixture.json")
