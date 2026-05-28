from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_geometry_review.py"


def run_review(*args: str) -> subprocess.CompletedProcess[str]:
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


def topology_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "nets": [
            {"net_name": "V3P3", "net_type": "power"},
            {"net_name": "GND", "net_type": "ground"},
            {"net_name": "SIG_A", "net_type": "signal"},
        ],
        "power_rails": [{"net_name": "V3P3"}],
        "current_models": [{"model_id": "cm_v3p3", "target": "rail:V3P3", "basis": "unresolved"}],
        "validation": {"execution_pass": True},
    }


def copper_association_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "copper_objects": [],
        "layers": [],
        "net_associations": [],
        "execution_pass": True,
        "association_pass": True,
    }


def stackup_fixture(*, non_copper_top: bool = False) -> dict:
    top = {
        "name": "TOP",
        "sequence": 1,
        "type": "Conductor" if not non_copper_top else "Mask",
        "material": "COPPER" if not non_copper_top else "EPOXY",
        "function": "CONDUCTOR" if not non_copper_top else "SILKSCREEN",
        "side": "TOP",
        "copper_thickness": 0.0014,
    }
    return {
        "project_name": "unit",
        "parser_version": "ipc2581-v1",
        "units": "INCH",
        "physical_stackup": [
            top,
            {"name": "L2", "sequence": 2, "type": "Plane", "material": "COPPER", "function": "PLANE", "side": "INTERNAL", "copper_thickness": 0.0012},
            {"name": "BOTTOM", "sequence": 3, "type": "Conductor", "material": "COPPER", "function": "CONDUCTOR", "side": "BOTTOM", "copper_thickness": 0.0014},
        ],
    }


def geometry(
    *,
    width_count: int = 1,
    min_width: float | None = 0.01,
    max_width: float | None = 0.02,
    length: float | None = 1.5,
    area: float | None = None,
    bbox: dict | None = None,
    trace: bool = True,
    plane: bool = False,
    vias: bool = False,
) -> dict:
    return {
        "units": "INCH",
        "known_width_count": width_count,
        "min_width": min_width,
        "max_width": max_width,
        "total_length": length,
        "total_area": area,
        "bbox": bbox,
        "has_trace_like_geometry": trace,
        "has_plane_like_geometry": plane,
        "has_vias": vias,
    }


def branch(
    branch_id: str,
    net_name: str,
    net_type: str,
    branch_type: str,
    *,
    layer: str | None = "TOP",
    geom: dict | None = None,
    current_basis: str = "unresolved",
    estimated_current_a: float | None = None,
    current_model_ref: str | None = "cm_v3p3",
    unresolved_flags: list[str] | None = None,
) -> dict:
    return {
        "branch_id": branch_id,
        "net_name": net_name,
        "topology_net_type": net_type,
        "branch_type": branch_type,
        "layer": layer,
        "layers": [layer] if layer else [],
        "copper_object_refs": [],
        "pin_refs": [],
        "source_refs": [],
        "sink_refs": [],
        "object_count": 2,
        "geometry_summary": geom or geometry(),
        "current_model_ref": current_model_ref,
        "estimated_current_a": estimated_current_a,
        "current_basis": current_basis,
        "thermal_model_ref": None,
        "association_basis": "explicit_net_group",
        "confidence": 1.0,
        "unresolved_flags": unresolved_flags or [],
    }


def branch_topology_fixture(branches: list[dict] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "branches": branches
        if branches is not None
        else [
            branch("br_v3p3_top_trace_group_000001", "V3P3", "power", "trace_group"),
            branch(
                "br_gnd_l2_plane_region_000001",
                "GND",
                "ground",
                "plane_region",
                layer="L2",
                geom=geometry(width_count=0, min_width=None, max_width=None, length=None, area=10.0, bbox={"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1}, trace=False, plane=True),
                current_model_ref=None,
            ),
            branch(
                "br_sig_a_bottom_pad_group_000001",
                "SIG_A",
                "signal",
                "pad_group",
                layer="BOTTOM",
                geom=geometry(width_count=1, length=None, area=None, bbox={"min_x": 2, "min_y": 2, "max_x": 3, "max_y": 3}, trace=False),
                current_model_ref=None,
            ),
        ],
        "net_branch_index": {},
        "unresolved": [],
        "execution_pass": True,
        "branch_topology_pass": True,
    }


def invoke(
    tmp_path: Path,
    *,
    topology: dict | None = None,
    copper: dict | None = None,
    branches: dict | None = None,
    stackup: dict | None = None,
    extra: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], Path]:
    topology_path = write_json(tmp_path / "topology.json", topology or topology_fixture())
    copper_path = write_json(tmp_path / "copper.json", copper or copper_association_fixture())
    branch_path = write_json(tmp_path / "branches.json", branches or branch_topology_fixture())
    stackup_path = write_json(tmp_path / "stackup.json", stackup or stackup_fixture())
    out = tmp_path / "geometry-review.json"
    result = run_review(
        "--project",
        "unit",
        "--topology",
        str(topology_path),
        "--copper-association",
        str(copper_path),
        "--branch-topology",
        str(branch_path),
        "--stackup",
        str(stackup_path),
        "--out",
        str(out),
        *extra,
    )
    return result, out


def record_for(artifact: dict, branch_id: str) -> dict:
    return [record for record in artifact["review_records"] if record["branch_id"] == branch_id][0]


def evidence_types(artifact: dict, branch_id: str) -> set[str]:
    return {item["evidence_type"] for item in artifact["evidence_records"] if item["branch_id"] == branch_id}


def test_trace_branch_with_width_length_produces_review_and_evidence(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    rec = record_for(artifact, "br_v3p3_top_trace_group_000001")
    assert rec["geometry"]["known_width_count"] == 1
    assert {"width", "length"} <= evidence_types(artifact, rec["branch_id"])


def test_plane_branch_with_area_bbox_produces_evidence(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    types = evidence_types(read_json(out), "br_gnd_l2_plane_region_000001")
    assert {"area", "bbox"} <= types


def test_via_cluster_produces_via_evidence(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_top_via_cluster_000001", "V3P3", "power", "via_cluster", geom=geometry(vias=True, trace=False))
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    rec = record_for(read_json(out), "br_v3p3_top_via_cluster_000001")
    assert rec["geometry"]["has_vias"] is True
    assert "width" in evidence_types(read_json(out), rec["branch_id"])


def test_pad_group_produces_pad_geometry_evidence(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "bbox" in evidence_types(read_json(out), "br_sig_a_bottom_pad_group_000001")


def test_power_branch_unresolved_current_creates_needs_current_status(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    rec = record_for(read_json(out), "br_v3p3_top_trace_group_000001")
    assert rec["review_status"] == "needs_current_model"
    assert "current_unknown" in rec["unresolved_flags"]


def test_power_branch_estimated_current_remains_null(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    rec = record_for(read_json(out), "br_v3p3_top_trace_group_000001")
    assert rec["current_context"]["estimated_current_a"] is None
    assert rec["current_context"]["current_known"] is False


def test_trace_branch_missing_width_creates_unresolved(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_top_trace_group_000001", "V3P3", "power", "trace_group", geom=geometry(width_count=0, min_width=None, max_width=None))
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_width" for item in read_json(out)["unresolved"])


def test_trace_branch_missing_length_creates_unresolved(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_top_trace_group_000001", "V3P3", "power", "trace_group", geom=geometry(length=None))
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_length" for item in read_json(out)["unresolved"])


def test_plane_branch_missing_area_bbox_creates_unresolved(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_gnd_l2_plane_region_000001", "GND", "ground", "plane_region", layer="L2", geom=geometry(width_count=0, min_width=None, max_width=None, length=None, area=None, bbox=None, trace=False, plane=True))
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_area" for item in read_json(out)["unresolved"])


def test_missing_stackup_layer_creates_unresolved(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_missing_trace_group_000001", "V3P3", "power", "trace_group", layer="MISSING")
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_layer" for item in read_json(out)["unresolved"])


def test_non_copper_layer_creates_unresolved(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, stackup=stackup_fixture(non_copper_top=True))

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "non_copper_layer" for item in read_json(out)["unresolved"])


def test_stackup_copper_thickness_is_copied_to_evidence(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    evidence = [
        item for item in read_json(out)["evidence_records"]
        if item["branch_id"] == "br_v3p3_top_trace_group_000001" and item["evidence_type"] == "stackup_copper_thickness"
    ]
    assert evidence[0]["value"] == 0.0014


def test_signal_branch_defaults_without_current_failure(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    rec = record_for(read_json(out), "br_sig_a_bottom_pad_group_000001")
    assert rec["review_status"] in {"evidence_only", "ready_for_later_calculation"}
    assert "current_unknown" not in rec["unresolved_flags"]


def test_strict_mode_fails_power_branch_unknown_current(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, extra=("--strict",))

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["geometry_review_pass"] is False
    assert any("power branch current unknown" in error for error in artifact["errors"])


def test_strict_mode_fails_power_trace_missing_width_length(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_top_trace_group_000001", "V3P3", "power", "trace_group", geom=geometry(width_count=0, min_width=None, max_width=None, length=None))
    ])
    result, out = invoke(tmp_path, branches=branches, extra=("--strict",))

    assert result.returncode == 1
    assert any("power trace branch missing width/length" in error for error in read_json(out)["errors"])


def test_non_strict_mode_passes_with_unresolved_current_geometry(tmp_path: Path) -> None:
    branches = branch_topology_fixture([
        branch("br_v3p3_top_trace_group_000001", "V3P3", "power", "trace_group", geom=geometry(width_count=0, min_width=None, max_width=None, length=None))
    ])
    result, out = invoke(tmp_path, branches=branches)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["geometry_review_pass"] is True
    assert artifact["unresolved"]


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "review_records",
        "evidence_records",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "geometry_review_pass",
        "human_review_needed",
    }
    assert expected.issubset(artifact)


def test_exit_code_2_for_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "review.json"
    result = run_review(
        "--project",
        "unit",
        "--topology",
        str(tmp_path / "missing.json"),
        "--copper-association",
        str(write_json(tmp_path / "copper.json", copper_association_fixture())),
        "--branch-topology",
        str(write_json(tmp_path / "branches.json", branch_topology_fixture())),
        "--stackup",
        str(write_json(tmp_path / "stackup.json", stackup_fixture())),
        "--out",
        str(out),
    )

    assert result.returncode == 2
    assert not out.exists()


def test_converter_shaped_branch_fixture_works(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["review_record_count"] == 3
    assert artifact["summary"]["evidence_record_count"] >= 10
