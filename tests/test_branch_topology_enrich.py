from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "branch_topology_enrich.py"


def run_enricher(*args: str) -> subprocess.CompletedProcess[str]:
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


def branch(branch_id: str, net: str, branch_type: str = "trace_group", **extra: object) -> dict:
    row = {
        "branch_id": branch_id,
        "net_name": net,
        "branch_type": branch_type,
        "topology_net_type": "power" if net.startswith("V") else "ground" if net == "GND" else "signal",
        "layer": "TOP",
        "estimated_current_a": None,
        "current_basis": "unresolved",
        "current_model_ref": None,
        "unresolved_flags": [],
    }
    row.update(extra)
    return row


def branch_topology_fixture(branches: list[dict] | None = None, key: str = "branches") -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        key: branches
        if branches is not None
        else [
            branch("br_v5", "V5P0"),
            branch("br_gnd", "GND", "plane_region"),
            branch("br_sig", "SDA"),
        ],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "branch_topology_pass": True,
    }


def component_role(
    refdes: str,
    role: str,
    subtype: str,
    nets: list[str],
    *,
    power: list[str] | None = None,
    ground: list[str] | None = None,
) -> dict:
    return {
        "refdes": refdes,
        "mpn": None,
        "value": None,
        "description": "",
        "footprint": "",
        "role": role,
        "role_subtype": subtype,
        "confidence": 0.8,
        "evidence": [],
        "connected_nets": nets,
        "power_nets": power if power is not None else [net for net in nets if net.startswith("V")],
        "ground_nets": ground or ([] if "GND" not in nets else ["GND"]),
        "input_nets": [],
        "output_nets": [],
        "pass_through_nets": nets if role == "pass_through" else [],
        "unresolved": [],
    }


def net_role(name: str, role: str = "power") -> dict:
    return {
        "net_name": name,
        "role": role,
        "voltage": None,
        "confidence": 0.9,
        "evidence": [],
        "connected_sources": [],
        "connected_sinks": [],
        "connected_pass_through": [],
        "unresolved": [],
    }


def role_resolution_fixture(
    *,
    nets: list[dict] | None = None,
    components: list[dict] | None = None,
    unresolved: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "component_roles": components
        if components is not None
        else [
            component_role("P1", "source", "connector_power_input_or_io", ["V5P0"], power=["V5P0"]),
            component_role("U1", "sink", "ic_load", ["V5P0", "GND"], power=["V5P0"], ground=["GND"]),
            component_role("R1", "pass_through", "zero_ohm_link", ["V5P0", "VCC"], power=["V5P0", "VCC"]),
            component_role("TP1", "bidirectional_or_interface", "test_point_signal", ["SDA"], power=[]),
        ],
        "net_roles": nets
        if nets is not None
        else [net_role("V5P0"), net_role("GND", "ground"), net_role("SDA", "signal"), net_role("VCC")],
        "pin_roles": [],
        "role_edges": [],
        "unresolved": unresolved or [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "role_resolution_pass": True,
    }


def rail_relationship(
    rel_id: str,
    parent: str | None,
    child: str | None,
    through: str,
    rel_type: str = "regulator_conversion",
    unresolved: list[dict] | None = None,
) -> dict:
    return {
        "relationship_id": rel_id,
        "relationship_type": rel_type,
        "parent_rail": parent,
        "child_rail": child,
        "through_component": through,
        "through_subtype": "ldo",
        "confidence": 0.8,
        "direction": "parent_to_child",
        "evidence": [],
        "unresolved": unresolved or [],
    }


def rail(name: str, role: str, *, parents: list[str] | None = None, children: list[str] | None = None) -> dict:
    return {
        "rail": name,
        "role": role,
        "voltage": 5.0 if name == "V5P0" else 3.3 if name == "V3P3" else None,
        "voltage_source": "net_name" if name.startswith("V") else "unknown",
        "confidence": 0.8,
        "source_components": ["P1"] if name == "V5P0" else [],
        "sink_components": ["U1"] if name in {"V5P0", "V3P3"} else [],
        "pass_through_components": ["R1"] if name in {"V5P0", "VCC"} else [],
        "parent_rails": parents or [],
        "child_rails": children or [],
        "evidence": [],
        "unresolved": [],
    }


def rail_relationships_fixture(*, unresolved: list[dict] | None = None) -> dict:
    rel_unresolved = [
        {
            "id": "unres_rel_u2",
            "category": "relationship_direction_unknown",
            "target_type": "relationship",
            "target_id": "rel_v5_u2_v3",
            "notes": "Direction is not deterministic.",
            "blocks": ["current_allocation", "calculation_readiness"],
            "recommended_resolution": "human_review",
            "candidate_rule_ids": [],
        }
    ]
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "rails": [
            rail("V5P0", "source", children=["V3P3"]),
            rail("V3P3", "derived", parents=["V5P0"]),
            rail("VCC", "derived", parents=["V5P0"]),
            rail("GND", "return"),
        ],
        "relationships": [
            rail_relationship("rel_v5_u2_v3", "V5P0", "V3P3", "U2", unresolved=rel_unresolved),
            rail_relationship("rel_v5_r1_vcc", "V5P0", "VCC", "R1", "pass_through"),
        ],
        "source_candidates": [],
        "derived_candidates": [],
        "unresolved": unresolved or rel_unresolved,
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "rail_relationship_pass": True,
    }


def geometry_review_fixture() -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "review_records": [
            {
                "review_id": "geo_br_v5",
                "branch_id": "br_v5",
                "net_name": "V5P0",
                "branch_type": "trace_group",
                "layer": "TOP",
                "geometry": {"units": "INCH", "known_width_count": 1, "min_width": 0.01, "max_width": 0.01, "total_length": 1.2, "total_area": None, "bbox": None},
                "stackup": {"primary_layer": "TOP", "is_copper_layer": True, "copper_thickness": 1.0},
                "evidence": ["ev1"],
                "unresolved_flags": [],
            }
        ],
        "evidence_records": [{"evidence_id": "ev1", "branch_id": "br_v5"}],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "geometry_review_pass": True,
    }


def invoke(
    tmp_path: Path,
    *,
    branch_topology: dict | None = None,
    role_resolution: dict | None = None,
    rail_relationships: dict | None = None,
    geometry_review: dict | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    branch_path = write_json(tmp_path / "branch-topology.json", branch_topology or branch_topology_fixture())
    role_path = write_json(tmp_path / "role-resolution.json", role_resolution or role_resolution_fixture())
    rail_path = write_json(tmp_path / "rail-relationships.json", rail_relationships or rail_relationships_fixture())
    out = tmp_path / "branch-enriched.json"
    args = [
        "--project",
        "unit",
        "--branch-topology",
        str(branch_path),
        "--role-resolution",
        str(role_path),
        "--rail-relationships",
        str(rail_path),
        "--out",
        str(out),
    ]
    if geometry_review is not None:
        args.extend(["--geometry-review", str(write_json(tmp_path / "geometry-review.json", geometry_review))])
    return run_enricher(*args), out


def branch_for(artifact: dict, branch_id: str) -> dict:
    return {row["branch_id"]: row for row in artifact["branches"]}[branch_id]


def test_missing_required_branch_topology_input_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    role_path = write_json(tmp_path / "role.json", role_resolution_fixture())
    rail_path = write_json(tmp_path / "rail.json", rail_relationships_fixture())
    result = run_enricher("--project", "unit", "--branch-topology", str(tmp_path / "missing.json"), "--role-resolution", str(role_path), "--rail-relationships", str(rail_path), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_missing_required_role_resolution_input_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    branch_path = write_json(tmp_path / "branch.json", branch_topology_fixture())
    rail_path = write_json(tmp_path / "rail.json", rail_relationships_fixture())
    result = run_enricher("--project", "unit", "--branch-topology", str(branch_path), "--role-resolution", str(tmp_path / "missing.json"), "--rail-relationships", str(rail_path), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_missing_required_rail_relationships_input_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    branch_path = write_json(tmp_path / "branch.json", branch_topology_fixture())
    role_path = write_json(tmp_path / "role.json", role_resolution_fixture())
    result = run_enricher("--project", "unit", "--branch-topology", str(branch_path), "--role-resolution", str(role_path), "--rail-relationships", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


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
        "branches",
        "rail_context",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "branch_enrichment_pass",
    }
    assert expected.issubset(artifact)


def test_branch_net_matching_rail_gets_rail_name_and_context(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["rail_name"] == "V5P0"
    assert row["rail_role"] == "source"
    assert row["rail_voltage"] == 5.0


def test_branch_on_v24p0_marked_power_branch(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, branch_topology=branch_topology_fixture([branch("br_v24", "V24P0")]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert branch_for(read_json(out), "br_v24")["is_power_branch"] is True


def test_branch_on_gnd_marked_ground_branch(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_gnd")
    assert row["is_ground_branch"] is True
    assert row["rail_role"] == "return"


def test_signal_branch_included_but_no_branch_current_unknown(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_sig")
    assert row["net_name"] == "SDA"
    assert not any(item["category"] == "branch_current_unknown" for item in row["unresolved"])


def test_source_candidates_attach_from_component_roles(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert [row["refdes"] for row in branch_for(read_json(out), "br_v5")["source_candidates"]] == ["P1"]


def test_sink_candidates_attach_from_component_roles(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert [row["refdes"] for row in branch_for(read_json(out), "br_v5")["sink_candidates"]] == ["U1"]


def test_pass_through_candidates_attach_from_component_roles(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert [row["refdes"] for row in branch_for(read_json(out), "br_v5")["pass_through_candidates"]] == ["R1"]


def test_rail_relationship_ids_attach_to_branch_by_parent_rail(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    ids = [row["relationship_id"] for row in branch_for(read_json(out), "br_v5")["rail_relationships"]]
    assert "rel_v5_u2_v3" in ids


def test_rail_relationship_ids_attach_to_branch_by_child_rail(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, branch_topology=branch_topology_fixture([branch("br_v3", "V3P3")]))

    assert result.returncode == 0, result.stderr + result.stdout
    ids = [row["relationship_id"] for row in branch_for(read_json(out), "br_v3")["rail_relationships"]]
    assert "rel_v5_u2_v3" in ids


def test_rail_parent_and_child_rails_populate_on_branch(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["parent_rails"] == []
    assert row["child_rails"] == ["V3P3"]


def test_geometry_review_record_attaches_by_branch_id(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, geometry_review=geometry_review_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    context = branch_for(read_json(out), "br_v5")["geometry_context"]
    assert context["has_geometry_context"] is True
    assert context["min_width"] == 0.01
    assert context["copper_thickness"] == 1.0


def test_missing_geometry_review_does_not_fail(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["branch_enrichment_pass"] is True
    assert branch_for(artifact, "br_v5")["geometry_context"] == {}


def test_power_branch_with_current_missing_emits_branch_current_unknown(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["category"] == "branch_current_unknown" for item in branch_for(read_json(out), "br_v5")["unresolved"])


def test_branch_with_explicit_numeric_current_preserves_it_and_marks_known(tmp_path: Path) -> None:
    row = branch("br_v5", "V5P0", estimated_current_a=0.125, current_model_ref="cm1")
    result, out = invoke(tmp_path, branch_topology=branch_topology_fixture([row]))

    assert result.returncode == 0, result.stderr + result.stdout
    status = branch_for(read_json(out), "br_v5")["current_model_status"]
    assert status["branch_current_known"] is True
    assert status["branch_current_a"] == 0.125
    assert status["current_source"] == "cm1"


def test_ready_for_current_allocation_true_with_rail_source_and_sink_context(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert branch_for(read_json(out), "br_v5")["calculation_readiness_seed"]["ready_for_current_allocation"] is True


def test_blocked_reasons_include_branch_source_unknown_without_source_context(tmp_path: Path) -> None:
    rels = rail_relationships_fixture()
    rels["rails"] = [rail("V3P3", "derived")]
    role = role_resolution_fixture(nets=[net_role("V3P3")], components=[component_role("U1", "sink", "ic_load", ["V3P3"], power=["V3P3"])])
    result, out = invoke(tmp_path, branch_topology=branch_topology_fixture([branch("br_v3", "V3P3")]), role_resolution=role, rail_relationships=rels)

    assert result.returncode == 0, result.stderr + result.stdout
    reasons = branch_for(read_json(out), "br_v3")["calculation_readiness_seed"]["blocked_reasons"]
    assert "branch_source_unknown" in reasons


def test_blocked_reasons_include_branch_sink_unknown_without_sink_context(tmp_path: Path) -> None:
    role = role_resolution_fixture(nets=[net_role("V5P0")], components=[component_role("P1", "source", "connector_power_input_or_io", ["V5P0"], power=["V5P0"])])
    rels = rail_relationships_fixture()
    rels["rails"] = [rail("V5P0", "source")]
    rels["relationships"] = []
    rels["unresolved"] = []
    result, out = invoke(tmp_path, branch_topology=branch_topology_fixture([branch("br_v5", "V5P0")]), role_resolution=role, rail_relationships=rels)

    assert result.returncode == 0, result.stderr + result.stdout
    reasons = branch_for(read_json(out), "br_v5")["calculation_readiness_seed"]["blocked_reasons"]
    assert "branch_sink_unknown" in reasons


def test_propagated_rail_relationship_unresolved_appears_in_branch_unresolved(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    categories = [item["category"] for item in branch_for(read_json(out), "br_v5")["unresolved"]]
    assert "relationship_direction_unknown" in categories


def test_summary_counts_are_internally_consistent(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, geometry_review=geometry_review_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    branches = artifact["branches"]
    assert summary["branch_count"] == len(branches)
    assert summary["power_branch_count"] == sum(1 for row in branches if row["is_power_branch"])
    assert summary["enriched_branch_count"] == len(branches)
    assert summary["branches_with_rail_context"] == sum(1 for row in branches if row["rail_name"] is not None)
    assert summary["branches_with_source_candidates"] == sum(1 for row in branches if row["source_candidates"])
    assert summary["branches_with_sink_candidates"] == sum(1 for row in branches if row["sink_candidates"])
    assert summary["branches_with_pass_through_candidates"] == sum(1 for row in branches if row["pass_through_candidates"])
    assert summary["branches_with_geometry_context"] == sum(1 for row in branches if row["geometry_context"])
    assert summary["branches_ready_for_current_allocation"] == sum(1 for row in branches if row["calculation_readiness_seed"]["ready_for_current_allocation"])
    assert summary["unresolved_count"] == len(artifact["unresolved"])


def test_no_current_is_inferred_when_absent(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    status = branch_for(read_json(out), "br_v5")["current_model_status"]
    assert status["branch_current_known"] is False
    assert status["branch_current_a"] is None
    assert status["current_source"] is None


def test_manual_converter_shaped_minimal_fixtures_work(tmp_path: Path) -> None:
    branches = branch_topology_fixture([branch("br_v3", "V3P3"), branch("br_sig", "SCL")], key="branch_records")
    role = role_resolution_fixture(
        nets=[net_role("V3P3"), net_role("SCL", "clock"), net_role("GND", "ground")],
        components=[
            component_role("U50", "source", "ldo", ["V5P0", "V3P3", "GND"], power=["V5P0", "V3P3"], ground=["GND"]),
            component_role("U1", "sink", "ic_load", ["V3P3", "GND", "SCL"], power=["V3P3"], ground=["GND"]),
        ],
    )
    rels = rail_relationships_fixture()
    rels["rails"] = [rail("V3P3", "derived", parents=["V5P0"]), rail("GND", "return")]
    result, out = invoke(tmp_path, branch_topology=branches, role_resolution=role, rail_relationships=rels)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["branch_enrichment_pass"] is True
    assert len(artifact["branches"]) == 2
    assert branch_for(artifact, "br_v3")["rail_name"] == "V3P3"
