#!/usr/bin/env python3
"""Normalize explicit rating records into a deterministic rating artifact.

PR 23 scope only: consume PR19 normalized rating records and preserve explicit
rating facts for later margin calculations. This script does not calculate
margins, infer ratings, infer current, create findings, or make compliance
judgments.
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

SUPPORTED_UNITS = {
    "A": 1.0,
    "mA": 1e-3,
    "uA": 1e-6,
    "µA": 1e-6,
}

SUPPORTED_TARGET_TYPES = {
    "fuse",
    "fuse_pin",
    "connector",
    "connector_pin",
    "regulator",
    "regulator_output",
    "regulator_input",
    "load_switch",
    "pass_through_component",
    "component",
    "rail",
    "branch",
}

SUPPORTED_RATING_NAMES = {
    "current_max",
    "pin_current_max",
    "output_current_max",
    "input_current_max",
    "continuous_current_max",
    "hold_current",
    "trip_current",
    "thermal_current_limit",
    "package_current_limit",
}

RATING_NAME_ALIASES = {
    "pin_current_max": "pin_current_max",
    "connector_pin_current_max": "pin_current_max",
    "fuse_hold_current": "hold_current",
    "fuse_trip_current": "trip_current",
    "regulator_output_current": "output_current_max",
    "regulator_current_limit": "current_max",
}

MANIFEST_CATEGORIES = {
    "rating_missing",
    "current_model_missing",
    "component_role_unknown",
    "source_sink_not_resolved",
    "relationship_direction_unknown",
}

MARGIN_FAMILIES = {
    "fuse_margin",
    "regulator_load_margin",
    "connector_pin_current_margin",
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


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    return value


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def canonical_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return text or None


def normalize_unit(unit: Any) -> str | None:
    if not isinstance(unit, str):
        return None
    aliases = {
        "a": "A",
        "ma": "mA",
        "ua": "uA",
        "μa": "µA",
        "µa": "µA",
    }
    return aliases.get(unit.strip().lower())


def normalize_rating_name(value: Any) -> str | None:
    canonical = canonical_text(value)
    if canonical is None:
        return None
    return RATING_NAME_ALIASES.get(canonical, canonical)


def source_artifact(artifact_type: str, path: Path | None, record_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "path": str(path) if path else None,
        "record_id": record_id,
        "notes": notes,
    }


def source_artifacts_for(paths: dict[str, Path | None]) -> list[dict[str, Any]]:
    artifacts = [
        source_artifact("current_models_normalized", paths["current_models"], None, "PR19 normalized explicit current/rating records.")
    ]
    for key, artifact_type, notes in (
        ("missing_data_manifest", "missing_data_manifest", "Optional PR16 blocker context."),
        ("role_resolution", "role_resolution", "Optional PR12 role context."),
        ("rail_relationships", "rail_relationships", "Optional PR13 rail relationship context."),
        ("branch_topology", "branch_topology_enriched", "Optional branch context."),
    ):
        if paths.get(key):
            artifacts.append(source_artifact(artifact_type, paths[key], None, notes))
    return artifacts


def source_record_index(record_id: Any) -> int | None:
    if not isinstance(record_id, str):
        return None
    match = re.fullmatch(r"source_record_(\d+)", record_id)
    if not match:
        return None
    return int(match.group(1))


def flattened_current_model_records(current_model: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("branch_currents", "rail_currents", "component_currents", "ratings"):
        rows.extend(row for row in as_list(current_model.get(key)) if isinstance(row, dict))
    return rows


def source_rating_record(record: dict[str, Any], cache: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for artifact in as_list(record.get("source_artifacts")):
        if not isinstance(artifact, dict) or artifact.get("artifact_type") != "current_model":
            continue
        path_value = artifact.get("path")
        source_index = source_record_index(artifact.get("record_id"))
        if not isinstance(path_value, str) or source_index is None:
            continue
        source_path = Path(path_value)
        if not source_path.exists():
            continue
        cache_key = str(source_path)
        if cache_key not in cache:
            loaded = load_json(source_path)
            if isinstance(loaded, dict):
                cache[cache_key] = loaded
        current_model = cache.get(cache_key)
        if not isinstance(current_model, dict):
            continue
        rows = flattened_current_model_records(current_model)
        if 1 <= source_index <= len(rows):
            source = rows[source_index - 1]
            if isinstance(source, dict) and "rating_name" in source:
                return source
    return None


def hydrate_from_source_rating(record: dict[str, Any], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source = source_rating_record(record, cache)
    if source is None:
        return record
    hydrated = dict(record)
    for key in ("target_type", "refdes", "pin", "rail_name", "branch_id", "net_name", "rating_name", "basis", "confidence", "evidence_refs"):
        if hydrated.get(key) in (None, "", []):
            hydrated[key] = source.get(key)
    provenance = dict(as_dict(hydrated.get("provenance")))
    provenance.setdefault("original_value", source.get("value"))
    provenance.setdefault("original_unit", source.get("unit"))
    provenance.setdefault("original_rating_name", source.get("rating_name"))
    hydrated["provenance"] = provenance
    hydrated.setdefault("original_rating_name", source.get("rating_name"))
    return hydrated


def evidence_refs(record: dict[str, Any]) -> list[str]:
    return sorted({str(ref) for ref in as_list(record.get("evidence_refs")) if isinstance(ref, str)})


def confidence_value(record: dict[str, Any]) -> float | None:
    value = record.get("confidence")
    return float(value) if is_number(value) else None


def target_identity(record: dict[str, Any]) -> str | None:
    for key in ("refdes", "branch_id", "rail_name", "net_name", "target_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def item_id(item: dict[str, Any]) -> str | None:
    value = item.get("manifest_id") or item.get("id") or item.get("source_missing_data_id")
    return str(value) if value not in (None, "") else None


def string_values(values: Any) -> set[str]:
    return {str(value) for value in as_list(values) if value not in (None, "")}


def manifest_text_values(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("target_id") or ""),
        str(item.get("normalized_target") or ""),
        str(item.get("refdes") or ""),
        str(item.get("pin") or ""),
        str(item.get("rail_name") or ""),
        str(item.get("branch_id") or ""),
    }
    for key in ("affected_rails", "affected_branches", "affected_components", "blocks"):
        values.update(string_values(item.get(key)))
    return {value for value in values if value}


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(manifest.get("manifest_items")) if isinstance(row, dict)]


def manifest_matches(record: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    refdes = str(record.get("refdes")) if record.get("refdes") not in (None, "") else None
    rail_name = str(record.get("rail_name")) if record.get("rail_name") not in (None, "") else None
    branch_id = str(record.get("branch_id")) if record.get("branch_id") not in (None, "") else None
    net_name = str(record.get("net_name")) if record.get("net_name") not in (None, "") else None
    pin = str(record.get("pin")) if record.get("pin") not in (None, "") else None
    matches: list[dict[str, Any]] = []
    for item in manifest_items(manifest):
        if str(item.get("category") or "") not in MANIFEST_CATEGORIES:
            continue
        values = manifest_text_values(item)
        identity_match = (
            (refdes is not None and refdes in values)
            or (rail_name is not None and rail_name in values)
            or (branch_id is not None and branch_id in values)
            or (net_name is not None and net_name in values)
        )
        pin_match = pin is not None and str(item.get("pin") or "") == pin
        if identity_match and (pin is None or not item.get("pin") or pin_match):
            matches.append(item)
    return sorted({item_id(item): item for item in matches if item_id(item)}.values(), key=lambda row: str(item_id(row)))


def linkage(items: list[dict[str, Any]]) -> dict[str, Any]:
    ids = sorted({str(item_id(item)) for item in items if item_id(item)})
    groups = sorted({str(item.get("group_id")) for item in items if isinstance(item.get("group_id"), str)})
    paths = sorted({str(item.get("resolution_path")) for item in items if isinstance(item.get("resolution_path"), str)})
    queues = sorted({str(item.get("resolution_queue") or item.get("resolution_path")) for item in items if isinstance(item.get("resolution_queue") or item.get("resolution_path"), str)})
    return {
        "missing_data_manifest_item_ids": ids,
        "missing_data_group_ids": groups,
        "resolution_path": paths[0] if paths else None,
        "resolution_queue": queues[0] if queues else None,
    }


def component_role_rows(role_resolution: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(role_resolution.get("component_roles")) if isinstance(row, dict)]


def role_rows_for_refdes(role_resolution: dict[str, Any], refdes: str | None) -> list[dict[str, Any]]:
    if not refdes:
        return []
    return [row for row in component_role_rows(role_resolution) if row.get("refdes") == refdes]


def role_target_type(row: dict[str, Any]) -> str | None:
    subtype = canonical_text(row.get("role_subtype") or row.get("component_role") or row.get("component_type"))
    role = canonical_text(row.get("role"))
    if subtype in {"fuse", "polyfuse", "resettable_fuse"}:
        return "fuse"
    if subtype in {"connector", "connector_power_input_or_io", "power_connector"}:
        return "connector"
    if subtype and ("regulator" in subtype or subtype in {"ldo", "buck_converter", "boost_converter"}):
        return "regulator"
    if subtype in {"load_switch", "power_switch", "efuse"}:
        return "load_switch"
    if role == "pass_through":
        return "pass_through_component"
    return None


def branch_rows(branch_topology: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("branches", "branch_records", "branch_topology", "records"):
        rows = branch_topology.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def rail_relationship_rows(rail_relationships: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(rail_relationships.get("relationships")) if isinstance(row, dict)]


def target_exists_in_topology(record: dict[str, Any], role_resolution: dict[str, Any], rail_relationships: dict[str, Any], branch_topology: dict[str, Any]) -> bool | None:
    refdes = record.get("refdes")
    if isinstance(refdes, str) and role_rows_for_refdes(role_resolution, refdes):
        return True
    branch_id = record.get("branch_id")
    if isinstance(branch_id, str) and any(row.get("branch_id") == branch_id for row in branch_rows(branch_topology)):
        return True
    rail_name = record.get("rail_name")
    if isinstance(rail_name, str):
        if any(row.get("rail_name") == rail_name or row.get("rail") == rail_name or row.get("net_name") == rail_name for row in branch_rows(branch_topology)):
            return True
        if any(rail_name in {row.get("rail_name"), row.get("input_rail"), row.get("output_rail"), row.get("source_rail"), row.get("sink_rail")} for row in rail_relationship_rows(rail_relationships)):
            return True
    if role_resolution or rail_relationships or branch_topology:
        return False
    return None


def applies_to_families(target_type: str, rating_name: str, has_pin: bool, role_confirmed: bool) -> list[str]:
    families: set[str] = set()
    fuse_targets = {"fuse", "fuse_pin", "pass_through_component"}
    regulator_targets = {"regulator", "regulator_output", "regulator_input", "load_switch"}
    connector_targets = {"connector_pin"}
    if target_type in fuse_targets and rating_name in {"current_max", "continuous_current_max", "hold_current", "trip_current", "thermal_current_limit"}:
        families.add("fuse_margin")
    if target_type in regulator_targets and rating_name in {"current_max", "output_current_max", "input_current_max", "thermal_current_limit", "package_current_limit"}:
        families.add("regulator_load_margin")
    if target_type in connector_targets and has_pin and rating_name in {"pin_current_max", "current_max", "continuous_current_max", "package_current_limit"}:
        families.add("connector_pin_current_margin")
    if target_type == "connector" and has_pin and rating_name in {"pin_current_max", "current_max", "continuous_current_max", "package_current_limit"}:
        families.add("connector_pin_current_margin")
    if target_type == "component" and role_confirmed:
        # Role-confirmed component ratings can be normalized for a future family,
        # but only after role_resolution explicitly identifies the component role.
        families.update(applies_to_families(role_confirmed_type_for_component(target_type), rating_name, has_pin, False))
    return sorted(families)


def role_confirmed_type_for_component(target_type: str) -> str:
    return target_type


def target_identity_complete(target_type: str, record: dict[str, Any]) -> bool:
    if target_type in {"connector_pin", "fuse_pin"}:
        return isinstance(record.get("refdes"), str) and isinstance(record.get("pin"), str)
    if target_type in {"fuse", "connector", "regulator", "regulator_output", "regulator_input", "load_switch", "pass_through_component", "component"}:
        return isinstance(record.get("refdes"), str)
    if target_type == "rail":
        return isinstance(record.get("rail_name"), str)
    if target_type == "branch":
        return isinstance(record.get("branch_id"), str)
    return False


def reject_record(source_record_id: str | None, reason_code: str, detail: str, original_record: Any, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "source_record_id": source_record_id,
        "reason_code": reason_code,
        "detail": detail,
        "original_record": json_safe(original_record),
        "errors": errors or [detail],
    }


def unresolved_link(
    *,
    source_record_id: str | None,
    reason_code: str,
    record: dict[str, Any],
    detail: str,
    matches: list[dict[str, Any]] | None = None,
    human_review_needed: bool = True,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    link = linkage(matches or [])
    return {
        "unresolved_id": f"unresolved_rating_{safe_id(reason_code)}_{safe_id(source_record_id)}",
        "source_record_id": source_record_id,
        "reason_code": reason_code,
        "target_type": record.get("target_type"),
        "refdes": record.get("refdes"),
        "pin": record.get("pin"),
        "rail_name": record.get("rail_name"),
        "branch_id": record.get("branch_id"),
        "detail": detail,
        "missing_data_manifest_item_ids": link["missing_data_manifest_item_ids"],
        "missing_data_group_ids": link["missing_data_group_ids"],
        "resolution_path": link["resolution_path"],
        "resolution_queue": link["resolution_queue"],
        "human_review_needed": human_review_needed,
        "warnings": warnings or [],
    }


def original_value_and_unit(record: dict[str, Any]) -> tuple[Any, Any]:
    provenance = as_dict(record.get("provenance"))
    return (
        record.get("original_value", provenance.get("original_value", record.get("value"))),
        record.get("original_unit", provenance.get("original_unit", record.get("unit"))),
    )


def normalize_value(value: Any, unit: Any) -> tuple[float | None, str | None, str | None]:
    if not is_number(value):
        return None, None, "invalid_value"
    if float(value) < 0:
        return None, None, "negative_rating"
    normalized_unit = normalize_unit(unit)
    if normalized_unit is None:
        return None, None, "unsupported_unit"
    return float(value) * SUPPORTED_UNITS[normalized_unit], normalized_unit, None


def normalize_rating_record(
    record: dict[str, Any],
    *,
    index: int,
    paths: dict[str, Path | None],
    manifest: dict[str, Any],
    role_resolution: dict[str, Any],
    rail_relationships: dict[str, Any],
    branch_topology: dict[str, Any],
    source_record_cache: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    record = hydrate_from_source_rating(record, source_record_cache)
    source_record_id = str(record.get("record_id") or f"rating_source_{index:06d}")
    target_type = canonical_text(record.get("target_type"))
    original_rating_name = record.get("original_rating_name") or record.get("rating_name") or record.get("normalized_rating_name")
    normalized_rating_name = normalize_rating_name(original_rating_name)
    original_value, original_unit = original_value_and_unit(record)
    value = record.get("value")
    unit = record.get("unit")

    if target_type is None or target_identity(record) is None:
        return None, [reject_record(source_record_id, "missing_target", "rating record is missing explicit target type or target identity", record)], []
    if target_type not in SUPPORTED_TARGET_TYPES:
        return None, [reject_record(source_record_id, "unsupported_record_type", f"unsupported rating target type: {target_type}", record)], []
    if original_rating_name is None:
        return None, [reject_record(source_record_id, "missing_rating_name", "rating record is missing rating_name", record)], []
    if normalized_rating_name not in SUPPORTED_RATING_NAMES:
        return None, [reject_record(source_record_id, "unsupported_rating_name", f"unsupported rating name: {original_rating_name}", record)], []
    if "value" not in record:
        return None, [reject_record(source_record_id, "missing_value", "rating record is missing value", record)], []
    value_a, normalized_unit, reason = normalize_value(value, unit)
    if reason:
        detail = f"rating value cannot be normalized to amps: {reason}"
        return None, [reject_record(source_record_id, reason, detail, record)], []
    assert value_a is not None

    role_confirmed_type: str | None = None
    role_confirmed = False
    target_warnings: list[str] = []
    unresolved: list[dict[str, Any]] = []
    role_rows = role_rows_for_refdes(role_resolution, record.get("refdes") if isinstance(record.get("refdes"), str) else None)
    if len(role_rows) > 1:
        unresolved.append(unresolved_link(
            source_record_id=source_record_id,
            reason_code="ambiguous_target_mapping",
            record=record,
            detail="multiple role-resolution rows match this rating target",
            human_review_needed=True,
        ))
        target_warnings.append("multiple role-resolution rows match this rating target")
    elif role_rows:
        role_confirmed_type = role_target_type(role_rows[0])
        if role_confirmed_type:
            role_confirmed = True
        elif target_type == "component":
            unresolved.append(unresolved_link(
                source_record_id=source_record_id,
                reason_code="target_role_unknown",
                record=record,
                detail="role_resolution does not identify the component role for this component rating",
                human_review_needed=True,
            ))
            target_warnings.append("component role is unknown")

    normalized_target_type = target_type
    if target_type == "component" and role_confirmed_type:
        normalized_target_type = role_confirmed_type

    topology_exists = target_exists_in_topology(record, role_resolution, rail_relationships, branch_topology)
    if topology_exists is False:
        unresolved.append(unresolved_link(
            source_record_id=source_record_id,
            reason_code="target_not_found_in_topology",
            record=record,
            detail="optional topology artifacts do not contain a deterministic match for this rating target",
            human_review_needed=True,
        ))
        target_warnings.append("rating target was not found in optional topology artifacts")

    manifest_matches_for_record = manifest_matches(record, manifest) if manifest else []
    manifest_link = linkage(manifest_matches_for_record)
    if manifest and not manifest_matches_for_record:
        warning = "no matching missing-data manifest item was found for this rating"
        unresolved.append(unresolved_link(
            source_record_id=source_record_id,
            reason_code="manifest_link_not_found",
            record=record,
            detail=warning,
            human_review_needed=True,
            warnings=[warning],
        ))
        target_warnings.append(warning)

    families = applies_to_families(normalized_target_type, normalized_rating_name, isinstance(record.get("pin"), str), role_confirmed)
    identity_complete = target_identity_complete(target_type, record)
    usable = bool(identity_complete and families and not any(row["reason_code"] == "ambiguous_target_mapping" for row in unresolved))
    if target_type == "connector" and normalized_rating_name == "pin_current_max" and not isinstance(record.get("pin"), str):
        usable = False
        target_warnings.append("connector pin rating is not expanded to pins without an explicit pin")

    rating_id = f"rating_{safe_id(normalized_target_type)}_{safe_id(target_identity(record))}_{safe_id(record.get('pin'))}_{safe_id(normalized_rating_name)}_{index:06d}"
    source_artifacts = [row for row in as_list(record.get("source_artifacts")) if isinstance(row, dict)] or [
        source_artifact("current_models_normalized", paths["current_models"], source_record_id, "Normalized PR19 rating record.")
    ]
    normalized = {
        "rating_id": rating_id,
        "source_record_id": source_record_id,
        "target_type": target_type,
        "normalized_target_type": normalized_target_type,
        "refdes": record.get("refdes"),
        "pin": record.get("pin"),
        "rail_name": record.get("rail_name"),
        "branch_id": record.get("branch_id"),
        "net_name": record.get("net_name"),
        "rating_name": str(original_rating_name),
        "normalized_rating_name": normalized_rating_name,
        "value_a": value_a,
        "unit": "A",
        "original_value": original_value,
        "original_unit": original_unit,
        "original_rating_name": original_rating_name,
        "basis": record.get("basis"),
        "source": record.get("source") or "current_models_normalized",
        "confidence": confidence_value(record),
        "evidence_refs": evidence_refs(record),
        "source_artifacts": source_artifacts,
        "usable_for_margin_calculation": usable,
        "human_review_needed": bool(target_warnings or unresolved),
        "applies_to_calculation_families": families,
        "missing_data_manifest_item_ids": manifest_link["missing_data_manifest_item_ids"],
        "missing_data_group_ids": manifest_link["missing_data_group_ids"],
        "resolution_path": manifest_link["resolution_path"],
        "resolution_queue": manifest_link["resolution_queue"],
        "warnings": sorted(set(target_warnings)),
    }
    return normalized, [], unresolved


def build_artifact(
    *,
    project: str,
    paths: dict[str, Path | None],
    current_models: dict[str, Any],
    manifest: dict[str, Any],
    role_resolution: dict[str, Any],
    rail_relationships: dict[str, Any],
    branch_topology: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    normalized_ratings: list[dict[str, Any]] = []
    rejected_ratings: list[dict[str, Any]] = []
    unresolved_links: list[dict[str, Any]] = []
    input_rating_record_count = 0
    ignored_current_record_count = 0
    source_record_cache: dict[str, dict[str, Any]] = {}

    for index, record in enumerate(as_list(current_models.get("normalized_currents")), start=1):
        if not isinstance(record, dict):
            continue
        if record.get("record_type") != "rating":
            ignored_current_record_count += 1
            continue
        input_rating_record_count += 1
        normalized, rejected, unresolved = normalize_rating_record(
            record,
            index=index,
            paths=paths,
            manifest=manifest,
            role_resolution=role_resolution,
            rail_relationships=rail_relationships,
            branch_topology=branch_topology,
            source_record_cache=source_record_cache,
        )
        if normalized:
            normalized_ratings.append(normalized)
        rejected_ratings.extend(rejected)
        unresolved_links.extend(unresolved)

    warnings.extend(sorted({
        warning
        for rating in normalized_ratings
        for warning in as_list(rating.get("warnings"))
        if isinstance(warning, str)
    }))
    warning_count = len(warnings) + sum(len(as_list(row.get("warnings"))) for row in unresolved_links)
    errors: list[str] = []
    summary = {
        "input_rating_record_count": input_rating_record_count,
        "ignored_current_record_count": ignored_current_record_count,
        "normalized_rating_count": len(normalized_ratings),
        "rejected_rating_count": len(rejected_ratings),
        "unresolved_rating_link_count": len(unresolved_links),
        "fuse_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") == "fuse"),
        "connector_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") == "connector"),
        "connector_pin_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") == "connector_pin"),
        "regulator_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") in {"regulator", "regulator_output", "regulator_input"}),
        "branch_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") == "branch"),
        "rail_rating_count": sum(1 for row in normalized_ratings if row.get("normalized_target_type") == "rail"),
        "usable_for_margin_calculation_count": sum(1 for row in normalized_ratings if row.get("usable_for_margin_calculation") is True),
        "human_review_count": sum(1 for row in normalized_ratings if row.get("human_review_needed") is True) + sum(1 for row in unresolved_links if row.get("human_review_needed") is True),
        "error_count": len(errors),
        "warning_count": warning_count,
    }
    return {
        "project": project,
        "generated_at_utc": utc_now(),
        "execution_pass": True,
        "rating_model_ingest_pass": not errors,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts_for(paths),
        "normalized_ratings": sorted(normalized_ratings, key=lambda row: row["rating_id"]),
        "rejected_ratings": sorted(rejected_ratings, key=lambda row: str(row.get("source_record_id"))),
        "unresolved_rating_links": sorted(unresolved_links, key=lambda row: (str(row.get("source_record_id")), str(row.get("reason_code")))),
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


def load_optional_json(path: Path | None, label: str, warnings: list[str]) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        warnings.append(f"optional {label} input missing: {path}")
        return {}
    loaded = load_json(path)
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return loaded


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize explicit rating model data.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--current-models-normalized", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--branch-topology-enriched", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    current_models_path = Path(args.current_models_normalized or default_path("exports/{project}-current-models-normalized.json", project))
    out_path = Path(args.out or default_path("exports/{project}-rating-models-normalized.json", project))
    paths = {
        "current_models": current_models_path,
        "missing_data_manifest": Path(args.missing_data_manifest) if args.missing_data_manifest else None,
        "role_resolution": Path(args.role_resolution) if args.role_resolution else None,
        "rail_relationships": Path(args.rail_relationships) if args.rail_relationships else None,
        "branch_topology": Path(args.branch_topology_enriched) if args.branch_topology_enriched else None,
    }

    try:
        if not current_models_path.exists():
            raise FileNotFoundError(f"missing current-models-normalized JSON: {current_models_path}")
        current_models = load_json(current_models_path)
        if not isinstance(current_models, dict):
            raise ValueError(f"current-models-normalized artifact must be a JSON object: {current_models_path}")
        warnings: list[str] = []
        manifest = load_optional_json(paths["missing_data_manifest"], "missing-data-manifest", warnings)
        role_resolution = load_optional_json(paths["role_resolution"], "role-resolution", warnings)
        rail_relationships = load_optional_json(paths["rail_relationships"], "rail-relationships", warnings)
        branch_topology = load_optional_json(paths["branch_topology"], "branch-topology-enriched", warnings)
        artifact = build_artifact(
            project=project,
            paths=paths,
            current_models=current_models,
            manifest=manifest,
            role_resolution=role_resolution,
            rail_relationships=rail_relationships,
            branch_topology=branch_topology,
            warnings=warnings,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "rating model ingest: "
        f"input={summary['input_rating_record_count']} "
        f"normalized={summary['normalized_rating_count']} "
        f"rejected={summary['rejected_rating_count']} "
        f"unresolved_links={summary['unresolved_rating_link_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["rating_model_ingest_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
