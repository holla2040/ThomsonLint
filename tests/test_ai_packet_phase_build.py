from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_packet_phase_build.py"
DOC = ROOT / "docs" / "ai_packet_phase_driver.md"


def run_build(*args: str) -> subprocess.CompletedProcess[str]:
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


def mdi(
    item_id: str,
    category: str,
    target_type: str,
    target_id: str,
    *,
    refdes: str | None = None,
    mpn: str | None = None,
    affected_components: list[str] | None = None,
    affected_rails: list[str] | None = None,
    affected_branches: list[str] | None = None,
    blocks: list[str] | None = None,
    recommended: str = "datasheet_extraction",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "manifest_id": item_id,
        "source_missing_data_id": f"source_{item_id}",
        "category": category,
        "target_type": target_type,
        "target_id": target_id,
        "normalized_target": target_id,
        "affected_components": affected_components if affected_components is not None else ([refdes] if refdes else []),
        "affected_rails": affected_rails or [],
        "affected_branches": affected_branches or [],
        "blocks": blocks or ["copper_calculation"],
        "priority": "medium",
        "resolution_path": recommended,
        "group_id": f"group_{category}_{target_id}",
        "evidence": [],
        "notes": f"{category} for {target_id}",
    }
    if refdes:
        row["refdes"] = refdes
    if mpn:
        row["mpn"] = mpn
    return row


def manifest_fixture(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "manifest_items": items
        if items is not None
        else [
            mdi("mdi_u2_current", "branch_current_unknown", "component", "U2", refdes="U2", affected_rails=["V3P3"]),
            mdi("mdi_u1_role", "component_role_unknown", "component", "U1", refdes="U1", blocks=["current_allocation"], recommended="ai_rule_packet"),
            mdi("mdi_f1_rating", "rating_missing", "component", "F1", refdes="F1", blocks=["fuse_margin"]),
        ],
        "groups": [],
        "warnings": [],
        "errors": [],
    }


def bom_fixture() -> dict[str, Any]:
    return {
        "project": "TestProject",
        "components": [
            {"refdes": "U1", "mpn": "REG-123"},
            {"refdes": "U2", "mpn": "MCU-456"},
            {"refdes": "F1", "mpn": "FUSE-789"},
            {"refdes": "J1", "mpn": "CONN-001"},
        ],
    }


def invoke(
    tmp_path: Path,
    items: list[dict[str, Any]] | None = None,
    *,
    max_items_per_packet: int | None = None,
    with_bom: bool = True,
    with_datasheet_manifest: bool = True,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    manifest = write_json(tmp_path / "manifest.json", manifest_fixture(items))
    out_dir = tmp_path / "exports" / "TestProject" / "ai_packets" / "phase_12"
    args = [
        "--project",
        "TestProject",
        "--missing-data-manifest",
        str(manifest),
        "--out-dir",
        str(out_dir),
        "--phase-id",
        "12",
        "--phase-name",
        "AI Data Completion",
    ]
    if max_items_per_packet is not None:
        args.extend(["--max-items-per-packet", str(max_items_per_packet)])
    if with_bom:
        args.extend(["--bom", str(write_json(tmp_path / "bom.json", bom_fixture()))])
    if with_datasheet_manifest:
        args.extend(["--datasheet-manifest", str(write_json(tmp_path / "datasheets.json", {"datasheets": []}))])
    return run_build(*args), out_dir


def queue(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "packet_queue.json")


def phase_status(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "phase_status.json")


def packets(out_dir: Path) -> list[dict[str, Any]]:
    return queue(out_dir)["packets"]


def only_packet(out_dir: Path) -> dict[str, Any]:
    rows = packets(out_dir)
    assert len(rows) == 1
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


def test_missing_manifest_exits_2(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    result = run_build("--project", "TestProject", "--missing-data-manifest", str(tmp_path / "missing.json"), "--out-dir", str(out_dir))
    assert result.returncode == 2
    assert not out_dir.exists()


def test_malformed_manifest_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = run_build("--project", "TestProject", "--missing-data-manifest", str(bad), "--out-dir", str(out_dir))
    assert result.returncode == 2
    assert not out_dir.exists()


def test_output_directory_shape_created(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (out_dir / "packet_queue.json").exists()
    assert (out_dir / "phase_status.json").exists()
    assert (out_dir / "phase_12_summary.json").exists()
    assert (out_dir / "packets").is_dir()


def test_packet_queue_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "phase_id", "phase_name", "schema_version", "generated_at_utc", "source_artifacts", "packets", "summary", "errors", "warnings"}
    assert expected.issubset(queue(out_dir))


def test_phase_status_has_expected_shape(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "project",
        "phase_id",
        "phase_name",
        "status",
        "packet_count",
        "pending_count",
        "accepted_count",
        "rejected_count",
        "human_review_count",
        "retry_count",
        "source_artifacts",
        "errors",
        "warnings",
    }
    assert expected.issubset(phase_status(out_dir))


def test_packet_ids_are_unique(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    ids = [packet["packet_id"] for packet in packets(out_dir)]
    assert len(ids) == len(set(ids))


def test_packet_ids_are_deterministic(tmp_path: Path) -> None:
    result1, out1 = invoke(tmp_path / "a")
    result2, out2 = invoke(tmp_path / "b")
    assert result1.returncode == 0, result1.stderr + result1.stdout
    assert result2.returncode == 0, result2.stderr + result2.stdout
    assert [packet["packet_id"] for packet in packets(out1)] == [packet["packet_id"] for packet in packets(out2)]


def test_summary_counts_match_packet_files(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = queue(out_dir)
    packet_dirs = [path for path in (out_dir / "packets").iterdir() if path.is_dir()]
    assert artifact["summary"]["packet_count"] == len(artifact["packets"]) == len(packet_dirs)
    assert phase_status(out_dir)["packet_count"] == len(packet_dirs)


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in out_dir.rglob("*.json"):
        for value in all_values(read_json(path)):
            assert not (isinstance(value, float) and not math.isfinite(value))


def test_branch_current_unknown_routes_to_stage_12b_current_extraction(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")])
    assert result.returncode == 0, result.stderr + result.stdout
    packet = only_packet(out_dir)
    assert packet["stage_id"] == "12B"
    assert packet["packet_type"] == "datasheet_current_extraction"


def test_current_model_missing_routes_to_stage_12b(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_model", "current_model_missing", "component", "U2", refdes="U2")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_packet(out_dir)["stage_id"] == "12B"


def test_rating_missing_routes_to_stage_12c_rating_extraction(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_rating", "rating_missing", "component", "F1", refdes="F1", blocks=["fuse_margin"])])
    assert result.returncode == 0, result.stderr + result.stdout
    packet = only_packet(out_dir)
    assert packet["stage_id"] == "12C"
    assert packet["packet_type"] == "datasheet_rating_extraction"


def test_component_role_unknown_routes_to_stage_12a_role_pin_extraction(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_role", "component_role_unknown", "component", "U1", refdes="U1", blocks=["current_allocation"])])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_packet(out_dir)["stage_id"] == "12A"


def test_relationship_direction_unknown_routes_to_stage_12a(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_rel", "relationship_direction_unknown", "relationship", "rel1", affected_components=["U1"])])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_packet(out_dir)["stage_id"] == "12A"


def test_geometry_missing_does_not_route_to_datasheet_ai_by_default(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_cu", "copper_thickness_missing", "branch", "br1", affected_branches=["br1"])])
    assert result.returncode == 0, result.stderr + result.stdout
    assert queue(out_dir)["packets"] == []
    assert queue(out_dir)["summary"]["skipped_item_count"] == 1


def test_unknown_category_routes_to_human_review_or_skipped_with_warning(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_unknown", "future_unknown_category", "component", "U9", refdes="U9")])
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = queue(out_dir)
    assert artifact["warnings"]
    assert only_packet(out_dir)["human_review_needed"] is True


def test_each_packet_has_request_context_prompt_and_status_files(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for packet in packets(out_dir):
        packet_dir = out_dir / "packets" / packet["packet_id"]
        assert (packet_dir / "request.json").exists()
        assert (packet_dir / "context.json").exists()
        assert (packet_dir / "prompt.md").exists()
        assert (packet_dir / "status.json").exists()


def test_prompt_contains_no_guessing_guardrail(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")])
    assert result.returncode == 0, result.stderr + result.stdout
    prompt = (out_dir / only_packet(out_dir)["prompt_path"]).read_text(encoding="utf-8")
    assert "Do not guess." in prompt
    assert "return unknown" in prompt


def test_prompt_contains_evidence_requirement(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")])
    assert result.returncode == 0, result.stderr + result.stdout
    prompt = (out_dir / only_packet(out_dir)["prompt_path"]).read_text(encoding="utf-8")
    assert "Every extracted numeric value must include unit and evidence" in prompt


def test_prompt_forbids_findings_pass_fail_and_compliance(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")])
    assert result.returncode == 0, result.stderr + result.stdout
    prompt = (out_dir / only_packet(out_dir)["prompt_path"]).read_text(encoding="utf-8")
    assert "Do not produce findings" in prompt
    assert "Do not produce pass/fail" in prompt
    assert "Do not produce compliance judgments" in prompt


def test_context_is_bounded_to_relevant_missing_items(tmp_path: Path) -> None:
    items = [
        mdi("mdi_u2_1", "branch_current_unknown", "component", "U2", refdes="U2"),
        mdi("mdi_u2_2", "current_model_missing", "component", "U2", refdes="U2"),
        mdi("mdi_u3", "current_model_missing", "component", "U3", refdes="U3"),
    ]
    result, out_dir = invoke(tmp_path, items)
    assert result.returncode == 0, result.stderr + result.stdout
    for packet in packets(out_dir):
        context = read_json(out_dir / packet["context_path"])
        assert {item["manifest_id"] for item in context["missing_data_items"]} == set(packet["missing_data_item_ids"])


def test_missing_optional_datasheet_manifest_is_warning_not_failure(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")], with_datasheet_manifest=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert queue(out_dir)["summary"]["missing_datasheet_context_count"] == 1
    assert queue(out_dir)["warnings"]


def test_missing_optional_bom_is_warning_not_failure(tmp_path: Path) -> None:
    result, out_dir = invoke(tmp_path, [mdi("mdi_current", "branch_current_unknown", "component", "U2", refdes="U2")], with_bom=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert queue(out_dir)["summary"]["missing_bom_context_count"] == 1
    assert queue(out_dir)["warnings"]


def test_packets_group_by_refdes_or_target_not_entire_board(tmp_path: Path) -> None:
    items = [
        mdi("mdi_u2", "branch_current_unknown", "component", "U2", refdes="U2"),
        mdi("mdi_u3", "branch_current_unknown", "component", "U3", refdes="U3"),
    ]
    result, out_dir = invoke(tmp_path, items)
    assert result.returncode == 0, result.stderr + result.stdout
    assert {packet["target_refdes"] for packet in packets(out_dir)} == {"U2", "U3"}


def test_max_items_per_packet_is_respected(tmp_path: Path) -> None:
    items = [mdi(f"mdi_u2_{idx}", "branch_current_unknown", "component", "U2", refdes="U2") for idx in range(5)]
    result, out_dir = invoke(tmp_path, items, max_items_per_packet=2)
    assert result.returncode == 0, result.stderr + result.stdout
    assert all(len(packet["missing_data_item_ids"]) <= 2 for packet in packets(out_dir))
    assert len(packets(out_dir)) == 3


def test_high_risk_items_are_not_grouped_into_large_packets(tmp_path: Path) -> None:
    items = [mdi(f"mdi_f1_{idx}", "rating_missing", "component", "F1", refdes="F1", blocks=["fuse_margin"]) for idx in range(3)]
    result, out_dir = invoke(tmp_path, items, max_items_per_packet=5)
    assert result.returncode == 0, result.stderr + result.stdout
    assert all(len(packet["missing_data_item_ids"]) == 1 for packet in packets(out_dir))


def test_docs_describe_phase_stage_packet_model() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "Phase -> Stage -> Packet -> Item" in text


def test_docs_state_ai_does_not_mutate_core_artifacts() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "does not mutate core topology artifacts" in text


def test_docs_state_datasheets_are_primary_evidence_for_component_facts() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "Datasheets are the primary evidence source for component facts" in text
