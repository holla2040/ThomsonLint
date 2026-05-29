from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_geometry_validate.py"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(branch_id: str, evidence_type: str, value: object, source: str = "branch_topology") -> dict:
    return {
        "evidence_id": f"ev_{branch_id}_{evidence_type}",
        "branch_id": branch_id,
        "net_name": "VCC",
        "evidence_type": evidence_type,
        "value": value,
        "unit": "INCH",
        "source": source,
        "notes": f"{evidence_type} evidence.",
    }


def unresolved(branch_id: str, item_type: str) -> dict:
    return {
        "id": f"unres_{branch_id}_{item_type}",
        "type": item_type,
        "branch_id": branch_id,
        "net_name": "VCC",
        "human_review_needed": True,
        "notes": f"{item_type} needs review.",
    }


def review_record(
    branch_id: str = "br_vcc_top_trace_group_000001",
    *,
    net_type: str = "power",
    branch_type: str = "trace_group",
    layer: str | None = "TOP",
    current_known: bool = True,
    estimated_current_a: float | None = 0.2,
    current_model_ref: str | None = "cm_vcc",
    current_basis: str = "datasheet",
    status: str = "ready_for_later_calculation",
    geometry: dict | None = None,
    stackup: dict | None = None,
    unresolved_flags: list[str] | None = None,
) -> dict:
    geom = {
        "units": "INCH",
        "known_width_count": 1,
        "min_width": 0.01,
        "max_width": 0.02,
        "total_length": 1.5,
        "total_area": None,
        "bbox": None,
        "has_trace_like_geometry": True,
        "has_plane_like_geometry": False,
        "has_vias": False,
    }
    if geometry is not None:
        geom.update(geometry)

    return {
        "review_id": f"geo_{branch_id}",
        "branch_id": branch_id,
        "net_name": "VCC",
        "topology_net_type": net_type,
        "branch_type": branch_type,
        "layer": layer,
        "layers": [layer] if layer else [],
        "object_count": 1,
        "geometry": geom,
        "stackup": stackup
        if stackup is not None
        else {
            "primary_layer": layer,
            "is_copper_layer": True,
            "copper_thickness": 0.0014,
            "layer_function": "CONDUCTOR",
            "side": "TOP",
        },
        "current_context": {
            "current_model_ref": current_model_ref,
            "estimated_current_a": estimated_current_a,
            "current_basis": current_basis,
            "current_known": current_known,
        },
        "review_status": status,
        "evidence": [],
        "unresolved_flags": unresolved_flags or [],
        "warnings": [],
    }


def rebuild_summary(review: dict, *, legacy: bool = False) -> dict:
    records = review["review_records"]
    unresolved_items = review["unresolved"]
    summary = {
        "review_record_count": len(records),
        "evidence_record_count": len(review["evidence_records"]),
        "unresolved_count": len(unresolved_items),
        "error_count": len(review["errors"]),
        "warning_count": len(review["warnings"]),
        "power_review_count": sum(1 for row in records if row["topology_net_type"] == "power"),
        "current_unknown_power_count": sum(
            1
            for row in records
            if row["topology_net_type"] == "power" and row["current_context"]["current_known"] is False
        ),
        "geometry_incomplete_count": sum(
            1
            for row in records
            if row["review_status"] == "geometry_incomplete"
            or any(item["branch_id"] == row["branch_id"] and item["type"] in {"missing_width", "missing_length", "missing_area", "missing_geometry"} for item in unresolved_items)
        ),
        "missing_stackup_count": sum(1 for item in unresolved_items if item["type"] == "missing_layer"),
        "non_copper_layer_count": sum(1 for item in unresolved_items if item["type"] == "non_copper_layer"),
    }
    if legacy:
        summary["power_branch_review_count"] = summary.pop("power_review_count")
        summary["geometry_incomplete_branch_count"] = sum(1 for row in records if row["review_status"] == "geometry_incomplete")
        summary.pop("unresolved_count")
        summary.pop("current_unknown_power_count")
        summary.pop("missing_stackup_count")
        summary.pop("non_copper_layer_count")
    return summary


def minimal_review(records: list[dict] | None = None, unresolved_items: list[dict] | None = None, *, legacy: bool = False) -> dict:
    recs = records or [review_record()]
    evidence_records: list[dict] = []
    for record in recs:
        branch_id = record["branch_id"]
        if record["branch_type"] == "trace_group":
            evidence_records.extend([evidence(branch_id, "width", {"min_width": 0.01}), evidence(branch_id, "length", 1.5)])
        elif record["branch_type"] in {"plane_region", "pad_group"}:
            evidence_records.append(evidence(branch_id, "bbox", {"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1}))
        elif record["branch_type"] == "via_cluster":
            evidence_records.append(evidence(branch_id, "width", {"min_width": 0.012}))
        evidence_records.append(evidence(branch_id, "stackup", {"is_copper": True}, source="stackup"))
        record["evidence"] = [item["evidence_id"] for item in evidence_records if item["branch_id"] == branch_id]

    review = {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "sources": {"branch_topology": "branches.json"},
        "summary": {},
        "review_records": recs,
        "evidence_records": evidence_records,
        "unresolved": unresolved_items or [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "geometry_review_pass": True,
    }
    review["summary"] = rebuild_summary(review, legacy=legacy)
    return review


def via_drill_span_record(layer_name: str) -> dict:
    start, end = [int(part) for part in layer_name.replace("DRILL_", "").replace("VIA_", "").replace("_", "-").split("-")]
    span_type = "VIA" if layer_name.upper().startswith("VIA") else "DRILL"
    return review_record(
        f"br_vcc_{layer_name.lower().replace('-', '_')}_via_cluster_000001",
        branch_type="via_cluster",
        layer=layer_name,
        geometry={"has_trace_like_geometry": False, "has_vias": True},
        stackup={
            "primary_layer": layer_name,
            "is_copper_layer": False,
            "is_drill_layer": True,
            "copper_thickness": None,
            "layer_function": "DRILL",
            "side": "ALL",
            "via_span": {
                "drill_or_via_type": span_type,
                "start_layer_index": start,
                "end_layer_index": end,
                "span_label": f"{start}-{end}",
                "layer_span_count": abs(end - start) + 1,
            },
        },
    )


def add_via_drill_span_evidence(review: dict, record: dict) -> dict:
    branch_id = record["branch_id"]
    item = evidence(
        branch_id,
        "via_drill_span",
        {
            "layer_name": record["layer"],
            "is_copper": False,
            "is_drill_layer": True,
            "via_span": record["stackup"]["via_span"],
        },
        source="stackup",
    )
    review["evidence_records"].append(item)
    record["evidence"].append(item["evidence_id"])
    review["summary"] = rebuild_summary(review)
    return review


def invoke(tmp_path: Path, review: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    review_path = write_json(tmp_path / "geometry-review.json", review)
    out = tmp_path / "geometry-validation.json"
    result = run_validator("--project", "unit", "--review", str(review_path), "--out", str(out), *extra)
    return result, out


def test_valid_minimal_review_artifact_passes_non_strict(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_review())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["artifact_validation_pass"] is True
    assert artifact["geometry_consistency_pass"] is True
    assert artifact["phase_gate_passed"] is True
    assert artifact["overall_pass"] is True


def test_unresolved_power_current_passes_non_strict_but_reports_human_review(tmp_path: Path) -> None:
    rec = review_record(current_known=False, estimated_current_a=None, current_basis="unresolved", status="needs_current_model", unresolved_flags=["current_unknown"])
    result, out = invoke(tmp_path, minimal_review([rec], [unresolved(rec["branch_id"], "current_unknown")]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["unresolved_items_present"] is True
    assert artifact["phase_gate_passed"] is True
    assert any(item["type"] == "current_unknown" for item in artifact["human_review_needed"])


def test_strict_mode_fails_unresolved_power_current(tmp_path: Path) -> None:
    rec = review_record(current_known=False, estimated_current_a=None, current_basis="unresolved", status="needs_current_model", unresolved_flags=["current_unknown"])
    result, out = invoke(tmp_path, minimal_review([rec], [unresolved(rec["branch_id"], "current_unknown")]), "--strict")

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["phase_gate_passed"] is False
    assert any("power branch current unknown" in error for error in artifact["errors"])


def test_duplicate_review_id_is_consistency_error(tmp_path: Path) -> None:
    first = review_record("br_a")
    second = review_record("br_b")
    second["review_id"] = first["review_id"]
    result, out = invoke(tmp_path, minimal_review([first, second]))

    assert result.returncode == 1
    assert any("duplicate review_id" in error for error in read_json(out)["errors"])


def test_duplicate_evidence_id_is_consistency_error(tmp_path: Path) -> None:
    review = minimal_review()
    review["evidence_records"].append(dict(review["evidence_records"][0]))
    review["summary"] = rebuild_summary(review)
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("duplicate evidence_id" in error for error in read_json(out)["errors"])


def test_evidence_branch_id_dangling_is_consistency_error(tmp_path: Path) -> None:
    review = minimal_review()
    review["evidence_records"][0]["branch_id"] = "missing_branch"
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("branch_id dangling" in error for error in read_json(out)["errors"])


def test_summary_count_mismatch_is_consistency_error(tmp_path: Path) -> None:
    review = minimal_review()
    review["summary"]["review_record_count"] = 99
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("summary.review_record_count" in error for error in read_json(out)["errors"])


def test_forbidden_evidence_types_are_errors(tmp_path: Path) -> None:
    for forbidden in ("ampacity", "current_density", "thermal_rise"):
        review = minimal_review()
        review["evidence_records"][0]["evidence_type"] = forbidden
        result, out = invoke(tmp_path / forbidden, review)

        assert result.returncode == 1
        assert any(f"forbidden evidence claim: {forbidden}" in error for error in read_json(out)["errors"])


@pytest.mark.parametrize("layer_name", ["DRILL_1-8", "DRILL_1-16"])
def test_via_cluster_on_drill_span_with_span_evidence_passes_without_layer_unresolved(tmp_path: Path, layer_name: str) -> None:
    rec = via_drill_span_record(layer_name)
    review = add_via_drill_span_evidence(minimal_review([rec]), rec)
    result, out = invoke(tmp_path, review)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["geometry_consistency_pass"] is True
    assert artifact["human_review_needed"] == []
    assert not any("missing_layer" in error for error in artifact["errors"])
    assert not any("non-copper" in error for error in artifact["errors"])


@pytest.mark.parametrize("layer_name", ["DRILL_1-8", "DRILL_1-16"])
def test_via_cluster_on_drill_span_does_not_require_missing_or_non_copper_unresolved(tmp_path: Path, layer_name: str) -> None:
    rec = via_drill_span_record(layer_name)
    review = minimal_review([rec])
    result, out = invoke(tmp_path, review)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["geometry_consistency_pass"] is True
    assert not any(item["type"] in {"missing_layer", "non_copper_layer"} for item in artifact["human_review_needed"])


def test_trace_missing_width_requires_unresolved_missing_width(tmp_path: Path) -> None:
    rec = review_record(geometry={"known_width_count": 0, "min_width": None, "max_width": None})
    review = minimal_review([rec])
    review["evidence_records"] = [item for item in review["evidence_records"] if item["evidence_type"] != "width"]
    review["review_records"][0]["evidence"] = [item["evidence_id"] for item in review["evidence_records"]]
    review["summary"] = rebuild_summary(review)
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("missing width without missing_width" in error for error in read_json(out)["errors"])


def test_trace_missing_length_requires_unresolved_missing_length(tmp_path: Path) -> None:
    rec = review_record(geometry={"total_length": None})
    review = minimal_review([rec])
    review["evidence_records"] = [item for item in review["evidence_records"] if item["evidence_type"] != "length"]
    review["review_records"][0]["evidence"] = [item["evidence_id"] for item in review["evidence_records"]]
    review["summary"] = rebuild_summary(review)
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("missing length without missing_length" in error for error in read_json(out)["errors"])


def test_plane_missing_area_bbox_requires_unresolved_missing_area(tmp_path: Path) -> None:
    rec = review_record(
        branch_type="plane_region",
        status="geometry_incomplete",
        geometry={"known_width_count": 0, "min_width": None, "max_width": None, "total_length": None, "total_area": None, "bbox": None},
    )
    review = minimal_review([rec])
    review["evidence_records"] = [item for item in review["evidence_records"] if item["evidence_type"] not in {"area", "bbox"}]
    review["review_records"][0]["evidence"] = [item["evidence_id"] for item in review["evidence_records"]]
    review["summary"] = rebuild_summary(review)
    result, out = invoke(tmp_path, review)

    assert result.returncode == 1
    assert any("plane_region missing area/bbox" in error for error in read_json(out)["errors"])


def test_missing_stackup_layer_requires_unresolved_missing_layer(tmp_path: Path) -> None:
    rec = review_record(layer=None, stackup={"primary_layer": None, "is_copper_layer": False})
    result, out = invoke(tmp_path, minimal_review([rec]))

    assert result.returncode == 1
    assert any("missing_layer unresolved" in error for error in read_json(out)["errors"])


def test_non_copper_layer_requires_unresolved_non_copper_layer(tmp_path: Path) -> None:
    rec = review_record(stackup={"primary_layer": "TOP", "is_copper_layer": False})
    result, out = invoke(tmp_path, minimal_review([rec]))

    assert result.returncode == 1
    assert any("non_copper_layer unresolved" in error for error in read_json(out)["errors"])


def test_trace_group_on_non_copper_layer_still_fails_strict_mode(tmp_path: Path) -> None:
    rec = review_record(stackup={"primary_layer": "FABRICATION", "is_copper_layer": False}, unresolved_flags=["non_copper_layer"])
    result, out = invoke(tmp_path, minimal_review([rec], [unresolved(rec["branch_id"], "non_copper_layer")]), "--strict")

    assert result.returncode == 1
    assert any("power branch on non-copper layer" in error for error in read_json(out)["errors"])


def test_current_known_must_be_false_when_estimated_current_is_null(tmp_path: Path) -> None:
    rec = review_record(estimated_current_a=None, current_known=True)
    result, out = invoke(tmp_path, minimal_review([rec]))

    assert result.returncode == 1
    assert any("current_known must be false" in error for error in read_json(out)["errors"])


def test_output_validation_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_review())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "checks",
        "errors",
        "warnings",
        "human_review_needed",
        "execution_pass",
        "artifact_validation_pass",
        "geometry_consistency_pass",
        "unresolved_items_present",
        "phase_gate_passed",
        "overall_pass",
    }
    assert expected.issubset(artifact)
    assert artifact["summary"]["review_record_count"] == 1
    assert artifact["checks"][0]["check"] == "artifact_shape"


def test_exit_codes_match_zero_one_two_behavior(tmp_path: Path) -> None:
    good_result, _ = invoke(tmp_path / "good", minimal_review())
    assert good_result.returncode == 0, good_result.stderr + good_result.stdout

    bad = minimal_review()
    bad["summary"]["review_record_count"] = 99
    bad_result, bad_out = invoke(tmp_path / "bad", bad)
    assert bad_result.returncode == 1
    assert bad_out.exists()

    missing_out = tmp_path / "missing" / "out.json"
    missing_result = run_validator("--project", "unit", "--review", str(tmp_path / "missing.json"), "--out", str(missing_out))
    assert missing_result.returncode == 2
    assert not missing_out.exists()


def test_manual_converter_shaped_pr10_review_fixture_works(tmp_path: Path) -> None:
    rec = review_record()
    review = minimal_review([rec], legacy=True)
    review["human_review_needed"] = False
    result, out = invoke(tmp_path, review)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["artifact_validation_pass"] is True
    assert artifact["summary"]["power_review_count"] == 1
