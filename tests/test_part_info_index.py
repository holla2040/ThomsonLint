from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "part_info_index.py"
EXAMPLE = ROOT / "examples" / "part_info_examples" / "passive_capacitor.json"


def run_index(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def write_part(tmp_path: Path, data: dict, name: str = "part.json") -> Path:
    part_dir = tmp_path / "part_info"
    part_dir.mkdir(parents=True, exist_ok=True)
    path = part_dir / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def write_bom(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "bom.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_examples_only_indexing_works(tmp_path: Path) -> None:
    out = tmp_path / "part_info_index.json"
    missing_part_dir = tmp_path / "missing_part_info"

    result = run_index(
        "--project",
        "examples",
        "--part-info-dir",
        str(missing_part_dir),
        "--examples",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["summary"]["part_info_files"] == 5
    assert artifact["summary"]["indexed_mpns"] == 5
    assert artifact["summary"]["bom_rows"] == 0


def test_bom_single_refdes_maps_to_part_info(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    bom_path = write_bom(
        tmp_path,
        {"items": [{"refdes": ["C1"], "fields": {"manufacturer": "Murata", "mpn": part["mpn"]}}]},
    )
    out = tmp_path / "index.json"

    result = run_index("--bom", str(bom_path), "--part-info-dir", str(part_path.parent), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["matched_refdes"] == 1
    assert artifact["refdes"]["C1"]["normalized_mpn"] == part["normalized_mpn"]
    assert artifact["refdes"]["C1"]["part_info_file"].endswith("cap.json")


def test_bom_comma_separated_refdes_maps_all_refdes(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    bom_path = write_bom(
        tmp_path,
        {"rows": [{"refdes": "C1,C2,C3", "manufacturer_part_number": part["mpn"], "manufacturer": "Murata"}]},
    )
    out = tmp_path / "index.json"

    result = run_index("--bom", str(bom_path), "--part-info-dir", str(part_path.parent), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["matched_refdes"] == 3
    assert set(artifact["refdes"]) == {"C1", "C2", "C3"}


def test_missing_part_info_is_reported(tmp_path: Path) -> None:
    part_dir = tmp_path / "part_info"
    part_dir.mkdir()
    bom_path = write_bom(tmp_path, [{"refdes": "U1", "mpn": "MISSING-123", "manufacturer": "Acme"}])
    out = tmp_path / "index.json"

    result = run_index("--bom", str(bom_path), "--part-info-dir", str(part_dir), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["summary"]["missing_part_info"] == 1
    assert artifact["missing"][0]["bom"]["mpn"] == "MISSING-123"


def test_missing_part_info_from_nonempty_index_is_reported(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    bom_path = write_bom(
        tmp_path,
        [
            {"refdes": "C1", "mpn": part["mpn"], "manufacturer": "Murata"},
            {"refdes": "U1", "mpn": "MISSING-123", "manufacturer": "Acme"},
        ],
    )
    out = tmp_path / "index.json"

    result = run_index("--bom", str(bom_path), "--part-info-dir", str(part_path.parent), "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["missing_part_info"] == 1
    assert artifact["missing"][0]["bom"]["mpn"] == "MISSING-123"


def test_duplicate_ambiguous_normalized_mpn_is_reported(tmp_path: Path) -> None:
    part_a = load_example()
    part_b = load_example()
    part_b["mpn"] = "GRM155R71H104KE14D-ALT"
    part_b["manufacturer"] = "Other Manufacturer"
    part_b["normalized_mpn"] = part_a["normalized_mpn"]
    write_part(tmp_path, part_a, "a.json")
    write_part(tmp_path, part_b, "b.json")
    out = tmp_path / "index.json"

    result = run_index("--part-info-dir", str(tmp_path / "part_info"), "--examples", "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["ambiguous_part_info"] >= 1
    assert any(row["normalized_mpn"] == part_a["normalized_mpn"] for row in artifact["ambiguous"])


def test_validation_invalid_entry_propagates_to_index(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps({"files": [{"path": str(part_path), "status": "invalid", "human_review_needed": False, "errors": ["bad"]}]}),
        encoding="utf-8",
    )
    out = tmp_path / "index.json"

    result = run_index(
        "--part-info-dir",
        str(part_path.parent),
        "--validation",
        str(validation),
        "--examples",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["invalid_part_info"] == 1
    assert artifact["invalid"][0]["file"].endswith("cap.json")


def test_missing_validation_artifact_warns_but_does_not_fail_by_default(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    out = tmp_path / "index.json"

    result = run_index(
        "--part-info-dir",
        str(part_path.parent),
        "--validation",
        str(tmp_path / "missing-validation.json"),
        "--examples",
        "--out",
        str(out),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["overall_pass"] is True
    assert any("validation artifact missing" in warning for warning in artifact["warnings"])


def test_strict_mode_fails_on_missing_ambiguous_invalid_entries(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    bom_path = write_bom(
        tmp_path,
        [
            {"refdes": "C1", "mpn": part["mpn"], "manufacturer": "Murata"},
            {"refdes": "U1", "mpn": "MISSING-123", "manufacturer": "Acme"},
        ],
    )
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"files": [{"path": str(part_path), "status": "valid"}]}), encoding="utf-8")
    out = tmp_path / "index.json"

    result = run_index(
        "--bom",
        str(bom_path),
        "--part-info-dir",
        str(part_path.parent),
        "--validation",
        str(validation),
        "--examples",
        "--out",
        str(out),
        "--strict",
    )

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["overall_pass"] is False
    assert artifact["summary"]["missing_part_info"] == 1


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    part = load_example()
    part_path = write_part(tmp_path, part, "cap.json")
    out = tmp_path / "index.json"

    result = run_index("--part-info-dir", str(part_path.parent), "--examples", "--out", str(out))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "mpns",
        "refdes",
        "missing",
        "ambiguous",
        "invalid",
        "human_review_needed",
        "warnings",
        "errors",
        "execution_pass",
        "artifact_validation_pass",
        "overall_pass",
    }
    assert expected.issubset(artifact)
    assert artifact["summary"]["part_info_files"] >= 1
