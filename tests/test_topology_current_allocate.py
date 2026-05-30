from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_current_allocate.py"


def run_allocator(*args: str) -> subprocess.CompletedProcess[str]:
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


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_record(
    record_type: str,
    record_id: str,
    value: float,
    *,
    branch_id: str | None = None,
    rail_name: str | None = None,
    refdes: str | None = None,
    current_type: str = "requirement",
    usable: bool = False,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_type": record_type,
        "target_type": "branch" if record_type == "branch_current" else "rail" if record_type == "rail_current" else "component" if record_type == "component_current" else "rating",
        "branch_id": branch_id,
        "rail_name": rail_name,
        "net_name": rail_name,
        "refdes": refdes,
        "pin": None,
        "value": value,
        "unit": "A",
        "current_type": current_type,
        "basis": "manual_design_requirement",
        "source": "current_model",
        "confidence": 1.0,
        "evidence_refs": [f"evidence:{record_id}"],
        "source_artifacts": [{"artifact_type": "current_model", "path": "current-model.json", "record_id": record_id, "notes": "fixture"}],
        "usable_for_calculation": usable,
        "human_review_needed": False,
        "missing_data_manifest_item_ids": [],
        "missing_data_group_ids": [],
        "warnings": [],
    }


def branch_current(branch_id: str = "br_vin", value: float = 0.5) -> dict[str, Any]:
    return current_record("branch_current", f"cur_branch_{branch_id}", value, branch_id=branch_id, rail_name="VIN", usable=True)


def rail_current(rail_name: str = "V3P3", value: float = 0.75) -> dict[str, Any]:
    return current_record("rail_current", f"cur_rail_{rail_name}", value, rail_name=rail_name, usable=False)


def component_current(refdes: str = "U12", rail_name: str = "V3P3", value: float = 0.12, current_type: str = "max") -> dict[str, Any]:
    return current_record("component_current", f"cur_comp_{refdes}_{rail_name}_{current_type}", value, rail_name=rail_name, refdes=refdes, current_type=current_type, usable=False)


def rating_record() -> dict[str, Any]:
    return current_record("rating", "cur_rating_p20_1", 2.0, refdes="P20", current_type="max", usable=False)


def current_models_fixture(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "normalized_currents": records if records is not None else [branch_current()],
        "rejected_currents": [],
        "unresolved_references": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def candidate(refdes: str, role: str = "sink") -> dict[str, Any]:
    return {"refdes": refdes, "role": role, "role_subtype": "ic_load" if role == "sink" else "fuse", "confidence": 0.9, "evidence_refs": []}


def branch(
    branch_id: str,
    rail_name: str,
    *,
    sinks: list[str] | None = None,
    sources: list[str] | None = None,
    passthroughs: list[str] | None = None,
    blocked: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "branch_id": branch_id,
        "net_name": rail_name,
        "rail_name": rail_name,
        "branch_type": "trace_group",
        "is_power_branch": True,
        "rail_role": "source" if rail_name == "VIN" else "derived",
        "source_candidates": [candidate(ref, "source") for ref in (sources or [])],
        "sink_candidates": [candidate(ref, "sink") for ref in (sinks or [])],
        "pass_through_candidates": [candidate(ref, "pass_through") for ref in (passthroughs or [])],
        "calculation_readiness_seed": {
            "ready_for_current_allocation": not blocked,
            "blocked_reasons": blocked or [],
        },
        "evidence": [],
        "unresolved": [{"category": item, "target_type": "branch", "target_id": branch_id} for item in (blocked or [])],
    }


def branch_topology_fixture(branches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = branches if branches is not None else [branch("br_vin", "VIN", sources=["P1"])]
    rail_context: dict[str, list[str]] = {}
    for row in rows:
        rail_context.setdefault(row["rail_name"], []).append(row["branch_id"])
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "branches": rows,
        "rail_context": [{"rail": rail, "branch_ids": ids} for rail, ids in sorted(rail_context.items())],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "branch_enrichment_pass": True,
    }


def relationship(
    *,
    rel_id: str = "rel_vin_f1_vout",
    parent: str = "VIN",
    child: str = "VOUT",
    through: str = "F1",
    direction: str = "parent_to_child",
    rel_type: str = "pass_through",
) -> dict[str, Any]:
    return {
        "relationship_id": rel_id,
        "relationship_type": rel_type,
        "parent_rail": parent,
        "child_rail": child,
        "through_component": through,
        "through_subtype": "fuse",
        "confidence": 0.9,
        "direction": direction,
        "evidence": [],
        "unresolved": [] if direction != "unknown" else [{"category": "relationship_direction_unknown", "target_type": "relationship", "target_id": rel_id}],
    }


def rail_relationships_fixture(relationships: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "rails": [],
        "relationships": relationships or [],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "rail_relationship_pass": True,
    }


def component_role(refdes: str, role: str = "sink", subtype: str | None = None) -> dict[str, Any]:
    return {
        "refdes": refdes,
        "role": role,
        "role_subtype": subtype or ("fuse" if role == "pass_through" else "ic_load"),
        "confidence": 0.9,
        "connected_nets": [],
        "power_nets": [],
        "ground_nets": [],
        "input_nets": [],
        "output_nets": [],
        "pass_through_nets": [],
        "unresolved": [],
    }


def role_resolution_fixture(components: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "component_roles": components if components is not None else [component_role("F1", "pass_through", "fuse"), component_role("U12"), component_role("U13")],
        "net_roles": [],
        "pin_roles": [],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "role_resolution_pass": True,
    }


def manifest_item(
    category: str,
    target_id: str,
    *,
    target_type: str = "branch",
    affected_rails: list[str] | None = None,
    affected_branches: list[str] | None = None,
    affected_components: list[str] | None = None,
    blocks: list[str] | None = None,
    resolution_path: str = "human_review",
) -> dict[str, Any]:
    return {
        "manifest_id": f"mdi_manifest_{category}_{target_id}",
        "source_missing_data_id": f"source_{category}_{target_id}",
        "category": category,
        "target_type": target_type,
        "target_id": target_id,
        "normalized_target": target_id,
        "affected_rails": affected_rails or ([] if target_type != "rail" else [target_id]),
        "affected_branches": affected_branches or ([] if target_type != "branch" else [target_id]),
        "affected_components": affected_components or ([] if target_type != "component" else [target_id]),
        "blocks": blocks or ["current_allocation", "calculation_readiness"],
        "group_id": f"group_{category}_{target_id}",
        "resolution_path": resolution_path,
        "resolution_queue": resolution_path,
    }


def manifest_fixture(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "manifest_items": items or [],
        "groups": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "missing_data_manifest_pass": True,
    }


def invoke(
    tmp_path: Path,
    *,
    current_models: dict[str, Any] | None = None,
    branch_topology: dict[str, Any] | None = None,
    rail_relationships: dict[str, Any] | None = None,
    role_resolution: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    current_path = write_json(tmp_path / "current-models-normalized.json", current_models or current_models_fixture())
    branch_path = write_json(tmp_path / "branch-topology-enriched.json", branch_topology or branch_topology_fixture())
    rail_path = write_json(tmp_path / "rail-relationships.json", rail_relationships or rail_relationships_fixture())
    role_path = write_json(tmp_path / "role-resolution.json", role_resolution or role_resolution_fixture())
    manifest_path = write_json(tmp_path / "manifest.json", manifest or manifest_fixture())
    out = tmp_path / "topology-current-allocation.json"
    result = run_allocator(
        "--project",
        "TestProject",
        "--current-models-normalized",
        str(current_path),
        "--branch-topology-enriched",
        str(branch_path),
        "--rail-relationships",
        str(rail_path),
        "--role-resolution",
        str(role_path),
        "--missing-data-manifest",
        str(manifest_path),
        "--out",
        str(out),
    )
    return result, out


def allocation_of_type(artifact: dict[str, Any], allocation_type: str) -> dict[str, Any]:
    rows = [row for row in artifact["allocation_records"] if row["allocation_type"] == allocation_type]
    assert len(rows) == 1
    return rows[0]


def unresolved_reason(artifact: dict[str, Any], reason: str) -> dict[str, Any]:
    rows = [row for row in artifact["unresolved_allocations"] if row["reason_code"] == reason]
    assert rows
    return rows[0]


def all_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(all_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(all_values(child))
    return values


def all_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(all_keys(child))
    return keys


def test_missing_required_current_models_exits_2(tmp_path: Path) -> None:
    branch_path = write_json(tmp_path / "branch.json", branch_topology_fixture())
    rail_path = write_json(tmp_path / "rail.json", rail_relationships_fixture())
    role_path = write_json(tmp_path / "role.json", role_resolution_fixture())
    manifest_path = write_json(tmp_path / "manifest.json", manifest_fixture())
    out = tmp_path / "out.json"
    result = run_allocator("--project", "TestProject", "--current-models-normalized", str(tmp_path / "missing.json"), "--branch-topology-enriched", str(branch_path), "--rail-relationships", str(rail_path), "--role-resolution", str(role_path), "--missing-data-manifest", str(manifest_path), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_malformed_current_models_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    branch_path = write_json(tmp_path / "branch.json", branch_topology_fixture())
    rail_path = write_json(tmp_path / "rail.json", rail_relationships_fixture())
    role_path = write_json(tmp_path / "role.json", role_resolution_fixture())
    manifest_path = write_json(tmp_path / "manifest.json", manifest_fixture())
    out = tmp_path / "out.json"
    result = run_allocator("--project", "TestProject", "--current-models-normalized", str(bad), "--branch-topology-enriched", str(branch_path), "--rail-relationships", str(rail_path), "--role-resolution", str(role_path), "--missing-data-manifest", str(manifest_path), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "project",
        "generated_at_utc",
        "execution_pass",
        "topology_current_allocation_pass",
        "schema_version",
        "source_artifacts",
        "allocation_records",
        "unresolved_allocations",
        "passthrough_records",
        "summary",
        "errors",
        "warnings",
    }
    assert expected.issubset(read_json(out))


def test_cli_writes_valid_json_artifact(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        if isinstance(value, float):
            assert math.isfinite(value)


def test_summary_counts_match_arrays(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    records = current_models_fixture()["normalized_currents"]
    allocations = artifact["allocation_records"]
    unresolved = artifact["unresolved_allocations"]
    passthroughs = artifact["passthrough_records"]
    assert summary["input_current_record_count"] == len(records)
    assert summary["allocation_record_count"] == len(allocations)
    assert summary["unresolved_allocation_count"] == len(unresolved)
    assert summary["passthrough_record_count"] == len(passthroughs)
    assert summary["directly_usable_branch_allocation_count"] == sum(1 for row in allocations if row["allocation_type"] == "explicit_branch_current" and row["usable_for_calculation"])
    assert summary["deterministic_rail_allocation_count"] == sum(1 for row in allocations if row["allocation_type"] == "deterministic_single_path_rail_current")
    assert summary["deterministic_component_allocation_count"] == sum(1 for row in allocations if row["allocation_type"] == "deterministic_branch_sum")
    assert summary["deterministic_passthrough_allocation_count"] == sum(1 for row in allocations if row["allocation_type"] == "deterministic_passthrough_current")
    assert summary["error_count"] == len(artifact["errors"])
    assert summary["warning_count"] == len(artifact["warnings"])


def test_explicit_branch_current_emits_usable_allocation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models=current_models_fixture([branch_current("br_vin", 0.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = allocation_of_type(read_json(out), "explicit_branch_current")
    assert row["branch_id"] == "br_vin"
    assert row["allocated_current_a"] == 0.5
    assert row["usable_for_calculation"] is True


def test_explicit_branch_current_preserves_source_record_id(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models=current_models_fixture([branch_current("br_vin", 0.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = allocation_of_type(read_json(out), "explicit_branch_current")
    assert row["source_current_record_ids"] == ["cur_branch_br_vin"]


def test_rating_records_are_not_allocated(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models=current_models_fixture([rating_record()]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["rating_input_count"] == 1
    assert artifact["allocation_records"] == []


def test_single_path_rail_current_allocates_when_only_one_branch_exists(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("V3P3", 0.75)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=["U12"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = allocation_of_type(read_json(out), "deterministic_single_path_rail_current")
    assert row["branch_id"] == "br_v3p3"
    assert row["allocated_current_a"] == 0.75


def test_multi_branch_rail_current_does_not_divide_current(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("V3P3", 0.75)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3_a", "V3P3"), branch("br_v3p3_b", "V3P3")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["allocation_records"]
    assert not any(row.get("allocated_current_a") == 0.375 for row in artifact["allocation_records"])


def test_multi_branch_rail_current_emits_shared_plane_unresolved(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("V3P3", 0.75)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3_a", "V3P3"), branch("br_v3p3_b", "V3P3")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "shared_plane_current_unknown")
    assert row["rail_name"] == "V3P3"


def test_component_current_allocates_when_single_sink_branch_mapping_exists(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([component_current("U12", "V3P3", 0.12)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=["U12"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = allocation_of_type(read_json(out), "deterministic_branch_sum")
    assert row["branch_id"] == "br_v3p3"
    assert row["allocated_current_a"] == 0.12


def test_component_current_unresolved_when_mapping_missing(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([component_current("U12", "V3P3", 0.12)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=[])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "component_to_branch_mapping_unknown")
    assert row["refdes"] == "U12"


def test_component_current_unresolved_when_multiple_candidate_branches_exist(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([component_current("U12", "V3P3", 0.12)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3_a", "V3P3", sinks=["U12"]), branch("br_v3p3_b", "V3P3", sinks=["U12"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "component_to_branch_mapping_unknown")
    assert row["refdes"] == "U12"


def test_passthrough_current_copies_when_direction_and_single_path_known(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([branch_current("br_vin", 0.5)]),
        branch_topology=branch_topology_fixture([branch("br_vin", "VIN", sources=["P1"], passthroughs=["F1"]), branch("br_vout", "VOUT", sinks=["U1"], passthroughs=["F1"])]),
        rail_relationships=rail_relationships_fixture([relationship()]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = allocation_of_type(artifact, "deterministic_passthrough_current")
    assert row["branch_id"] == "br_vout"
    assert row["allocated_current_a"] == 0.5
    assert artifact["passthrough_records"][0]["current_transfer_status"] == "deterministic"


def test_passthrough_current_unresolved_when_direction_unknown(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([branch_current("br_vin", 0.5)]),
        branch_topology=branch_topology_fixture([branch("br_vin", "VIN", sources=["P1"], passthroughs=["F1"]), branch("br_vout", "VOUT", sinks=["U1"], passthroughs=["F1"])]),
        rail_relationships=rail_relationships_fixture([relationship(direction="unknown")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "relationship_direction_unknown")
    assert row["refdes"] == "F1"


def test_passthrough_current_unresolved_when_source_sink_not_resolved(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([branch_current("br_vin", 0.5)]),
        branch_topology=branch_topology_fixture([branch("br_vin", "VIN", sources=["P1"], passthroughs=["F1"], blocked=["source_sink_not_resolved"]), branch("br_vout", "VOUT", sinks=["U1"], passthroughs=["F1"])]),
        rail_relationships=rail_relationships_fixture([relationship()]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "source_sink_not_resolved")
    assert row["refdes"] == "F1"


def test_multiple_component_currents_sum_only_explicit_known_values(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([component_current("U12", "V3P3", 0.12), component_current("U13", "V3P3", 0.18)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=["U12", "U13"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = allocation_of_type(read_json(out), "deterministic_branch_sum")
    assert math.isclose(row["allocated_current_a"], 0.30, rel_tol=1e-12)
    assert set(row["source_current_record_ids"]) == {"cur_comp_U12_V3P3_max", "cur_comp_U13_V3P3_max"}


def test_missing_component_current_is_not_treated_as_zero(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([component_current("U12", "V3P3", 0.12)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=["U12", "U13"])]),
        manifest=manifest_fixture([manifest_item("current_model_missing", "U13", target_type="component", affected_rails=["V3P3"], affected_branches=["br_v3p3"], affected_components=["U13"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = allocation_of_type(artifact, "deterministic_branch_sum")
    assert row["allocated_current_a"] == 0.12
    assert not any(allocation.get("allocated_current_a") == 0 for allocation in artifact["allocation_records"])


def test_malformed_component_current_candidate_is_not_summed_as_zero(tmp_path: Path) -> None:
    malformed = component_current("U12", "V3P3", 0.12)
    malformed["value"] = None
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([malformed]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=["U12"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["allocation_records"]
    row = unresolved_reason(artifact, "missing_current_model")
    assert row["refdes"] == "U12"
    assert any(item["field"] == "component_current_a" for item in row["missing_inputs"])
    assert not any(allocation.get("allocated_current_a") == 0 for allocation in artifact["allocation_records"])


def test_unresolved_allocation_references_source_sink_manifest_items(tmp_path: Path) -> None:
    manifest = manifest_fixture([manifest_item("source_sink_not_resolved", "br_v3p3", affected_rails=["V3P3"], affected_branches=["br_v3p3"])])
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("V3P3", 0.75)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3")]),
        manifest=manifest,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "source_sink_not_resolved")
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_source_sink_not_resolved_br_v3p3"]
    assert "source_sink_not_resolved" in row["blocked_by_categories"]


def test_branch_current_unknown_manifest_links_to_unresolved_record(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3")]),
        manifest=manifest_fixture([manifest_item("branch_current_unknown", "br_v3p3", affected_rails=["V3P3"], affected_branches=["br_v3p3"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "missing_current_model")
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_branch_current_unknown_br_v3p3"]


def test_resolution_path_and_queue_are_preserved_when_available(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3")]),
        manifest=manifest_fixture([manifest_item("branch_current_unknown", "br_v3p3", affected_rails=["V3P3"], affected_branches=["br_v3p3"], resolution_path="datasheet_extraction")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = unresolved_reason(read_json(out), "missing_current_model")
    assert row["resolution_path"] == "datasheet_extraction"
    assert row["resolution_queue"] == "datasheet_extraction"


def test_no_current_inference_from_rail_or_component_names(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("br_v3p3", 0.75), component_current("br_v3p3", "V1P8", 0.2)]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3", sinks=[])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["allocation_records"]


def test_no_current_division_across_parallel_or_plane_branches(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([rail_current("V3P3", 1.0)]),
        branch_topology=branch_topology_fixture([branch("br_plane_a", "V3P3"), branch("br_plane_b", "V3P3")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not any(row.get("allocated_current_a") == 0.5 for row in artifact["allocation_records"])
    assert unresolved_reason(artifact, "shared_plane_current_unknown")


def test_unknown_current_is_not_zero(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([]),
        branch_topology=branch_topology_fixture([branch("br_v3p3", "V3P3")]),
        manifest=manifest_fixture([manifest_item("branch_current_unknown", "br_v3p3", affected_rails=["V3P3"], affected_branches=["br_v3p3"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not any(row.get("allocated_current_a") == 0 for row in artifact["allocation_records"])
    assert artifact["unresolved_allocations"]


def test_no_findings_or_pass_fail_judgments_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    raw_keys = "\n".join(key.lower() for key in all_keys(artifact))
    forbidden = ["finding_id", "issue_id", "compliance_pass", "compliance_fail", "margin_pass", "margin_fail", "pass_fail", "judgment"]
    assert not any(token in raw_keys for token in forbidden)


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models=current_models_fixture([
            branch_current("br_vin", 0.5),
            rail_current("V3P3", 0.75),
            component_current("U12", "V3P3", 0.12),
            rating_record(),
        ]),
        branch_topology=branch_topology_fixture([
            branch("br_vin", "VIN", sources=["P1"], passthroughs=["F1"]),
            branch("br_vout", "VOUT", sinks=["U1"], passthroughs=["F1"]),
            branch("br_v3p3", "V3P3", sinks=["U12"]),
        ]),
        rail_relationships=rail_relationships_fixture([relationship()]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"
    assert artifact["execution_pass"] is True
    assert artifact["topology_current_allocation_pass"] is True
    assert artifact["summary"]["input_current_record_count"] == 4
    assert artifact["summary"]["rating_input_count"] == 1
    assert artifact["summary"]["allocation_record_count"] >= 3
