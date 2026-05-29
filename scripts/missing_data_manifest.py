#!/usr/bin/env python3
"""Build a deterministic missing data manifest from readiness inventory.

PR 16 scope only: organize PR 15 missing-data inventory into grouped resolution
work queues. This script does not resolve missing data, infer or allocate
current, calculate electrical/thermal values, create findings, call AI, create
AI prompts, or mutate prior artifacts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
QUEUE_NAMES = ["deterministic_rule", "datasheet_extraction", "ai_rule_packet", "human_review", "not_required"]
CURRENT_MODEL_CATEGORIES = {"branch_current_unknown", "current_model_missing"}
RELATIONSHIP_CATEGORIES = {"relationship_direction_unknown", "power_path_direction_unknown", "ambiguous_pass_through"}
GEOMETRY_CATEGORIES = {"copper_thickness_missing", "geometry_width_missing", "geometry_area_missing", "geometry_length_missing", "layer_unknown"}
SOURCE_SINK_CATEGORIES = {"source_sink_not_resolved", "rail_source_unknown", "rail_sink_unknown", "branch_source_unknown", "branch_sink_unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_optional_json(path: Path | None, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None:
        return None, []
    if not path.exists():
        return None, [f"optional {label} input missing: {path}"]
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return data, []


def evidence(item_type: str, source: str, field: str, value: Any, reason: str) -> dict[str, Any]:
    return {"type": item_type, "source": source, "field": field, "value": value, "reason": reason}


def branch_index(calculation_readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["branch_id"]: row
        for row in as_list(calculation_readiness.get("branch_readiness"))
        if isinstance(row, dict) and isinstance(row.get("branch_id"), str)
    }


def rail_index(calculation_readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["rail"]: row
        for row in as_list(calculation_readiness.get("rail_readiness"))
        if isinstance(row, dict) and isinstance(row.get("rail"), str)
    }


def component_refs_from_branch(branch: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_candidates", "sink_candidates", "pass_through_candidates"):
        for row in as_list(branch.get(key)):
            if isinstance(row, dict) and isinstance(row.get("refdes"), str) and row["refdes"] not in refs:
                refs.append(row["refdes"])
    return sorted(refs)


def affected_context(item: dict[str, Any], branches: dict[str, dict[str, Any]], rails: dict[str, dict[str, Any]]) -> dict[str, list[str] | str]:
    target_type = str(item.get("target_type") or "")
    target_id = str(item.get("target_id") or "")
    affected_rails: list[str] = []
    affected_branches: list[str] = []
    affected_components: list[str] = []

    if target_type == "branch" and target_id in branches:
        branch = branches[target_id]
        affected_branches.append(target_id)
        rail_name = branch.get("rail_name")
        if isinstance(rail_name, str):
            affected_rails.append(rail_name)
        affected_components.extend(component_refs_from_branch(branch))
    elif target_type in {"rail", "net"}:
        affected_rails.append(target_id)
        rail = rails.get(target_id)
        if isinstance(rail, dict):
            affected_branches.extend([str(value) for value in as_list(rail.get("branch_ids"))])
    elif target_type == "component":
        affected_components.append(target_id)
    elif target_type == "relationship":
        for branch in branches.values():
            for rel in as_list(branch.get("rail_relationships")):
                if isinstance(rel, dict) and rel.get("relationship_id") == target_id:
                    branch_id = branch.get("branch_id")
                    rail_name = branch.get("rail_name")
                    if isinstance(branch_id, str) and branch_id not in affected_branches:
                        affected_branches.append(branch_id)
                    if isinstance(rail_name, str) and rail_name not in affected_rails:
                        affected_rails.append(rail_name)
                    through = rel.get("through_component")
                    if isinstance(through, str) and through not in affected_components:
                        affected_components.append(through)

    if target_id in rails and target_id not in affected_rails:
        affected_rails.append(target_id)
        rail = rails[target_id]
        if isinstance(rail, dict):
            affected_branches.extend([str(value) for value in as_list(rail.get("branch_ids"))])

    for value in as_list(item.get("evidence")):
        if not isinstance(value, dict):
            continue
        raw = value.get("value")
        if isinstance(raw, str) and raw in rails and raw not in affected_rails:
            affected_rails.append(raw)

    normalized = affected_rails[0] if affected_rails else affected_components[0] if affected_components else target_id
    return {
        "normalized_target": normalized,
        "affected_rails": sorted(set(affected_rails)),
        "affected_branches": sorted(set(affected_branches)),
        "affected_components": sorted(set(affected_components)),
    }


def resolution_path(item: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    category = str(item.get("category") or "")
    blocks = set(str(block) for block in as_list(item.get("blocks")))
    recommended = str(item.get("recommended_resolution") or "")
    target_id = str(item.get("target_id") or "")
    rails = set(context.get("affected_rails", []))

    if recommended == "not_required" or not blocks:
        return "not_required", "item is explicitly not required for the next planned stage"
    if category in CURRENT_MODEL_CATEGORIES:
        return "datasheet_extraction", "current model data requires datasheet or explicit load-model evidence"
    if category == "regulator_input_output_unknown":
        return "datasheet_extraction", "regulator input/output pin functions require datasheet-backed mapping"
    if category == "voltage_unknown":
        if target_id.upper() in {"VCC", "VDD", "VSYS", "VBAT"} or rails.intersection({"VCC", "VDD", "VSYS", "VBAT"}):
            return "ai_rule_packet", "ambiguous rail name needs bounded semantic voltage-resolution work"
        return "deterministic_rule", "voltage may be resolvable from existing rail relationship context"
    if category in GEOMETRY_CATEGORIES:
        if "current_allocation" not in blocks and blocks.issubset({"thermal_calculation", "voltage_drop_calculation"}):
            return "not_required", "geometry detail is retained but not required for the next current-allocation stage"
        return "deterministic_rule", "geometry or stackup attachment can be improved deterministically from existing artifacts"
    if category == "component_role_unknown":
        return "ai_rule_packet", "component role likely needs bounded semantic classification over local artifacts"
    if category == "ambiguous_pass_through":
        return "human_review", "ambiguous rail bridging can require engineering judgement before assuming connectivity"
    if category == "power_path_direction_unknown":
        return "human_review", "power path direction ambiguity can affect hardware safety"
    if category == "relationship_direction_unknown":
        if any("_SW" in rail.upper() or "_OUT" in rail.upper() for rail in rails) or "_sw" in target_id.lower():
            return "deterministic_rule", "rail naming suggests a possible deterministic direction rule improvement"
        return "ai_rule_packet", "relationship direction needs bounded graph/context reasoning"
    if category in SOURCE_SINK_CATEGORIES:
        return "ai_rule_packet", "source/sink ordering should be resolved from bounded topology graph context"
    if category == "human_review_needed":
        return "human_review", "source item explicitly requests human review"
    if recommended in QUEUE_NAMES:
        return recommended, "source item recommendation is preserved"
    if "current_allocation" in blocks:
        return "human_review", "current-allocation blocker lacks a deterministic resolution route"
    return "not_required", "item is retained for later stages but does not block the next stage"


def priority_for_item(item: dict[str, Any], path: str) -> str:
    category = str(item.get("category") or "")
    blocks = set(str(block) for block in as_list(item.get("blocks")))
    if path == "not_required":
        return "low"
    if "current_allocation" in blocks or category in {"power_path_direction_unknown", "ambiguous_pass_through", "component_role_unknown"}:
        return "high"
    if "copper_calculation" in blocks or category in CURRENT_MODEL_CATEGORIES or category in GEOMETRY_CATEGORIES:
        return "medium"
    return "low"


def packet_hint(category: str, path: str) -> dict[str, Any]:
    if path == "not_required":
        return {
            "packet_type": "not_applicable",
            "max_items_per_packet": 10,
            "suggested_stage": "deterministic",
            "requires_artifacts": [],
        }
    if category in CURRENT_MODEL_CATEGORIES:
        return {
            "packet_type": "current_model_completion",
            "max_items_per_packet": 5,
            "suggested_stage": "datasheet",
            "requires_artifacts": ["role_resolution", "component_datasheets", "part_info_index"],
        }
    if category in RELATIONSHIP_CATEGORIES or category in SOURCE_SINK_CATEGORIES:
        return {
            "packet_type": "relationship_resolution",
            "max_items_per_packet": 5,
            "suggested_stage": "ai_assisted" if path == "ai_rule_packet" else "human_review" if path == "human_review" else "deterministic",
            "requires_artifacts": ["rail_relationships", "branch_topology_enriched", "role_resolution"],
        }
    if category == "voltage_unknown":
        return {
            "packet_type": "voltage_resolution",
            "max_items_per_packet": 10,
            "suggested_stage": "ai_assisted" if path == "ai_rule_packet" else "deterministic",
            "requires_artifacts": ["rail_relationships", "role_resolution"],
        }
    if category in GEOMETRY_CATEGORIES:
        return {
            "packet_type": "geometry_completion",
            "max_items_per_packet": 10,
            "suggested_stage": "deterministic",
            "requires_artifacts": ["geometry_review", "stackup"],
        }
    if category == "component_role_unknown":
        return {
            "packet_type": "component_role_resolution",
            "max_items_per_packet": 10,
            "suggested_stage": "ai_assisted",
            "requires_artifacts": ["role_resolution", "schematic"],
        }
    return {
        "packet_type": "relationship_resolution",
        "max_items_per_packet": 10,
        "suggested_stage": "human_review" if path == "human_review" else "deterministic",
        "requires_artifacts": ["calculation_readiness"],
    }


def group_type_for_category(category: str, path: str) -> str:
    if path == "not_required":
        return "not_required"
    if category in CURRENT_MODEL_CATEGORIES:
        return "current_model_missing"
    if category in RELATIONSHIP_CATEGORIES:
        return "rail_relationship_ambiguity"
    if category == "voltage_unknown":
        return "voltage_unknown"
    if category in GEOMETRY_CATEGORIES:
        return "geometry_missing"
    if category in SOURCE_SINK_CATEGORIES:
        return "source_sink_unresolved"
    if category == "component_role_unknown":
        return "component_role_unknown"
    return "human_review"


def group_key_for_item(item: dict[str, Any], context: dict[str, Any], path: str) -> tuple[str, str]:
    category = str(item.get("category") or "unknown")
    group_type = group_type_for_category(category, path)
    rails = context.get("affected_rails", [])
    components = context.get("affected_components", [])
    normalized = str(context.get("normalized_target") or item.get("target_id") or "unknown")

    if group_type == "current_model_missing":
        return group_type, rails[0] if rails else normalized
    if group_type == "rail_relationship_ambiguity":
        if category == "ambiguous_pass_through" and components:
            return group_type, components[0]
        return group_type, rails[0] if rails else normalized
    if group_type == "voltage_unknown":
        return group_type, rails[0] if rails else normalized
    if group_type == "geometry_missing":
        return group_type, rails[0] if rails else normalized
    if group_type == "source_sink_unresolved":
        return group_type, rails[0] if rails else normalized
    if group_type == "component_role_unknown":
        return group_type, components[0] if components else normalized
    return group_type, normalized


def manifest_id_for(source_id: str, category: str, normalized_target: str) -> str:
    return f"mdi_manifest_{safe_id(category)}_{safe_id(normalized_target)}_{safe_id(source_id)}"


def build_manifest_item(source: dict[str, Any], branches: dict[str, dict[str, Any]], rails: dict[str, dict[str, Any]]) -> dict[str, Any]:
    category = str(source.get("category") or "human_review_needed")
    context = affected_context(source, branches, rails)
    path, reason = resolution_path(source, context)
    priority = priority_for_item(source, path)
    group_type, group_target = group_key_for_item(source, context, path)
    group_id = f"group_{safe_id(group_type)}_{safe_id(group_target)}"
    source_id = str(source.get("id") or f"{category}_{source.get('target_type')}_{source.get('target_id')}")
    normalized_target = str(context["normalized_target"])
    return {
        "manifest_id": manifest_id_for(source_id, category, normalized_target),
        "source_missing_data_id": source_id,
        "category": category,
        "scope": source.get("scope", source.get("target_type", "project")),
        "target_type": source.get("target_type", "project"),
        "target_id": source.get("target_id"),
        "normalized_target": normalized_target,
        "affected_rails": context["affected_rails"],
        "affected_branches": context["affected_branches"],
        "affected_components": context["affected_components"],
        "blocks": [str(block) for block in as_list(source.get("blocks"))],
        "priority": priority,
        "severity": source.get("severity", "info"),
        "resolution_path": path,
        "resolution_reason": reason,
        "group_id": group_id,
        "packet_hint": packet_hint(category, path),
        "evidence": as_list(source.get("evidence")) + [
            evidence("calculation_readiness", "calculation_readiness", "source_missing_data_id", source_id, "manifest item is derived from PR 15 missing data")
        ],
        "notes": source.get("notes", ""),
    }


def group_title(group_type: str, target: str) -> tuple[str, str]:
    titles = {
        "current_model_missing": "Current Model Missing",
        "rail_relationship_ambiguity": "Rail Relationship Ambiguity",
        "voltage_unknown": "Voltage Unknown",
        "geometry_missing": "Geometry Missing",
        "component_role_unknown": "Component Role Unknown",
        "source_sink_unresolved": "Source/Sink Unresolved",
        "human_review": "Human Review Needed",
        "not_required": "Not Required For Next Stage",
    }
    title = f"{titles.get(group_type, 'Missing Data')} - {target}"
    description = f"Grouped {group_type.replace('_', ' ')} items for {target}."
    return title, description


def packet_policy_for_group(group_type: str, path: str) -> dict[str, Any]:
    if path == "not_required":
        return {"packetizable": False, "max_items_per_packet": 10, "split_by": "none"}
    if group_type == "current_model_missing":
        return {"packetizable": True, "max_items_per_packet": 5, "split_by": "rail"}
    if group_type == "rail_relationship_ambiguity":
        return {"packetizable": True, "max_items_per_packet": 5, "split_by": "rail"}
    if group_type == "component_role_unknown":
        return {"packetizable": True, "max_items_per_packet": 10, "split_by": "component"}
    if group_type == "geometry_missing":
        return {"packetizable": True, "max_items_per_packet": 10, "split_by": "rail"}
    return {"packetizable": True, "max_items_per_packet": 10, "split_by": "category"}


def build_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item["group_id"]), []).append(item)

    groups: list[dict[str, Any]] = []
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    for group_id in sorted(grouped):
        rows = sorted(grouped[group_id], key=lambda row: row["manifest_id"])
        group_type = group_id[len("group_"):].rsplit("_", 1)[0] if "_" in group_id else "human_review"
        # The parsed type above is only a fallback; use the first item's category routing for exact type.
        exact_group_type = group_type_for_category(str(rows[0].get("category")), str(rows[0].get("resolution_path")))
        target = str(rows[0].get("normalized_target") or "unknown")
        title, description = group_title(exact_group_type, target)
        path = str(rows[0].get("resolution_path"))
        priority = sorted({str(row.get("priority")) for row in rows}, key=lambda value: priority_rank.get(value, 99))[0]
        blocks = sorted({block for row in rows for block in as_list(row.get("blocks"))})
        groups.append({
            "group_id": group_id,
            "group_type": exact_group_type,
            "title": title,
            "description": description,
            "resolution_path": path,
            "priority": priority,
            "blocks": blocks,
            "item_ids": [row["manifest_id"] for row in rows],
            "target_ids": sorted({str(row.get("target_id")) for row in rows if row.get("target_id") is not None}),
            "affected_rails": sorted({rail for row in rows for rail in as_list(row.get("affected_rails"))}),
            "affected_branches": sorted({branch for row in rows for branch in as_list(row.get("affected_branches"))}),
            "affected_components": sorted({component for row in rows for component in as_list(row.get("affected_components"))}),
            "packet_policy": packet_policy_for_group(exact_group_type, path),
            "evidence": [evidence("calculation_readiness", "calculation_readiness", "group_id", group_id, "group built from manifest items")],
            "unresolved": [],
        })
    return groups


def dedupe_source_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or f"missing_{idx:06d}")
        deduped.setdefault(source_id, item)
    return [deduped[key] for key in sorted(deduped)]


def validate_manifest(source_items: list[dict[str, Any]], manifest_items: list[dict[str, Any]], queues: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    source_ids = {str(item.get("id") or "") for item in source_items}
    represented = {str(item.get("source_missing_data_id") or "") for item in manifest_items}
    dropped = sorted(source_ids - represented)
    if dropped:
        errors.append(f"source missing data item(s) not represented: {', '.join(dropped[:20])}")
    item_ids = {item["manifest_id"] for item in manifest_items}
    assignment_count: dict[str, int] = {item_id: 0 for item_id in item_ids}
    for queue_name, ids in queues.items():
        if queue_name not in QUEUE_NAMES:
            errors.append(f"unexpected resolution queue: {queue_name}")
        for item_id in ids:
            if item_id not in item_ids:
                errors.append(f"resolution queue {queue_name} references unknown item: {item_id}")
            else:
                assignment_count[item_id] += 1
    bad_assignments = sorted(item_id for item_id, count in assignment_count.items() if count != 1)
    if bad_assignments:
        errors.append(f"manifest item(s) not assigned to exactly one queue: {', '.join(bad_assignments[:20])}")
    return errors


def build_manifest(
    project: str,
    calculation_readiness_path: Path,
    branch_topology_enriched_path: Path | None,
    role_resolution_path: Path | None,
    rail_relationships_path: Path | None,
) -> dict[str, Any]:
    calculation_readiness = load_json(calculation_readiness_path)
    if not isinstance(calculation_readiness, dict):
        raise ValueError(f"calculation-readiness artifact must be a JSON object: {calculation_readiness_path}")
    _, branch_warnings = load_optional_json(branch_topology_enriched_path, "branch-topology-enriched")
    _, role_warnings = load_optional_json(role_resolution_path, "role-resolution")
    _, rail_warnings = load_optional_json(rail_relationships_path, "rail-relationships")
    warnings = branch_warnings + role_warnings + rail_warnings

    branches = branch_index(calculation_readiness)
    rails = rail_index(calculation_readiness)
    source_items = dedupe_source_items(as_list(calculation_readiness.get("missing_data_items")))
    manifest_items = [build_manifest_item(item, branches, rails) for item in source_items]
    manifest_items = sorted({item["manifest_id"]: item for item in manifest_items}.values(), key=lambda row: row["manifest_id"])
    groups = build_groups(manifest_items)
    resolution_queues = {name: [] for name in QUEUE_NAMES}
    for item in manifest_items:
        resolution_queues[item["resolution_path"]].append(item["manifest_id"])
    for name in resolution_queues:
        resolution_queues[name] = sorted(resolution_queues[name])

    errors = validate_manifest(source_items, manifest_items, resolution_queues)
    summary = {
        "missing_data_item_count": len(source_items),
        "manifest_item_count": len(manifest_items),
        "group_count": len(groups),
        "deterministic_rule_item_count": len(resolution_queues["deterministic_rule"]),
        "datasheet_extraction_item_count": len(resolution_queues["datasheet_extraction"]),
        "ai_rule_packet_item_count": len(resolution_queues["ai_rule_packet"]),
        "human_review_item_count": len(resolution_queues["human_review"]),
        "not_required_item_count": len(resolution_queues["not_required"]),
        "current_allocation_blocker_count": sum(1 for item in manifest_items if "current_allocation" in item["blocks"]),
        "copper_calculation_blocker_count": sum(1 for item in manifest_items if "copper_calculation" in item["blocks"]),
        "voltage_drop_blocker_count": sum(1 for item in manifest_items if "voltage_drop_calculation" in item["blocks"]),
        "thermal_blocker_count": sum(1 for item in manifest_items if "thermal_calculation" in item["blocks"]),
        "high_priority_count": sum(1 for item in manifest_items if item["priority"] == "high"),
        "medium_priority_count": sum(1 for item in manifest_items if item["priority"] == "medium"),
        "low_priority_count": sum(1 for item in manifest_items if item["priority"] == "low"),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "calculation_readiness": str(calculation_readiness_path),
            "branch_topology_enriched": str(branch_topology_enriched_path) if branch_topology_enriched_path else None,
            "role_resolution": str(role_resolution_path) if role_resolution_path else None,
            "rail_relationships": str(rail_relationships_path) if rail_relationships_path else None,
        },
        "summary": summary,
        "groups": groups,
        "manifest_items": manifest_items,
        "resolution_queues": resolution_queues,
        "unresolved": as_list(calculation_readiness.get("unresolved")),
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "missing_data_manifest_pass": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic missing data manifest.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--calculation-readiness", default=None)
    parser.add_argument("--branch-topology-enriched", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    readiness_path = Path(args.calculation_readiness or default_path("exports/{project}-calculation-readiness-inventory.json", project))
    branch_path = Path(args.branch_topology_enriched) if args.branch_topology_enriched else None
    role_path = Path(args.role_resolution) if args.role_resolution else None
    rail_path = Path(args.rail_relationships) if args.rail_relationships else None
    out_path = Path(args.out or default_path("exports/{project}-missing-data-manifest.json", project))

    try:
        if not readiness_path.exists():
            raise FileNotFoundError(f"missing calculation-readiness JSON: {readiness_path}")
        artifact = build_manifest(project, readiness_path, branch_path, role_path, rail_path)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "missing data manifest: "
        f"source_missing={summary['missing_data_item_count']} "
        f"items={summary['manifest_item_count']} "
        f"groups={summary['group_count']} "
        f"deterministic={summary['deterministic_rule_item_count']} "
        f"datasheet={summary['datasheet_extraction_item_count']} "
        f"ai={summary['ai_rule_packet_item_count']} "
        f"human={summary['human_review_item_count']} "
        f"not_required={summary['not_required_item_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["missing_data_manifest_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
