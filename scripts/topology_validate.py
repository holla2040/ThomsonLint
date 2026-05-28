#!/usr/bin/env python3
"""Validate ThomsonLint topology-map artifacts.

This validator checks deterministic topology-map artifacts produced by
topology_builder.py. It does not build topology, extract datasheets, map copper,
run thermal checks, modify workflow state, or create findings.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = Path("schemas/topology_map_schema.json")
HUMAN_REVIEW_UNRESOLVED_TYPES = {
    "power_net_no_source",
    "voltage_unknown",
    "sink_current_unknown",
    "missing_part_info",
    "pin_mapping_conflict",
    "pass_through_unresolved",
    "circular_propagation",
}
STRICT_UNRESOLVED_TYPES = {"power_net_no_source", "voltage_unknown", "sink_current_unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_jsonschema() -> Any:
    try:
        import jsonschema  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "jsonschema is required for topology validation. Install it with "
            "`python3 -m pip install jsonschema` or add it to the project environment."
        ) from exc
    return jsonschema


def format_path(path: list[Any] | tuple[Any, ...]) -> str:
    if not path:
        return "<root>"
    out = ""
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def check_row(name: str, errors: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    errors = errors or []
    warnings = warnings or []
    return {"check": name, "passed": not errors, "errors": errors, "warnings": warnings}


def count_duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def unresolved_types(topology: dict[str, Any]) -> set[str]:
    unresolved = topology.get("unresolved")
    if not isinstance(unresolved, list):
        return set()
    return {
        item.get("type")
        for item in unresolved
        if isinstance(item, dict) and isinstance(item.get("type"), str)
    }


def unresolved_for_net(topology: dict[str, Any], net_name: str, item_type: str) -> bool:
    unresolved = topology.get("unresolved")
    if not isinstance(unresolved, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("type") == item_type
        and item.get("net") == net_name
        for item in unresolved
    )


def model_ids(topology: dict[str, Any], key: str) -> set[str]:
    rows = topology.get(key)
    if not isinstance(rows, list):
        return set()
    return {
        row.get("model_id")
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("model_id"), str)
    }


def id_values(topology: dict[str, Any], key: str, id_key: str) -> list[str]:
    rows = topology.get(key)
    if not isinstance(rows, list):
        return []
    return [row.get(id_key) for row in rows if isinstance(row, dict) and isinstance(row.get(id_key), str)]


def target_suffix(target: Any, prefix: str) -> str | None:
    if not isinstance(target, str):
        return None
    marker = f"{prefix}:"
    if not target.startswith(marker):
        return None
    suffix = target[len(marker):]
    return suffix or None


def validate_schema(schema_path: Path, topology: Any) -> tuple[bool, list[str]]:
    jsonschema = load_jsonschema()
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        raise ValueError(f"topology schema must be a JSON object: {schema_path}")
    jsonschema.Draft7Validator.check_schema(schema)
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(topology), key=lambda err: list(err.path))
    return not errors, [f"{format_path(list(err.path))}: {err.message}" for err in errors]


def validate_references(topology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    net_names = set(id_values(topology, "nets", "net_name"))
    pin_refs = set(id_values(topology, "pins", "pin_ref"))
    branch_ids = set(id_values(topology, "branches", "branch_id"))
    current_ids = model_ids(topology, "current_models")
    voltage_ids = model_ids(topology, "voltage_models")

    for rail in topology.get("power_rails", []):
        if not isinstance(rail, dict):
            continue
        net_name = rail.get("net_name")
        current_ref = rail.get("current_model_ref")
        voltage_ref = rail.get("voltage_model_ref")
        if isinstance(current_ref, str) and current_ref not in current_ids:
            errors.append(f"power_rails[{net_name}].current_model_ref dangling: {current_ref}")
        if isinstance(voltage_ref, str) and voltage_ref not in voltage_ids:
            errors.append(f"power_rails[{net_name}].voltage_model_ref dangling: {voltage_ref}")

    for device in topology.get("devices", []):
        if not isinstance(device, dict):
            continue
        current_model = device.get("current_model")
        if isinstance(current_model, dict):
            model_id = current_model.get("model_id")
            if isinstance(model_id, str) and model_id not in current_ids:
                errors.append(f"devices[{device.get('refdes')}].current_model.model_id dangling: {model_id}")

    for row_key in ("pins", "source_nodes", "sink_nodes"):
        for row in topology.get(row_key, []):
            if not isinstance(row, dict):
                continue
            net_name = row.get("net_name")
            if isinstance(net_name, str) and net_name not in net_names:
                errors.append(f"{row_key}[{row.get('pin_ref') or row.get('node_id')}].net_name dangling: {net_name}")

    for sink in topology.get("sink_nodes", []):
        if not isinstance(sink, dict):
            continue
        current_ref = sink.get("current_model_ref")
        if isinstance(current_ref, str) and current_ref not in current_ids:
            errors.append(f"sink_nodes[{sink.get('node_id')}].current_model_ref dangling: {current_ref}")

    for branch in topology.get("branches", []):
        if not isinstance(branch, dict):
            continue
        branch_id = branch.get("branch_id")
        net_name = branch.get("net")
        source_ref = branch.get("source_ref")
        if isinstance(net_name, str) and net_name not in net_names:
            errors.append(f"branches[{branch_id}].net dangling: {net_name}")
        if isinstance(source_ref, str) and source_ref not in pin_refs:
            errors.append(f"branches[{branch_id}].source_ref dangling: {source_ref}")
        sink_refs = branch.get("sink_refs")
        if isinstance(sink_refs, list):
            for sink_ref in sink_refs:
                if isinstance(sink_ref, str) and sink_ref not in pin_refs:
                    errors.append(f"branches[{branch_id}].sink_refs dangling: {sink_ref}")

    for link in topology.get("copper_geometry_links", []):
        if not isinstance(link, dict):
            continue
        link_id = link.get("link_id")
        net_name = link.get("net")
        branch_id = link.get("branch_id")
        if isinstance(net_name, str) and net_name not in net_names:
            errors.append(f"copper_geometry_links[{link_id}].net dangling: {net_name}")
        if isinstance(branch_id, str) and branch_id not in branch_ids:
            errors.append(f"copper_geometry_links[{link_id}].branch_id dangling: {branch_id}")

    return errors


def validate_consistency(topology: dict[str, Any], *, strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    graph = topology.get("graph_summary") if isinstance(topology.get("graph_summary"), dict) else {}
    count_checks = [
        ("net_count", "nets"),
        ("device_count", "devices"),
        ("power_rail_count", "power_rails"),
        ("branch_count", "branches"),
        ("unresolved_count", "unresolved"),
    ]
    for summary_key, array_key in count_checks:
        rows = topology.get(array_key)
        expected = len(rows) if isinstance(rows, list) else 0
        actual = graph.get(summary_key)
        if actual != expected:
            errors.append(f"graph_summary.{summary_key}={actual} does not match len({array_key})={expected}")

    nets_by_name = {
        row.get("net_name"): row
        for row in topology.get("nets", [])
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }
    power_rail_names = {
        row.get("net_name")
        for row in topology.get("power_rails", [])
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }
    device_refdes = set(id_values(topology, "devices", "refdes"))
    current_ids = id_values(topology, "current_models", "model_id")
    voltage_ids = id_values(topology, "voltage_models", "model_id")
    branch_ids = id_values(topology, "branches", "branch_id")
    unresolved_ids = id_values(topology, "unresolved", "id")

    for duplicate in count_duplicates(current_ids):
        errors.append(f"duplicate current model_id: {duplicate}")
    for duplicate in count_duplicates(voltage_ids):
        errors.append(f"duplicate voltage model_id: {duplicate}")
    for duplicate in count_duplicates(branch_ids):
        errors.append(f"duplicate branch_id: {duplicate}")
    for duplicate in count_duplicates(unresolved_ids):
        message = f"duplicate unresolved id: {duplicate}"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    for rail in topology.get("power_rails", []):
        if not isinstance(rail, dict):
            continue
        net_name = rail.get("net_name")
        net = nets_by_name.get(net_name)
        if net is None:
            errors.append(f"power_rails[{net_name}].net_name missing from nets")
        elif net.get("net_type") != "power":
            errors.append(f"power_rails[{net_name}] references net classified as {net.get('net_type')}")

    for voltage_model in topology.get("voltage_models", []):
        if not isinstance(voltage_model, dict):
            continue
        net_name = target_suffix(voltage_model.get("target"), "net")
        if net_name is not None and net_name not in nets_by_name:
            errors.append(f"voltage_models[{voltage_model.get('model_id')}].target dangling net: {net_name}")

    for current_model in topology.get("current_models", []):
        if not isinstance(current_model, dict):
            continue
        rail_name = target_suffix(current_model.get("target"), "rail")
        if rail_name is not None and rail_name not in power_rail_names:
            errors.append(f"current_models[{current_model.get('model_id')}].target dangling rail: {rail_name}")

    for row_key in ("source_nodes", "sink_nodes"):
        for node in topology.get(row_key, []):
            if not isinstance(node, dict):
                continue
            refdes = node.get("refdes")
            if isinstance(refdes, str) and refdes not in device_refdes:
                errors.append(f"{row_key}[{node.get('node_id')}].refdes missing from devices: {refdes}")

    return errors, warnings


def validate_power_completeness(topology: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    current_models = topology.get("current_models") if isinstance(topology.get("current_models"), list) else []
    current_ids = {
        model.get("model_id")
        for model in current_models
        if isinstance(model, dict) and isinstance(model.get("model_id"), str)
    }
    current_by_id = {
        model.get("model_id"): model
        for model in current_models
        if isinstance(model, dict) and isinstance(model.get("model_id"), str)
    }
    voltage_models = topology.get("voltage_models") if isinstance(topology.get("voltage_models"), list) else []
    voltage_by_id = {
        model.get("model_id"): model
        for model in voltage_models
        if isinstance(model, dict) and isinstance(model.get("model_id"), str)
    }

    for rail in topology.get("power_rails", []):
        if not isinstance(rail, dict):
            continue
        net_name = rail.get("net_name")
        source_components = rail.get("source_components")
        if isinstance(source_components, list) and not source_components:
            if not (isinstance(net_name, str) and unresolved_for_net(topology, net_name, "power_net_no_source")):
                errors.append(f"power rail {net_name} has no source_components without power_net_no_source unresolved item")

        voltage_ref = rail.get("voltage_model_ref")
        voltage_model = voltage_by_id.get(voltage_ref)
        voltage_unknown = rail.get("voltage_source") == "unknown" or rail.get("nominal_voltage_v") is None
        if isinstance(voltage_model, dict) and voltage_model.get("nominal_voltage_v") is None:
            voltage_unknown = True
        rail_flags = rail.get("unresolved_flags") if isinstance(rail.get("unresolved_flags"), list) else []
        model_flags = voltage_model.get("unresolved_flags") if isinstance(voltage_model, dict) and isinstance(voltage_model.get("unresolved_flags"), list) else []
        has_voltage_marker = "voltage_unknown" in rail_flags or "voltage_unknown" in model_flags
        if voltage_unknown and not (has_voltage_marker or (isinstance(net_name, str) and unresolved_for_net(topology, net_name, "voltage_unknown"))):
            errors.append(f"power rail {net_name} has unknown voltage without voltage_unknown marker")

        sink_components = rail.get("sink_components")
        current_ref = rail.get("current_model_ref")
        rail_model = current_by_id.get(current_ref)
        rail_current_unresolved = not isinstance(rail_model, dict) or rail_model.get("basis") == "unresolved"
        if isinstance(sink_components, list) and sink_components and rail_current_unresolved:
            has_sink_unresolved = isinstance(net_name, str) and unresolved_for_net(topology, net_name, "sink_current_unknown")
            if not has_sink_unresolved:
                errors.append(f"power rail {net_name} has sink_components with unresolved current but no sink_current_unknown item")

    for model in current_models:
        if not isinstance(model, dict):
            continue
        flags = model.get("unresolved_flags")
        if model.get("basis") == "unresolved" and not flags:
            errors.append(f"current_models[{model.get('model_id')}] basis unresolved without unresolved_flags")
        if model.get("nominal_current_a") == 0:
            warnings.append(f"current_models[{model.get('model_id')}].nominal_current_a is zero; verify this is not missing current")

    for sink in topology.get("sink_nodes", []):
        if not isinstance(sink, dict):
            continue
        current_ref = sink.get("current_model_ref")
        if isinstance(current_ref, str) and current_ref not in current_ids:
            errors.append(f"sink_nodes[{sink.get('node_id')}] current_model_ref does not exist: {current_ref}")

    return errors, warnings


def collect_human_review(topology: dict[str, Any]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    unresolved = topology.get("unresolved")
    if isinstance(unresolved, list):
        for item in unresolved:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in HUMAN_REVIEW_UNRESOLVED_TYPES or item.get("human_review_needed") is True:
                review.append({
                    "type": item_type or "unknown",
                    "id": item.get("id"),
                    "net": item.get("net"),
                    "affected_refdes": item.get("affected_refdes", []),
                    "notes": item.get("notes"),
                })
    validation = topology.get("validation")
    if isinstance(validation, dict) and validation.get("human_review_needed") is True:
        review.append({
            "type": "topology_validation_human_review_needed",
            "id": "topology.validation.human_review_needed",
            "net": None,
            "affected_refdes": [],
            "notes": "Input topology map validation.human_review_needed is true.",
        })
    return review


def build_summary(topology: dict[str, Any], schema_error_count: int, consistency_error_count: int, warning_count: int, human_review_count: int) -> dict[str, int]:
    def count(key: str) -> int:
        value = topology.get(key)
        return len(value) if isinstance(value, list) else 0

    return {
        "net_count": count("nets"),
        "device_count": count("devices"),
        "pin_count": count("pins"),
        "power_rail_count": count("power_rails"),
        "source_node_count": count("source_nodes"),
        "sink_node_count": count("sink_nodes"),
        "current_model_count": count("current_models"),
        "voltage_model_count": count("voltage_models"),
        "unresolved_count": count("unresolved"),
        "schema_error_count": schema_error_count,
        "consistency_error_count": consistency_error_count,
        "warning_count": warning_count,
        "human_review_item_count": human_review_count,
    }


def validate_topology(project: str, topology_path: Path, schema_path: Path, *, strict: bool) -> dict[str, Any]:
    topology = load_json(topology_path)
    if not isinstance(topology, dict):
        raise ValueError(f"topology artifact must be a JSON object: {topology_path}")

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    schema_passed, schema_errors = validate_schema(schema_path, topology)
    checks.append(check_row("schema_validation", schema_errors))
    if schema_errors:
        errors.extend(f"schema_validation: {error}" for error in schema_errors)

    reference_errors = validate_references(topology) if schema_passed else []
    checks.append(check_row("reference_integrity", reference_errors))
    errors.extend(f"reference_integrity: {error}" for error in reference_errors)

    consistency_errors, consistency_warnings = validate_consistency(topology, strict=strict) if schema_passed else ([], [])
    checks.append(check_row("topology_consistency", consistency_errors, consistency_warnings))
    errors.extend(f"topology_consistency: {error}" for error in consistency_errors)
    warnings.extend(f"topology_consistency: {warning}" for warning in consistency_warnings)

    power_errors, power_warnings = validate_power_completeness(topology) if schema_passed else ([], [])
    checks.append(check_row("power_topology_completeness", power_errors, power_warnings))
    errors.extend(f"power_topology_completeness: {error}" for error in power_errors)
    warnings.extend(f"power_topology_completeness: {warning}" for warning in power_warnings)

    human_review_needed = collect_human_review(topology)
    checks.append(check_row("human_review", warnings=[f"{len(human_review_needed)} human review item(s)"]))

    strict_unresolved = unresolved_types(topology).intersection(STRICT_UNRESOLVED_TYPES)
    if strict and strict_unresolved:
        for item_type in sorted(strict_unresolved):
            errors.append(f"strict_mode: unresolved topology item present: {item_type}")

    artifact_validation_pass = schema_passed
    consistency_error_count = len(reference_errors) + len(consistency_errors) + len(power_errors)
    topology_consistency_pass = consistency_error_count == 0
    unresolved_items_present = bool(topology.get("unresolved"))
    phase_gate_passed = artifact_validation_pass and topology_consistency_pass and not (strict and strict_unresolved)
    overall_pass = phase_gate_passed

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "topology": str(topology_path),
            "schema": str(schema_path),
        },
        "summary": build_summary(
            topology,
            schema_error_count=len(schema_errors),
            consistency_error_count=consistency_error_count,
            warning_count=len(warnings),
            human_review_count=len(human_review_needed),
        ),
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "human_review_needed": human_review_needed,
        "execution_pass": True,
        "artifact_validation_pass": artifact_validation_pass,
        "topology_consistency_pass": topology_consistency_pass,
        "unresolved_items_present": unresolved_items_present,
        "phase_gate_passed": phase_gate_passed,
        "overall_pass": overall_pass,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a ThomsonLint topology-map artifact.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    topology_path = Path(args.topology or default_path("exports/{project}-topology-map.json", project))
    schema_path = Path(args.schema)
    out_path = Path(args.out or default_path("exports/{project}-topology-validation.json", project))

    try:
        if not topology_path.exists():
            raise FileNotFoundError(f"missing topology map: {topology_path}")
        if not schema_path.exists():
            raise FileNotFoundError(f"missing topology schema: {schema_path}")
        artifact = validate_topology(project, topology_path, schema_path, strict=args.strict)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology validation: "
        f"artifact_pass={artifact['artifact_validation_pass']} "
        f"consistency_pass={artifact['topology_consistency_pass']} "
        f"unresolved={summary['unresolved_count']} "
        f"errors={len(artifact['errors'])} warnings={len(artifact['warnings'])} "
        f"out={out_path}"
    )
    return 0 if artifact["phase_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
