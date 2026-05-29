from __future__ import annotations

import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
INPUT_SCHEMA_PATH = ROOT / "schemas" / "calculation_input_schema.json"
RESULT_SCHEMA_PATH = ROOT / "schemas" / "calculation_result_schema.json"
EXAMPLES_DIR = ROOT / "examples" / "calculation_examples"


CURRENT_DEPENDENT_BLOCKED = {
    "voltage_drop_input_blocked_missing_current.json",
    "voltage_drop_result_blocked_missing_current.json",
    "current_density_result_blocked_missing_current.json",
    "via_current_density_result_blocked_missing_current.json",
    "regulator_load_margin_result_blocked_missing_load_current.json"
}
RATING_DEPENDENT_BLOCKED = {
    "fuse_margin_result_blocked_missing_rating.json": "fuse_rated_current_a",
    "connector_pin_current_margin_result_blocked_missing_rating.json": "connector_pin_current_rating_a"
}
SOURCE_SINK_EXAMPLE = EXAMPLES_DIR / "current_allocation_result_blocked_source_sink_not_resolved.json"
COPPER_THICKNESS_EXAMPLE = EXAMPLES_DIR / "trace_cross_section_result_blocked_missing_copper_thickness.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def example_paths() -> list[Path]:
    return sorted(EXAMPLES_DIR.glob("*.json"))


def schema_for_example(path: Path) -> dict:
    if "_input_" in path.name:
        return load_json(INPUT_SCHEMA_PATH)
    return load_json(RESULT_SCHEMA_PATH)


def test_loads_every_json_schema() -> None:
    input_schema = load_json(INPUT_SCHEMA_PATH)
    result_schema = load_json(RESULT_SCHEMA_PATH)

    jsonschema.Draft7Validator.check_schema(input_schema)
    jsonschema.Draft7Validator.check_schema(result_schema)


def test_loads_every_example_json() -> None:
    paths = example_paths()

    assert len(paths) >= 11
    for path in paths:
        data = load_json(path)
        assert isinstance(data, dict), path.name
        assert data["schema_version"] == "1.0"


def test_every_example_validates_against_appropriate_schema() -> None:
    for path in example_paths():
        schema = schema_for_example(path)
        jsonschema.validate(instance=load_json(path), schema=schema)


def test_blocked_examples_include_missing_inputs() -> None:
    for path in example_paths():
        data = load_json(path)
        is_blocked_result = data.get("status") == "blocked"
        is_blocked_input = "_blocked_" in path.name and "_input_" in path.name
        if is_blocked_result or is_blocked_input:
            assert data.get("missing_inputs"), path.name
            assert data.get("blocked_by_manifest_items"), path.name


def test_current_dependent_blocked_examples_include_missing_current_field() -> None:
    for filename in CURRENT_DEPENDENT_BLOCKED:
        data = load_json(EXAMPLES_DIR / filename)
        fields = {item["field"] for item in data["missing_inputs"]}
        assert "branch_current_a" in fields or "allocated_load_current_a" in fields


def test_rating_dependent_blocked_examples_include_missing_rating_field() -> None:
    for filename, expected_field in RATING_DEPENDENT_BLOCKED.items():
        data = load_json(EXAMPLES_DIR / filename)
        fields = {item["field"] for item in data["missing_inputs"]}
        assert expected_field in fields


def test_blocked_results_are_valid_first_class_results() -> None:
    schema = load_json(RESULT_SCHEMA_PATH)
    blocked_paths = [path for path in example_paths() if load_json(path).get("status") == "blocked"]

    assert blocked_paths
    for path in blocked_paths:
        data = load_json(path)
        jsonschema.validate(instance=data, schema=schema)
        assert data["status"] == "blocked"
        assert data["missing_inputs"]
        assert data["result"]


def test_examples_do_not_encode_findings_or_pass_fail_judgments() -> None:
    forbidden_keys = {"finding_id", "issue_id", "pass", "fail", "compliance_pass", "compliance_fail"}
    for path in example_paths():
        raw = path.read_text(encoding="utf-8").lower()
        data = load_json(path)
        assert not forbidden_keys.intersection(data.keys()), path.name
        assert "finding" not in raw, path.name
        assert "compliance_pass" not in raw, path.name
        assert "compliance_fail" not in raw, path.name


def test_unknown_current_is_missing_not_zero() -> None:
    for filename in CURRENT_DEPENDENT_BLOCKED:
        data = load_json(EXAMPLES_DIR / filename)
        raw = json.dumps(data).lower()
        assert "zero current" not in raw
        assert any(item["field"] in {"branch_current_a", "allocated_load_current_a"} for item in data["missing_inputs"])


def test_blocked_examples_can_carry_missing_data_group_ids() -> None:
    for path in (SOURCE_SINK_EXAMPLE, COPPER_THICKNESS_EXAMPLE):
        data = load_json(path)
        assert data["status"] == "blocked"
        assert data["missing_data_group_ids"]
        assert all(isinstance(item, str) for item in data["missing_data_group_ids"])


def test_blocked_examples_can_carry_resolution_path_or_queue() -> None:
    for path in (SOURCE_SINK_EXAMPLE, COPPER_THICKNESS_EXAMPLE):
        data = load_json(path)
        assert isinstance(data["resolution_path"], str)
        assert isinstance(data["resolution_queue"], str)
        assert data["resolution_path"] == data["resolution_queue"]


def test_source_sink_not_resolved_example_blocks_current_allocation() -> None:
    data = load_json(SOURCE_SINK_EXAMPLE)

    assert "source_sink_not_resolved" in data["blocked_by_categories"]
    assert "current_allocation" in data["blocked_by_calculations"]
    assert "calculation_readiness" in data["blocked_by_calculations"]
    assert any("current_allocation" in item["required_for"] for item in data["missing_inputs"])


def test_copper_thickness_missing_example_blocks_trace_cross_section_or_resistance() -> None:
    data = load_json(COPPER_THICKNESS_EXAMPLE)

    assert "copper_thickness_missing" in data["blocked_by_categories"]
    assert {"trace_cross_section", "trace_resistance"}.intersection(data["blocked_by_calculations"])
    assert any(item["field"] == "copper_thickness" for item in data["missing_inputs"])
