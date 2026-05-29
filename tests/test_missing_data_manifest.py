from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "missing_data_manifest.py"


def run_manifest(*args: str) -> subprocess.CompletedProcess[str]:
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


def mdi(
    item_id: str,
    category: str,
    target_type: str,
    target_id: str,
    blocks: list[str],
    *,
    recommended: str = "human_review",
    severity: str = "blocker",
    notes: str | None = None,
) -> dict:
    return {
        "id": item_id,
        "scope": target_type,
        "target_type": target_type,
        "target_id": target_id,
        "category": category,
        "severity": severity,
        "blocks": blocks,
        "recommended_resolution": recommended,
        "source_artifact": "calculation_readiness",
        "evidence": [],
        "notes": notes or f"{category} for {target_id}",
    }


def branch(branch_id: str, net: str, rail: str | None = None, *, components: list[str] | None = None) -> dict:
    components = components or []
    return {
        "branch_id": branch_id,
        "net_name": net,
        "rail_name": rail,
        "branch_type": "trace_group",
        "is_power_branch": rail is not None,
        "is_ground_branch": False,
        "rail_role": "source" if rail == "V24P0" else "derived" if rail else "unknown",
        "rail_voltage": 24.0 if rail == "V24P0" else 5.0 if rail == "V5P0" else None,
        "current_allocation_readiness": {"status": "ready", "ready": True, "blocking_reasons": [], "required_missing_data_ids": [], "notes": []},
        "copper_calculation_readiness": {"status": "blocked", "ready": False, "blocking_reasons": ["branch_current_unknown"], "required_missing_data_ids": [], "notes": []},
        "available_context": {},
        "source_candidates": [{"refdes": ref, "role": "source", "role_subtype": "connector", "confidence": 0.8, "evidence_refs": []} for ref in components[:1]],
        "sink_candidates": [{"refdes": ref, "role": "sink", "role_subtype": "ic_load", "confidence": 0.8, "evidence_refs": []} for ref in components[1:]],
        "pass_through_candidates": [],
        "rail_relationships": [{"relationship_id": "rel_v24_q2_v24_sw", "through_component": "Q2"}] if rail == "V24P0_SW" else [],
        "evidence": [],
        "unresolved": [],
    }


def rail(name: str, role: str, branch_ids: list[str]) -> dict:
    return {
        "rail": name,
        "role": role,
        "voltage": None if name == "VCC" else 24.0 if name == "V24P0" else 5.0,
        "parent_rails": [] if role == "source" else ["V24P0"],
        "child_rails": ["V24P0_SW"] if name == "V24P0" else [],
        "branch_ids": branch_ids,
        "current_allocation_readiness": {"status": "ready", "ready": True, "blocking_reasons": [], "required_missing_data_ids": [], "notes": []},
        "copper_calculation_readiness": {"status": "blocked", "ready": False, "blocking_reasons": ["branch_current_unknown"], "required_missing_data_ids": [], "notes": []},
        "available_context": {},
        "missing_data_ids": [],
        "unresolved": [],
    }


def readiness_fixture(items: list[dict] | None = None) -> dict:
    items = items if items is not None else [
        mdi("mdi_branch_current_unknown_branch_br_v24", "branch_current_unknown", "branch", "br_v24", ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"], recommended="datasheet_extraction"),
        mdi("mdi_branch_current_unknown_branch_br_v24b", "branch_current_unknown", "branch", "br_v24b", ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"], recommended="datasheet_extraction"),
        mdi("mdi_source_sink_not_resolved_branch_br_v24", "source_sink_not_resolved", "branch", "br_v24", ["current_allocation", "calculation_readiness"], recommended="ai_rule_batch"),
        mdi("mdi_voltage_unknown_rail_vcc", "voltage_unknown", "rail", "VCC", ["voltage_drop_calculation"], recommended="deterministic_rule", severity="warning"),
    ]
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {"missing_data_item_count": len(items)},
        "branch_readiness": [
            branch("br_v24", "V24P0", "V24P0", components=["P1", "U1"]),
            branch("br_v24b", "V24P0", "V24P0", components=["P1", "U2"]),
            branch("br_sw", "V24P0_SW", "V24P0_SW", components=["Q2"]),
            branch("br_sig", "SDA", None),
        ],
        "rail_readiness": [
            rail("V24P0", "source", ["br_v24", "br_v24b"]),
            rail("V24P0_SW", "switched", ["br_sw"]),
            rail("VCC", "derived", []),
        ],
        "missing_data_items": items,
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "calculation_readiness_pass": True,
    }


def invoke(tmp_path: Path, readiness: dict | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
    readiness_path = write_json(tmp_path / "readiness.json", readiness or readiness_fixture())
    out = tmp_path / "manifest.json"
    result = run_manifest("--project", "unit", "--calculation-readiness", str(readiness_path), "--out", str(out))
    return result, out


def item_by_category(artifact: dict, category: str) -> dict:
    return [item for item in artifact["manifest_items"] if item["category"] == category][0]


def items_by_category(artifact: dict, category: str) -> list[dict]:
    return [item for item in artifact["manifest_items"] if item["category"] == category]


def queue_for_item(artifact: dict, item_id: str) -> list[str]:
    return [name for name, ids in artifact["resolution_queues"].items() if item_id in ids]


def test_missing_required_calculation_readiness_input_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_manifest("--project", "unit", "--calculation-readiness", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "groups",
        "manifest_items",
        "resolution_queues",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "missing_data_manifest_pass",
    }
    assert expected.issubset(read_json(out))


def test_every_source_missing_data_item_is_represented(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert {item["id"] for item in readiness_fixture()["missing_data_items"]} == {item["source_missing_data_id"] for item in artifact["manifest_items"]}


def test_every_manifest_item_assigned_to_exactly_one_resolution_queue(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    for item in artifact["manifest_items"]:
        assert len(queue_for_item(artifact, item["manifest_id"])) == 1


def test_summary_counts_are_internally_consistent(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    items = artifact["manifest_items"]
    queues = artifact["resolution_queues"]
    assert summary["missing_data_item_count"] == len(readiness_fixture()["missing_data_items"])
    assert summary["manifest_item_count"] == len(items)
    assert summary["group_count"] == len(artifact["groups"])
    assert summary["deterministic_rule_item_count"] == len(queues["deterministic_rule"])
    assert summary["datasheet_extraction_item_count"] == len(queues["datasheet_extraction"])
    assert summary["ai_rule_packet_item_count"] == len(queues["ai_rule_packet"])
    assert summary["human_review_item_count"] == len(queues["human_review"])
    assert summary["not_required_item_count"] == len(queues["not_required"])
    assert summary["high_priority_count"] == sum(1 for item in items if item["priority"] == "high")
    assert summary["medium_priority_count"] == sum(1 for item in items if item["priority"] == "medium")
    assert summary["low_priority_count"] == sum(1 for item in items if item["priority"] == "low")


def test_branch_current_unknown_groups_by_rail(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    group = [group for group in artifact["groups"] if group["group_id"] == "group_current_model_missing_v24p0"][0]
    assert group["group_type"] == "current_model_missing"
    assert len(group["item_ids"]) == 2


def test_current_model_missing_routes_to_datasheet_extraction(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_current_model_missing_component_u1", "current_model_missing", "component", "U1", ["copper_calculation"], recommended="datasheet_extraction")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "current_model_missing")
    assert item["resolution_path"] == "datasheet_extraction"


def test_relationship_direction_unknown_routes_to_ai_or_human_review(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_rel_unknown", "relationship_direction_unknown", "relationship", "rel_weak", ["current_allocation"], recommended="human_review")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "relationship_direction_unknown")
    assert item["resolution_path"] in {"ai_rule_packet", "human_review", "deterministic_rule"}


def test_power_path_direction_unknown_on_switched_rail_routes_high_priority(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_power_path", "power_path_direction_unknown", "branch", "br_sw", ["current_allocation"], recommended="human_review")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "power_path_direction_unknown")
    assert item["priority"] == "high"
    assert item["resolution_path"] == "human_review"


def test_ambiguous_pass_through_routes_to_human_or_ai_with_low_packet_size(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_jp1", "ambiguous_pass_through", "component", "JP1", ["current_allocation"], recommended="human_review")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "ambiguous_pass_through")
    assert item["resolution_path"] in {"human_review", "ai_rule_packet"}
    assert item["packet_hint"]["max_items_per_packet"] <= 5


def test_voltage_unknown_for_vcc_routes_with_voltage_resolution_packet_hint(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "voltage_unknown")
    assert item["resolution_path"] in {"ai_rule_packet", "deterministic_rule"}
    assert item["packet_hint"]["packet_type"] == "voltage_resolution"


def test_copper_thickness_missing_routes_deterministic_or_not_required(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_cu", "copper_thickness_missing", "branch", "br_v24", ["copper_calculation", "thermal_calculation"], recommended="deterministic_rule")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "copper_thickness_missing")
    assert item["resolution_path"] in {"deterministic_rule", "not_required"}


def test_source_sink_not_resolved_groups_by_rail(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    group = [group for group in artifact["groups"] if group["group_id"] == "group_source_sink_unresolved_v24p0"][0]
    assert group["affected_rails"] == ["V24P0"]


def test_component_role_unknown_groups_by_component(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_role_u9", "component_role_unknown", "component", "U9", ["current_allocation"], recommended="ai_rule_batch")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    group = read_json(out)["groups"][0]
    assert group["group_id"] == "group_component_role_unknown_u9"


def test_not_required_items_are_retained_not_dropped(tmp_path: Path) -> None:
    readiness = readiness_fixture([mdi("mdi_later_geom", "geometry_width_missing", "branch", "br_sig", ["thermal_calculation"], recommended="not_required", severity="info")])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert len(artifact["manifest_items"]) == 1
    assert artifact["manifest_items"][0]["resolution_path"] == "not_required"


def test_packet_hints_exist_for_every_item(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert all(item.get("packet_hint", {}).get("packet_type") for item in read_json(out)["manifest_items"])


def test_high_priority_assigned_for_current_allocation_blockers(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "source_sink_not_resolved")
    assert "current_allocation" in item["blocks"]
    assert item["priority"] == "high"


def test_medium_priority_assigned_for_copper_calculation_blockers(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "branch_current_unknown")
    assert "copper_calculation" in item["blocks"]
    assert item["priority"] == "medium"


def test_low_priority_assigned_for_later_only_blockers(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    item = item_by_category(read_json(out), "voltage_unknown")
    assert item["blocks"] == ["voltage_drop_calculation"]
    assert item["priority"] == "low"


def test_stable_ids_are_deterministic(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    ids = sorted(item["manifest_id"] for item in read_json(out)["manifest_items"])
    assert "mdi_manifest_branch_current_unknown_v24p0_mdi_branch_current_unknown_branch_br_v24" in ids
    assert ids == sorted(ids)


def test_duplicate_missing_data_items_deduplicate_correctly(tmp_path: Path) -> None:
    duplicate = mdi("mdi_dupe", "branch_current_unknown", "branch", "br_v24", ["copper_calculation"], recommended="datasheet_extraction")
    readiness = readiness_fixture([duplicate, dict(duplicate)])
    result, out = invoke(tmp_path, readiness)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["missing_data_item_count"] == 1
    assert artifact["summary"]["manifest_item_count"] == 1


def test_group_item_ids_reference_existing_manifest_items(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    item_ids = {item["manifest_id"] for item in artifact["manifest_items"]}
    assert all(item_id in item_ids for group in artifact["groups"] for item_id in group["item_ids"])


def test_resolution_queue_item_ids_reference_existing_manifest_items(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    item_ids = {item["manifest_id"] for item in artifact["manifest_items"]}
    assert all(item_id in item_ids for queue in artifact["resolution_queues"].values() for item_id in queue)


def test_malformed_input_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    out = tmp_path / "out.json"
    result = run_manifest("--project", "unit", "--calculation-readiness", str(bad), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    items = [
        mdi("mdi_branch_current_unknown_branch_br_v24", "branch_current_unknown", "branch", "br_v24", ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"], recommended="datasheet_extraction"),
        mdi("mdi_power_path", "power_path_direction_unknown", "branch", "br_sw", ["current_allocation"], recommended="human_review"),
        mdi("mdi_voltage_unknown_rail_vcc", "voltage_unknown", "rail", "VCC", ["voltage_drop_calculation"], recommended="deterministic_rule", severity="warning"),
    ]
    result, out = invoke(tmp_path, readiness_fixture(items))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["missing_data_manifest_pass"] is True
    assert artifact["manifest_items"]
    assert artifact["groups"]
