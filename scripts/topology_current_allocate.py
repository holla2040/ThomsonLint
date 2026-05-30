#!/usr/bin/env python3
"""Allocate explicit normalized currents to topology branches where deterministic.

PR 20 scope only: consume PR19 normalized current records and topology context,
then emit branch-level allocation records where the mapping is deterministic.
This script does not infer unknown load currents, divide shared currents, infer
ratings, create findings, or make compliance judgments.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
CURRENT_BLOCKER_CATEGORIES = {
    "branch_current_unknown",
    "source_sink_not_resolved",
    "relationship_direction_unknown",
    "component_role_unknown",
    "power_path_direction_unknown",
    "current_model_missing",
}
AMBIGUOUS_CATEGORIES = {
    "source_sink_not_resolved",
    "relationship_direction_unknown",
    "power_path_direction_unknown",
}
PASSTHROUGH_SUBTYPES = {
    "fuse",
    "shunt",
    "ferrite_bead",
    "zero_ohm_link",
    "zero_ohm_resistor",
    "jumper",
    "load_switch",
    "current_sense",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def source_artifact(artifact_type: str, path: Path | None, record_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "path": str(path) if path else None,
        "record_id": record_id,
        "notes": notes,
    }


def source_artifacts_for(paths: dict[str, Path | None]) -> list[dict[str, Any]]:
    return [
        source_artifact("current_models_normalized", paths["current_models"], None, "PR19 normalized explicit current records."),
        source_artifact("branch_topology_enriched", paths["branch_topology"], None, "PR14 branch context."),
        source_artifact("rail_relationships", paths["rail_relationships"], None, "PR13 rail relationship context."),
        source_artifact("role_resolution", paths["role_resolution"], None, "PR12 role context."),
        source_artifact("missing_data_manifest", paths["missing_data_manifest"], None, "PR16 blocker context."),
    ] + ([source_artifact("calculation_readiness", paths["calculation_readiness"], None, "Optional PR15 readiness context.")] if paths.get("calculation_readiness") else [])


def branch_rows(branch_topology: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("branches", "branch_records", "branch_topology", "records"):
        rows = branch_topology.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def relationship_rows(rail_relationships: dict[str, Any], branch_topology: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in as_list(rail_relationships.get("relationships")) if isinstance(row, dict)]
    if rows:
        return rows
    deduped: dict[str, dict[str, Any]] = {}
    for branch in branch_rows(branch_topology):
        for row in as_list(branch.get("rail_relationships")):
            if isinstance(row, dict):
                rel_id = str(row.get("relationship_id") or f"relationship_{len(deduped):06d}")
                deduped[rel_id] = row
    return [deduped[key] for key in sorted(deduped)]


def component_rows(role_resolution: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(role_resolution.get("component_roles")) if isinstance(row, dict)]


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(manifest.get("manifest_items")) if isinstance(row, dict)]


def item_id(item: dict[str, Any]) -> str | None:
    value = item.get("manifest_id") or item.get("id") or item.get("source_missing_data_id")
    return str(value) if value not in (None, "") else None


def text_values(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("target_id") or ""),
        str(item.get("normalized_target") or ""),
    }
    for key in ("affected_rails", "affected_branches", "affected_components", "blocks"):
        values.update(str(value) for value in as_list(item.get(key)) if value not in (None, ""))
    return {value for value in values if value}


def manifest_matches(
    manifest: dict[str, Any],
    *,
    branch_id: str | None = None,
    rail_name: str | None = None,
    refdes: str | None = None,
    categories: set[str] | None = None,
    blocks: set[str] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in manifest_items(manifest):
        category = str(item.get("category") or "")
        if categories is not None and category not in categories:
            continue
        item_blocks = {str(block) for block in as_list(item.get("blocks"))}
        if blocks is not None and item_blocks.isdisjoint(blocks):
            continue
        values = text_values(item)
        if (
            (branch_id and branch_id in values)
            or (rail_name and rail_name in values)
            or (refdes and refdes in values)
        ):
            matches.append(item)
    return sorted({item_id(item): item for item in matches if item_id(item)}.values(), key=lambda row: str(item_id(row)))


def linkage(items: list[dict[str, Any]]) -> dict[str, Any]:
    ids = sorted({str(item_id(item)) for item in items if item_id(item)})
    groups = sorted({str(item.get("group_id")) for item in items if isinstance(item.get("group_id"), str)})
    categories = sorted({str(item.get("category")) for item in items if isinstance(item.get("category"), str)})
    calculations = sorted({str(block) for item in items for block in as_list(item.get("blocks")) if isinstance(block, str)})
    paths = sorted({str(item.get("resolution_path")) for item in items if isinstance(item.get("resolution_path"), str)})
    queues = sorted({str(item.get("resolution_queue") or item.get("resolution_path")) for item in items if isinstance(item.get("resolution_queue") or item.get("resolution_path"), str)})
    return {
        "missing_data_manifest_item_ids": ids,
        "missing_data_group_ids": groups,
        "blocked_by_categories": categories,
        "blocked_by_calculations": calculations,
        "resolution_path": paths[0] if paths else None,
        "resolution_queue": queues[0] if queues else None,
    }


def record_ids(records: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row.get("record_id")) for row in records if isinstance(row.get("record_id"), str)})


def evidence_refs(records: list[dict[str, Any]]) -> list[str]:
    return sorted({str(ref) for row in records for ref in as_list(row.get("evidence_refs")) if isinstance(ref, str)})


def branch_id_set(branch: dict[str, Any]) -> str | None:
    value = branch.get("branch_id")
    return str(value) if isinstance(value, str) and value else None


def rail_for_branch(branch: dict[str, Any]) -> str | None:
    value = branch.get("rail_name") or branch.get("rail") or branch.get("net_name")
    return str(value) if isinstance(value, str) and value else None


def net_for_branch(branch: dict[str, Any]) -> str | None:
    value = branch.get("net_name")
    return str(value) if isinstance(value, str) and value else None


def branch_index(branches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {branch["branch_id"]: branch for branch in branches if isinstance(branch.get("branch_id"), str)}


def branches_by_rail(branches: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_rail: dict[str, list[dict[str, Any]]] = {}
    for branch in branches:
        rail_name = rail_for_branch(branch)
        if rail_name:
            by_rail.setdefault(rail_name, []).append(branch)
    return {rail: sorted(rows, key=lambda row: str(row.get("branch_id"))) for rail, rows in by_rail.items()}


def component_refdeses(rows: Any) -> set[str]:
    refs: set[str] = set()
    for row in as_list(rows):
        if isinstance(row, dict) and isinstance(row.get("refdes"), str):
            refs.add(row["refdes"])
        elif isinstance(row, str):
            refs.add(row)
    return refs


def branch_has_blocker(branch: dict[str, Any], categories: set[str]) -> bool:
    seed = branch.get("calculation_readiness_seed") if isinstance(branch.get("calculation_readiness_seed"), dict) else {}
    blocked = {str(value) for value in as_list(seed.get("blocked_reasons"))}
    for item in as_list(branch.get("unresolved")):
        if isinstance(item, dict) and isinstance(item.get("category"), str):
            blocked.add(item["category"])
    return not blocked.isdisjoint(categories)


def rail_has_manifest_blocker(manifest: dict[str, Any], rail_name: str) -> bool:
    return bool(manifest_matches(
        manifest,
        rail_name=rail_name,
        categories=AMBIGUOUS_CATEGORIES,
        blocks={"current_allocation", "calculation_readiness"},
    ))


def current_record_source_artifacts(record: dict[str, Any], fallback_paths: dict[str, Path | None]) -> list[dict[str, Any]]:
    artifacts = [row for row in as_list(record.get("source_artifacts")) if isinstance(row, dict)]
    return artifacts or [source_artifact("current_models_normalized", fallback_paths["current_models"], record.get("record_id"), "Normalized explicit current record.")]


def allocation_record(
    *,
    allocation_type: str,
    branch: dict[str, Any],
    current_a: float,
    current_type: str | None,
    basis: str,
    confidence: float | None,
    records: list[dict[str, Any]],
    manifest_linkage: dict[str, Any],
    paths: dict[str, Path | None],
    assumptions: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id"))
    allocation_id = f"alloc_{safe_id(allocation_type)}_{safe_id(branch_id)}_{safe_id(current_type or 'current')}_{safe_id('_'.join(record_ids(records)))}"
    return {
        "allocation_id": allocation_id,
        "allocation_type": allocation_type,
        "branch_id": branch_id,
        "rail_name": rail_for_branch(branch),
        "net_name": net_for_branch(branch),
        "allocated_current_a": current_a,
        "current_type": current_type,
        "basis": basis,
        "confidence": confidence,
        "source_current_record_ids": record_ids(records),
        "source_artifacts": current_record_source_artifacts(records[0], paths) if records else source_artifacts_for(paths),
        "evidence_refs": evidence_refs(records),
        "missing_data_manifest_item_ids": manifest_linkage.get("missing_data_manifest_item_ids", []),
        "missing_data_group_ids": manifest_linkage.get("missing_data_group_ids", []),
        "assumptions": assumptions or [],
        "warnings": warnings or [],
        "usable_for_calculation": True,
    }


def unresolved_record(
    *,
    reason_code: str,
    target_type: str,
    detail: str,
    paths: dict[str, Path | None],
    branch_id: str | None = None,
    rail_name: str | None = None,
    refdes: str | None = None,
    records: list[dict[str, Any]] | None = None,
    manifest_linkage: dict[str, Any] | None = None,
    missing_inputs: list[dict[str, Any]] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    records = records or []
    manifest_linkage = manifest_linkage or {}
    unresolved_id = f"unres_alloc_{safe_id(reason_code)}_{safe_id(target_type)}_{safe_id(branch_id or rail_name or refdes or '_'.join(record_ids(records)))}"
    return {
        "unresolved_id": unresolved_id,
        "reason_code": reason_code,
        "target_type": target_type,
        "branch_id": branch_id,
        "rail_name": rail_name,
        "refdes": refdes,
        "source_current_record_ids": record_ids(records),
        "missing_inputs": missing_inputs or [],
        "blocked_by_categories": manifest_linkage.get("blocked_by_categories", []),
        "blocked_by_calculations": manifest_linkage.get("blocked_by_calculations", []),
        "missing_data_manifest_item_ids": manifest_linkage.get("missing_data_manifest_item_ids", []),
        "missing_data_group_ids": manifest_linkage.get("missing_data_group_ids", []),
        "resolution_path": manifest_linkage.get("resolution_path"),
        "resolution_queue": manifest_linkage.get("resolution_queue"),
        "human_review_needed": True,
        "detail": detail,
        "source_artifacts": source_artifacts_for(paths),
        "evidence_refs": sorted(set(evidence or evidence_refs(records))),
    }


def missing_input(field: str, reason: str, required_for: list[str]) -> dict[str, Any]:
    return {
        "field": field,
        "reason": reason,
        "required_for": required_for,
    }


def normalized_current_records(current_models: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(current_models.get("normalized_currents")) if isinstance(row, dict)]


def current_value(record: dict[str, Any]) -> float | None:
    value = record.get("value")
    unit = record.get("unit")
    return float(value) if is_number(value) and unit == "A" else None


def explicit_current_values(records: list[dict[str, Any]]) -> tuple[list[float], list[dict[str, Any]]]:
    values: list[float] = []
    invalid: list[dict[str, Any]] = []
    for record in records:
        value = current_value(record)
        if value is None or not math.isfinite(value):
            invalid.append(record)
            continue
        values.append(value)
    return values, invalid


def add_explicit_branch_allocations(
    records: list[dict[str, Any]],
    branches: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    paths: dict[str, Path | None],
) -> list[dict[str, Any]]:
    allocations: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type") != "branch_current" or record.get("usable_for_calculation") is not True:
            continue
        branch_id = record.get("branch_id")
        value = current_value(record)
        if not isinstance(branch_id, str) or value is None:
            continue
        branch = branches.get(branch_id, {"branch_id": branch_id, "rail_name": record.get("rail_name"), "net_name": record.get("net_name")})
        link_items = manifest_matches(manifest, branch_id=branch_id, rail_name=record.get("rail_name"), categories={"branch_current_unknown", "current_model_missing"})
        allocations.append(allocation_record(
            allocation_type="explicit_branch_current",
            branch=branch,
            current_a=value,
            current_type=record.get("current_type"),
            basis=str(record.get("basis") or "explicit_branch_current"),
            confidence=float(record.get("confidence")) if is_number(record.get("confidence")) else None,
            records=[record],
            manifest_linkage=linkage(link_items),
            paths=paths,
            assumptions=[],
        ))
    return allocations


def rail_allocation_unresolved_reason(branches: list[dict[str, Any]], manifest: dict[str, Any], rail_name: str) -> str | None:
    if not branches:
        return "rail_to_branch_mapping_unknown"
    if rail_has_manifest_blocker(manifest, rail_name) or any(branch_has_blocker(branch, AMBIGUOUS_CATEGORIES) for branch in branches):
        return "source_sink_not_resolved"
    if len(branches) > 1:
        return "shared_plane_current_unknown"
    return None


def add_rail_allocations(
    records: list[dict[str, Any]],
    by_rail: dict[str, list[dict[str, Any]]],
    manifest: dict[str, Any],
    paths: dict[str, Path | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allocations: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type") != "rail_current":
            continue
        rail_name = record.get("rail_name")
        value = current_value(record)
        if not isinstance(rail_name, str) or value is None:
            continue
        candidates = by_rail.get(rail_name, [])
        reason = rail_allocation_unresolved_reason(candidates, manifest, rail_name)
        link_items = manifest_matches(manifest, rail_name=rail_name, categories=CURRENT_BLOCKER_CATEGORIES)
        link = linkage(link_items)
        if reason is not None:
            unresolved.append(unresolved_record(
                reason_code=reason,
                target_type="rail",
                rail_name=rail_name,
                records=[record],
                manifest_linkage=link,
                missing_inputs=[missing_input("deterministic_single_branch_for_rail", "Rail current cannot be allocated without exactly one deterministic branch owner.", ["current_allocation"])],
                detail="Explicit rail current was preserved but not divided or assigned because branch ownership is not deterministic.",
                paths=paths,
            ))
            continue
        branch = candidates[0]
        allocations.append(allocation_record(
            allocation_type="deterministic_single_path_rail_current",
            branch=branch,
            current_a=value,
            current_type=record.get("current_type"),
            basis=str(record.get("basis") or "explicit_rail_current_single_path"),
            confidence=float(record.get("confidence")) if is_number(record.get("confidence")) else None,
            records=[record],
            manifest_linkage=link,
            paths=paths,
            assumptions=[{
                "id": "single_path_rail_current",
                "description": "Explicit rail current maps to exactly one branch for this rail.",
                "basis": "topology_branch_count",
                "evidence_refs": [],
                "confidence": 0.9,
            }],
        ))
    return allocations, unresolved


def component_sink_candidates(record: dict[str, Any], branches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refdes = record.get("refdes")
    rail_name = record.get("rail_name")
    if not isinstance(refdes, str) or not isinstance(rail_name, str):
        return []
    candidates: list[dict[str, Any]] = []
    for branch in branches:
        if rail_for_branch(branch) != rail_name:
            continue
        if refdes in component_refdeses(branch.get("sink_candidates")):
            candidates.append(branch)
    return sorted(candidates, key=lambda row: str(row.get("branch_id")))


def add_component_allocations(
    records: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    manifest: dict[str, Any],
    paths: dict[str, Path | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unresolved: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for record in records:
        if record.get("record_type") != "component_current":
            continue
        refdes = record.get("refdes")
        rail_name = record.get("rail_name")
        value = current_value(record)
        link_items = manifest_matches(manifest, rail_name=rail_name if isinstance(rail_name, str) else None, refdes=refdes if isinstance(refdes, str) else None, categories=CURRENT_BLOCKER_CATEGORIES)
        link = linkage(link_items)
        candidates = component_sink_candidates(record, branches)
        if value is None and isinstance(refdes, str) and isinstance(rail_name, str) and len(candidates) == 1:
            unresolved.append(unresolved_record(
                reason_code="missing_current_model",
                target_type="component",
                rail_name=rail_name,
                refdes=refdes,
                records=[record],
                manifest_linkage=link,
                missing_inputs=[missing_input("component_current_a", "Mapped component current record is missing a finite amp value.", ["current_allocation"])],
                detail="Explicit component current was not allocated because its normalized value is missing or not a finite amp value.",
                paths=paths,
            ))
            continue
        if value is None or not isinstance(refdes, str) or not isinstance(rail_name, str) or len(candidates) != 1:
            unresolved.append(unresolved_record(
                reason_code="component_to_branch_mapping_unknown",
                target_type="component",
                rail_name=rail_name if isinstance(rail_name, str) else None,
                refdes=refdes if isinstance(refdes, str) else None,
                records=[record],
                manifest_linkage=link,
                missing_inputs=[missing_input("single_sink_branch_mapping", "Component current requires exactly one sink branch on the same rail.", ["current_allocation"])],
                detail="Explicit component current was not allocated because component-to-branch mapping is missing or ambiguous.",
                paths=paths,
            ))
            continue
        branch = candidates[0]
        grouped.setdefault((str(branch["branch_id"]), str(record.get("current_type") or "nominal")), []).append((record, branch))

    allocations: list[dict[str, Any]] = []
    for (branch_id, current_type), rows in sorted(grouped.items()):
        records_for_branch = [row[0] for row in rows]
        branch = rows[0][1]
        explicit_values, invalid_records = explicit_current_values(records_for_branch)
        link_items = manifest_matches(manifest, branch_id=branch_id, rail_name=rail_for_branch(branch), categories=CURRENT_BLOCKER_CATEGORIES)
        if invalid_records:
            unresolved.append(unresolved_record(
                reason_code="missing_current_model",
                target_type="branch",
                branch_id=branch_id,
                rail_name=rail_for_branch(branch),
                records=invalid_records,
                manifest_linkage=linkage(link_items),
                missing_inputs=[missing_input("component_current_a", "Mapped component current record is missing a finite amp value.", ["current_allocation"])],
                detail="Component current branch sum was not emitted because at least one mapped current record lacked an explicit finite amp value.",
                paths=paths,
            ))
            continue
        current_sum = sum(explicit_values)
        warnings = []
        if any(str(item.get("category")) in {"branch_current_unknown", "current_model_missing"} for item in link_items):
            warnings.append("branch has current-model missing manifest items; only explicit mapped component currents were summed")
        allocations.append(allocation_record(
            allocation_type="deterministic_branch_sum",
            branch=branch,
            current_a=current_sum,
            current_type=current_type,
            basis="sum_of_explicit_component_currents",
            confidence=min([float(record.get("confidence")) for record in records_for_branch if is_number(record.get("confidence"))] or [0.8]),
            records=records_for_branch,
            manifest_linkage=linkage(link_items),
            paths=paths,
            assumptions=[{
                "id": "explicit_component_current_sum_only",
                "description": "Only explicit component current records mapped to this branch are summed; missing currents are not treated as zero.",
                "basis": "explicit_current_records",
                "evidence_refs": evidence_refs(records_for_branch),
                "confidence": 0.85,
            }],
            warnings=warnings,
        ))
    return allocations, unresolved


def passthrough_refdeses(branch: dict[str, Any]) -> set[str]:
    return component_refdeses(branch.get("pass_through_candidates"))


def relationship_direction_known(row: dict[str, Any]) -> bool:
    return row.get("direction") in {"parent_to_child", "input_to_output", "source_to_sink"}


def is_passthrough_relationship(row: dict[str, Any], components: dict[str, dict[str, Any]]) -> bool:
    rel_type = str(row.get("relationship_type") or "").lower()
    subtype = str(row.get("through_subtype") or "").lower()
    refdes = row.get("through_component")
    component = components.get(refdes) if isinstance(refdes, str) else None
    component_role = str(component.get("role") or "").lower() if component else ""
    component_subtype = str(component.get("role_subtype") or "").lower() if component else ""
    return rel_type == "pass_through" or component_role == "pass_through" or subtype in PASSTHROUGH_SUBTYPES or component_subtype in PASSTHROUGH_SUBTYPES


def known_current_by_branch(allocations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    known: dict[str, dict[str, Any]] = {}
    for allocation in allocations:
        if allocation.get("usable_for_calculation") is True and is_number(allocation.get("allocated_current_a")):
            known[str(allocation["branch_id"])] = allocation
    return known


def add_passthrough_allocations(
    allocations_so_far: list[dict[str, Any]],
    branches: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    components: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    paths: dict[str, Path | None],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_rail = branches_by_rail(branches)
    known = known_current_by_branch(allocations_so_far)
    new_allocations: list[dict[str, Any]] = []
    passthroughs: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for relationship in relationships:
        if not is_passthrough_relationship(relationship, components):
            continue
        refdes = relationship.get("through_component")
        if not isinstance(refdes, str):
            continue
        parent = relationship.get("parent_rail")
        child = relationship.get("child_rail")
        input_branches = by_rail.get(parent, []) if isinstance(parent, str) else []
        output_branches = by_rail.get(child, []) if isinstance(child, str) else []
        component = components.get(refdes, {})
        component_role = str(component.get("role") or "pass_through")
        link_items = manifest_matches(manifest, rail_name=parent if isinstance(parent, str) else None, refdes=refdes, categories=CURRENT_BLOCKER_CATEGORIES)
        link_items.extend(manifest_matches(manifest, rail_name=child if isinstance(child, str) else None, refdes=refdes, categories=CURRENT_BLOCKER_CATEGORIES))
        link = linkage(link_items)
        passthrough_id = f"pass_{safe_id(refdes)}_{safe_id(parent)}_{safe_id(child)}"

        reason: str | None = None
        if not relationship_direction_known(relationship):
            reason = "relationship_direction_unknown"
        elif len(input_branches) != 1 or len(output_branches) != 1:
            reason = "ambiguous_branch_path"
        elif branch_has_blocker(input_branches[0], {"source_sink_not_resolved"}) or branch_has_blocker(output_branches[0], {"source_sink_not_resolved"}):
            reason = "source_sink_not_resolved"
        elif str(input_branches[0].get("branch_id")) not in known:
            reason = "missing_current_model"

        if reason is not None:
            passthroughs.append({
                "passthrough_id": passthrough_id,
                "component_refdes": refdes,
                "component_role": component_role,
                "input_branch_ids": [str(branch.get("branch_id")) for branch in input_branches if isinstance(branch.get("branch_id"), str)],
                "output_branch_ids": [str(branch.get("branch_id")) for branch in output_branches if isinstance(branch.get("branch_id"), str)],
                "rail_name": child if isinstance(child, str) else parent if isinstance(parent, str) else None,
                "current_transfer_status": "ambiguous" if reason in {"ambiguous_branch_path", "relationship_direction_unknown"} else "blocked",
                "allocated_current_a": None,
                "source_current_record_ids": [],
                "warnings": [f"passthrough current transfer blocked: {reason}"],
                "evidence_refs": [],
            })
            unresolved.append(unresolved_record(
                reason_code=reason,
                target_type="component",
                rail_name=child if isinstance(child, str) else parent if isinstance(parent, str) else None,
                refdes=refdes,
                manifest_linkage=link,
                missing_inputs=[missing_input("deterministic_passthrough_path", "Pass-through allocation requires known direction, source/sink resolution, one input branch, one output branch, and known input current.", ["current_allocation"])],
                detail="Pass-through current transfer was not deterministic.",
                paths=paths,
            ))
            continue

        input_branch = input_branches[0]
        output_branch = output_branches[0]
        source_allocation = known[str(input_branch["branch_id"])]
        current_a = float(source_allocation["allocated_current_a"])
        current_records = [
            {
                "record_id": record_id,
                "evidence_refs": source_allocation.get("evidence_refs", []),
                "source_artifacts": source_allocation.get("source_artifacts", []),
                "basis": source_allocation.get("basis"),
                "confidence": source_allocation.get("confidence"),
            }
            for record_id in as_list(source_allocation.get("source_current_record_ids"))
        ]
        if not current_records:
            current_records = [{"record_id": source_allocation["allocation_id"], "evidence_refs": [], "source_artifacts": [], "basis": source_allocation.get("basis"), "confidence": source_allocation.get("confidence")}]
        passthroughs.append({
            "passthrough_id": passthrough_id,
            "component_refdes": refdes,
            "component_role": component_role,
            "input_branch_ids": [str(input_branch["branch_id"])],
            "output_branch_ids": [str(output_branch["branch_id"])],
            "rail_name": child if isinstance(child, str) else None,
            "current_transfer_status": "deterministic",
            "allocated_current_a": current_a,
            "source_current_record_ids": record_ids(current_records),
            "warnings": [],
            "evidence_refs": evidence_refs(current_records),
        })
        new_allocations.append(allocation_record(
            allocation_type="deterministic_passthrough_current",
            branch=output_branch,
            current_a=current_a,
            current_type=source_allocation.get("current_type"),
            basis="deterministic_passthrough_from_known_input_branch",
            confidence=source_allocation.get("confidence") if is_number(source_allocation.get("confidence")) else None,
            records=current_records,
            manifest_linkage=link,
            paths=paths,
            assumptions=[{
                "id": "single_path_passthrough",
                "description": "Known input branch current was copied through one resolved pass-through relationship to one output branch.",
                "basis": "resolved_passthrough_relationship",
                "evidence_refs": evidence_refs(current_records),
                "confidence": 0.85,
            }],
        ))
    return new_allocations, unresolved, passthroughs


def add_manifest_unresolved(
    manifest: dict[str, Any],
    branches: dict[str, dict[str, Any]],
    allocated_branch_ids: set[str],
    paths: dict[str, Path | None],
) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    for item in manifest_items(manifest):
        category = str(item.get("category") or "")
        if category not in {"branch_current_unknown", "current_model_missing"}:
            continue
        target_id = item.get("target_id")
        branch_ids = [str(value) for value in as_list(item.get("affected_branches")) if isinstance(value, str)]
        if isinstance(target_id, str) and target_id in branches and target_id not in branch_ids:
            branch_ids.append(target_id)
        if not branch_ids and item.get("target_type") == "branch" and isinstance(target_id, str):
            branch_ids.append(target_id)
        for branch_id in sorted(set(branch_ids)):
            if branch_id in allocated_branch_ids:
                continue
            branch = branches.get(branch_id, {"branch_id": branch_id})
            unresolved.append(unresolved_record(
                reason_code="missing_current_model",
                target_type="branch",
                branch_id=branch_id,
                rail_name=rail_for_branch(branch),
                manifest_linkage=linkage([item]),
                missing_inputs=[missing_input("branch_current_a", "Explicit branch current or deterministic allocation is missing.", ["current_allocation", "copper_calculation", "voltage_drop_calculation"])],
                detail="Branch remains without explicit or deterministically allocated current.",
                paths=paths,
            ))
    return unresolved


def dedupe_by_id(rows: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped[str(row.get(id_key))] = row
    return [deduped[key] for key in sorted(deduped)]


def build_allocation_artifact(
    *,
    project: str,
    current_models_path: Path,
    branch_topology_path: Path,
    rail_relationships_path: Path,
    role_resolution_path: Path,
    missing_data_manifest_path: Path,
    calculation_readiness_path: Path | None,
) -> dict[str, Any]:
    current_models = load_json(current_models_path)
    branch_topology = load_json(branch_topology_path)
    rail_relationships = load_json(rail_relationships_path)
    role_resolution = load_json(role_resolution_path)
    manifest = load_json(missing_data_manifest_path)
    if not isinstance(current_models, dict):
        raise ValueError(f"current-models-normalized artifact must be a JSON object: {current_models_path}")
    if not isinstance(branch_topology, dict):
        raise ValueError(f"branch-topology-enriched artifact must be a JSON object: {branch_topology_path}")
    if not isinstance(rail_relationships, dict):
        raise ValueError(f"rail-relationships artifact must be a JSON object: {rail_relationships_path}")
    if not isinstance(role_resolution, dict):
        raise ValueError(f"role-resolution artifact must be a JSON object: {role_resolution_path}")
    if not isinstance(manifest, dict):
        raise ValueError(f"missing-data-manifest artifact must be a JSON object: {missing_data_manifest_path}")
    if calculation_readiness_path is not None and calculation_readiness_path.exists():
        readiness = load_json(calculation_readiness_path)
        if not isinstance(readiness, dict):
            raise ValueError(f"calculation-readiness artifact must be a JSON object: {calculation_readiness_path}")

    paths = {
        "current_models": current_models_path,
        "branch_topology": branch_topology_path,
        "rail_relationships": rail_relationships_path,
        "role_resolution": role_resolution_path,
        "missing_data_manifest": missing_data_manifest_path,
        "calculation_readiness": calculation_readiness_path,
    }
    branches = branch_rows(branch_topology)
    branch_by_id = branch_index(branches)
    by_rail = branches_by_rail(branches)
    relationships = relationship_rows(rail_relationships, branch_topology)
    components = {str(row["refdes"]): row for row in component_rows(role_resolution) if isinstance(row.get("refdes"), str)}
    records = normalized_current_records(current_models)

    errors: list[str] = []
    warnings: list[str] = []
    allocation_records: list[dict[str, Any]] = []
    unresolved_allocations: list[dict[str, Any]] = []
    passthrough_records: list[dict[str, Any]] = []

    unsupported_records = [record for record in records if record.get("record_type") not in {"branch_current", "rail_current", "component_current", "rating"}]
    for record in unsupported_records:
        unresolved_allocations.append(unresolved_record(
            reason_code="unsupported_current_record_type",
            target_type="current_record",
            records=[record],
            missing_inputs=[missing_input("supported_current_record_type", "Only branch_current, rail_current, and component_current are allocation inputs in PR20.", ["current_allocation"])],
            detail="Normalized current record type is unsupported for allocation.",
            paths=paths,
        ))

    allocation_records.extend(add_explicit_branch_allocations(records, branch_by_id, manifest, paths))
    rail_allocations, rail_unresolved = add_rail_allocations(records, by_rail, manifest, paths)
    allocation_records.extend(rail_allocations)
    unresolved_allocations.extend(rail_unresolved)
    component_allocations, component_unresolved = add_component_allocations(records, branches, manifest, paths)
    allocation_records.extend(component_allocations)
    unresolved_allocations.extend(component_unresolved)
    passthrough_allocations, passthrough_unresolved, passthroughs = add_passthrough_allocations(allocation_records, branches, relationships, components, manifest, paths)
    allocation_records.extend(passthrough_allocations)
    unresolved_allocations.extend(passthrough_unresolved)
    passthrough_records.extend(passthroughs)

    allocated_branch_ids = {str(row.get("branch_id")) for row in allocation_records if isinstance(row.get("branch_id"), str)}
    unresolved_allocations.extend(add_manifest_unresolved(manifest, branch_by_id, allocated_branch_ids, paths))

    allocation_records = dedupe_by_id(allocation_records, "allocation_id")
    unresolved_allocations = dedupe_by_id(unresolved_allocations, "unresolved_id")
    passthrough_records = dedupe_by_id(passthrough_records, "passthrough_id")
    warnings.extend([warning for row in allocation_records for warning in as_list(row.get("warnings"))])

    summary = {
        "input_current_record_count": len(records),
        "branch_current_input_count": sum(1 for row in records if row.get("record_type") == "branch_current"),
        "rail_current_input_count": sum(1 for row in records if row.get("record_type") == "rail_current"),
        "component_current_input_count": sum(1 for row in records if row.get("record_type") == "component_current"),
        "rating_input_count": sum(1 for row in records if row.get("record_type") == "rating"),
        "allocation_record_count": len(allocation_records),
        "unresolved_allocation_count": len(unresolved_allocations),
        "passthrough_record_count": len(passthrough_records),
        "directly_usable_branch_allocation_count": sum(1 for row in allocation_records if row.get("allocation_type") == "explicit_branch_current" and row.get("usable_for_calculation") is True),
        "deterministic_rail_allocation_count": sum(1 for row in allocation_records if row.get("allocation_type") == "deterministic_single_path_rail_current"),
        "deterministic_component_allocation_count": sum(1 for row in allocation_records if row.get("allocation_type") == "deterministic_branch_sum"),
        "deterministic_passthrough_allocation_count": sum(1 for row in allocation_records if row.get("allocation_type") == "deterministic_passthrough_current"),
        "ambiguous_allocation_count": sum(1 for row in unresolved_allocations if row.get("reason_code") in {"ambiguous_branch_path", "shared_plane_current_unknown", "component_to_branch_mapping_unknown", "rail_to_branch_mapping_unknown"}),
        "missing_current_model_count": sum(1 for row in unresolved_allocations if row.get("reason_code") == "missing_current_model"),
        "shared_plane_current_unknown_count": sum(1 for row in unresolved_allocations if row.get("reason_code") == "shared_plane_current_unknown"),
        "source_sink_unresolved_count": sum(1 for row in unresolved_allocations if row.get("reason_code") == "source_sink_not_resolved"),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return {
        "project": project,
        "generated_at_utc": utc_now(),
        "execution_pass": True,
        "topology_current_allocation_pass": not errors,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts_for(paths),
        "allocation_records": allocation_records,
        "unresolved_allocations": unresolved_allocations,
        "passthrough_records": passthrough_records,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Allocate explicit normalized currents to topology branches where deterministic.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--current-models-normalized", default=None)
    parser.add_argument("--branch-topology-enriched", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--calculation-readiness", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    current_models_path = Path(args.current_models_normalized or default_path("exports/{project}-current-models-normalized.json", project))
    branch_path = Path(args.branch_topology_enriched or default_path("exports/{project}-branch-topology-enriched.json", project))
    rail_path = Path(args.rail_relationships or default_path("exports/{project}-rail-relationships.json", project))
    role_path = Path(args.role_resolution or default_path("exports/{project}-topology-roles.json", project))
    manifest_path = Path(args.missing_data_manifest or default_path("exports/{project}-missing-data-manifest.json", project))
    readiness_path = Path(args.calculation_readiness) if args.calculation_readiness else None
    out_path = Path(args.out or default_path("exports/{project}-topology-current-allocation.json", project))

    try:
        for label, path in (
            ("current-models-normalized", current_models_path),
            ("branch-topology-enriched", branch_path),
            ("rail-relationships", rail_path),
            ("role-resolution", role_path),
            ("missing-data-manifest", manifest_path),
        ):
            if not path.exists():
                raise FileNotFoundError(f"missing {label} JSON: {path}")
        artifact = build_allocation_artifact(
            project=project,
            current_models_path=current_models_path,
            branch_topology_path=branch_path,
            rail_relationships_path=rail_path,
            role_resolution_path=role_path,
            missing_data_manifest_path=manifest_path,
            calculation_readiness_path=readiness_path,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology current allocation: "
        f"input={summary['input_current_record_count']} "
        f"allocations={summary['allocation_record_count']} "
        f"unresolved={summary['unresolved_allocation_count']} "
        f"passthrough={summary['passthrough_record_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["topology_current_allocation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
