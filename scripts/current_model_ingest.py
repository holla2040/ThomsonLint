#!/usr/bin/env python3
"""Normalize explicit current model data into a deterministic artifact.

PR 19 scope only: ingest explicit current/rating data and preserve it for
later allocation and calculations. This script does not infer current, allocate
current through topology, infer ratings, create findings, or make compliance
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
SUPPORTED_CURRENT_UNITS = {
    "A": 1.0,
    "mA": 1e-3,
    "uA": 1e-6,
    "µA": 1e-6,
}
CURRENT_MODEL_MANIFEST_CATEGORIES = {"branch_current_unknown", "current_model_missing"}
RATING_MANIFEST_CATEGORIES = {"rating_missing"}


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


def normalize_unit(unit: Any) -> str | None:
    if not isinstance(unit, str):
        return None
    compact = unit.strip()
    aliases = {
        "a": "A",
        "ma": "mA",
        "ua": "uA",
        "μa": "µA",
        "µa": "µA",
    }
    return aliases.get(compact.lower())


def normalized_current_value(value: Any, unit: Any) -> tuple[float | None, str | None, str | None]:
    if not is_number(value):
        return None, None, "invalid_value"
    if float(value) < 0:
        return None, None, "negative_current"
    normalized_unit = normalize_unit(unit)
    if normalized_unit is None:
        return None, None, "unsupported_unit"
    return float(value) * SUPPORTED_CURRENT_UNITS[normalized_unit], normalized_unit, None


def evidence_refs(record: dict[str, Any]) -> list[str]:
    return [str(ref) for ref in as_list(record.get("evidence_refs")) if isinstance(ref, str)]


def confidence_value(record: dict[str, Any]) -> float | None:
    value = record.get("confidence")
    return float(value) if is_number(value) else None


def reject_record(record_id: str | None, reason_code: str, detail: str, original_record: Any, errors: list[str] | None = None) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "reason_code": reason_code,
        "detail": detail,
        "original_record": original_record,
        "errors": errors or [detail],
    }


def manifest_items(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    return [item for item in as_list(manifest.get("manifest_items")) if isinstance(item, dict)]


def item_id(item: dict[str, Any]) -> str | None:
    value = item.get("manifest_id") or item.get("id") or item.get("source_missing_data_id")
    return str(value) if value is not None else None


def string_set(values: Any) -> set[str]:
    return {str(value) for value in as_list(values) if value is not None}


def manifest_text_values(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("target_id") or ""),
        str(item.get("normalized_target") or ""),
    }
    values.update(string_set(item.get("affected_rails")))
    values.update(string_set(item.get("affected_branches")))
    values.update(string_set(item.get("affected_components")))
    return {value for value in values if value}


def link_manifest_items(record: dict[str, Any], manifest: dict[str, Any] | None) -> tuple[list[str], list[str], list[str]]:
    matches: list[dict[str, Any]] = []
    record_type = record["record_type"]
    for item in manifest_items(manifest):
        category = str(item.get("category") or "")
        values = manifest_text_values(item)
        if record_type == "branch_current":
            branch_id = record.get("branch_id")
            if category in CURRENT_MODEL_MANIFEST_CATEGORIES and isinstance(branch_id, str) and branch_id in values:
                matches.append(item)
        elif record_type == "rail_current":
            rail_name = record.get("rail_name")
            if category in CURRENT_MODEL_MANIFEST_CATEGORIES and isinstance(rail_name, str) and rail_name in values:
                matches.append(item)
        elif record_type == "component_current":
            refdes = record.get("refdes")
            rail_name = record.get("rail_name")
            ref_match = isinstance(refdes, str) and refdes in values
            rail_match = isinstance(rail_name, str) and rail_name in values
            if category in CURRENT_MODEL_MANIFEST_CATEGORIES and (ref_match or rail_match):
                matches.append(item)
        elif record_type == "rating":
            refdes = record.get("refdes")
            pin = record.get("pin")
            ref_match = isinstance(refdes, str) and refdes in values
            pin_match = isinstance(pin, str) and str(item.get("pin") or "") == pin
            if category in RATING_MANIFEST_CATEGORIES and (ref_match or pin_match):
                matches.append(item)

    matches = sorted({item_id(item): item for item in matches if item_id(item)}.values(), key=lambda row: str(item_id(row)))
    ids = [str(item_id(item)) for item in matches if item_id(item)]
    groups = sorted({str(item.get("group_id")) for item in matches if isinstance(item.get("group_id"), str)})
    warnings: list[str] = []
    if manifest is not None and not ids:
        warnings.append("no matching missing-data manifest item was found for this explicit current record")
    return ids, groups, warnings


def value_from_fields(record: dict[str, Any], implied_field: str, generic_fields: list[str]) -> tuple[Any, Any, dict[str, Any]]:
    if implied_field in record:
        return record.get(implied_field), "A", {"field": implied_field, "unit_implied_by_field": True}
    for field in generic_fields:
        if field in record:
            return record.get(field), record.get("unit") or record.get("current_unit"), {"field": field, "unit_implied_by_field": False}
    return None, None, {"field": implied_field, "unit_implied_by_field": False}


def normalized_record(
    *,
    record_id: str,
    record_type: str,
    target_type: str,
    value: float,
    unit: str,
    original_value: Any,
    original_unit: Any,
    current_type: str | None,
    source_record: dict[str, Any],
    current_model_path: Path,
    usable_for_calculation: bool,
    source_index: int,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_type": record_type,
        "target_type": target_type,
        "branch_id": source_record.get("branch_id"),
        "rail_name": source_record.get("rail_name") or source_record.get("rail"),
        "net_name": source_record.get("net_name"),
        "refdes": source_record.get("refdes"),
        "pin": source_record.get("pin"),
        "value": value,
        "unit": unit,
        "current_type": current_type,
        "basis": source_record.get("basis"),
        "source": "current_model",
        "confidence": confidence_value(source_record),
        "evidence_refs": evidence_refs(source_record),
        "source_artifacts": [
            source_artifact("current_model", current_model_path, f"source_record_{source_index:06d}", "Explicit current model source record.")
        ],
        "usable_for_calculation": usable_for_calculation,
        "human_review_needed": False,
        "missing_data_manifest_item_ids": [],
        "missing_data_group_ids": [],
        "warnings": [],
        "provenance": {
            "original_value": original_value,
            "original_unit": original_unit,
            "normalized_unit": unit,
        },
    }


def normalize_branch_current(record: Any, index: int, current_model_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(record, dict):
        return [], [reject_record(f"cur_branch_current_{index:06d}", "unsupported_record_type", "branch current record must be a JSON object", record)]
    branch_id = record.get("branch_id")
    record_id = f"cur_branch_current_{safe_id(branch_id)}_{index:06d}"
    if not isinstance(branch_id, str) or not branch_id:
        return [], [reject_record(record_id, "missing_target", "branch current record is missing branch_id", record)]
    value, unit, provenance = value_from_fields(record, "branch_current_a", ["branch_current", "current", "value"])
    if value is None:
        return [], [reject_record(record_id, "missing_value", "branch current record is missing a current value", record)]
    normalized, source_unit, reason = normalized_current_value(value, unit)
    if reason:
        return [], [reject_record(record_id, reason, f"branch current value cannot be normalized to amps: {reason}", record)]
    assert normalized is not None
    return [normalized_record(
        record_id=record_id,
        record_type="branch_current",
        target_type="branch",
        value=normalized,
        unit="A",
        original_value=value,
        original_unit=unit if source_unit else provenance.get("field"),
        current_type="requirement",
        source_record=record,
        current_model_path=current_model_path,
        usable_for_calculation=True,
        source_index=index,
    )], []


def normalize_rail_current(record: Any, index: int, current_model_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(record, dict):
        return [], [reject_record(f"cur_rail_current_{index:06d}", "unsupported_record_type", "rail current record must be a JSON object", record)]
    rail_name = record.get("rail_name") or record.get("rail")
    record_id = f"cur_rail_current_{safe_id(rail_name)}_{index:06d}"
    if not isinstance(rail_name, str) or not rail_name:
        return [], [reject_record(record_id, "missing_target", "rail current record is missing rail_name", record)]
    value, unit, provenance = value_from_fields(record, "rail_current_a", ["rail_current", "current", "value"])
    if value is None:
        return [], [reject_record(record_id, "missing_value", "rail current record is missing a current value", record)]
    normalized, source_unit, reason = normalized_current_value(value, unit)
    if reason:
        return [], [reject_record(record_id, reason, f"rail current value cannot be normalized to amps: {reason}", record)]
    assert normalized is not None
    return [normalized_record(
        record_id=record_id,
        record_type="rail_current",
        target_type="rail",
        value=normalized,
        unit="A",
        original_value=value,
        original_unit=unit if source_unit else provenance.get("field"),
        current_type="requirement",
        source_record=record,
        current_model_path=current_model_path,
        usable_for_calculation=False,
        source_index=index,
    )], []


def component_value_fields(record: dict[str, Any]) -> list[tuple[str, str, Any, Any]]:
    rows: list[tuple[str, str, Any, Any]] = []
    if "typ_current_a" in record:
        rows.append(("typ", "typ_current_a", record.get("typ_current_a"), "A"))
    elif "typ_current" in record:
        rows.append(("typ", "typ_current", record.get("typ_current"), record.get("unit") or record.get("current_unit")))
    if "max_current_a" in record:
        rows.append(("max", "max_current_a", record.get("max_current_a"), "A"))
    elif "max_current" in record:
        rows.append(("max", "max_current", record.get("max_current"), record.get("unit") or record.get("current_unit")))
    if not rows and "value" in record:
        rows.append((str(record.get("current_type") or "nominal"), "value", record.get("value"), record.get("unit") or record.get("current_unit")))
    return rows


def normalize_component_current(record: Any, index: int, current_model_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(record, dict):
        return [], [reject_record(f"cur_component_current_{index:06d}", "unsupported_record_type", "component current record must be a JSON object", record)]
    refdes = record.get("refdes")
    record_id_base = f"cur_component_current_{safe_id(refdes)}_{safe_id(record.get('rail_name'))}_{index:06d}"
    if not isinstance(refdes, str) or not refdes:
        return [], [reject_record(record_id_base, "missing_target", "component current record is missing refdes", record)]
    rows = component_value_fields(record)
    if not rows:
        return [], [reject_record(record_id_base, "missing_value", "component current record is missing typ/max/current value", record)]
    normalized_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for current_type, field, value, unit in rows:
        record_id = f"{record_id_base}_{safe_id(current_type)}"
        normalized, _, reason = normalized_current_value(value, unit)
        if reason:
            rejected.append(reject_record(record_id, reason, f"component {field} cannot be normalized to amps: {reason}", record))
            continue
        assert normalized is not None
        normalized_rows.append(normalized_record(
            record_id=record_id,
            record_type="component_current",
            target_type="component",
            value=normalized,
            unit="A",
            original_value=value,
            original_unit=unit,
            current_type=current_type,
            source_record=record,
            current_model_path=current_model_path,
            usable_for_calculation=False,
            source_index=index,
        ))
    return normalized_rows, rejected


def rating_current_type(record: dict[str, Any]) -> str | None:
    name = str(record.get("rating_name") or "").lower()
    if "max" in name:
        return "max"
    if "typ" in name:
        return "typ"
    if "nominal" in name:
        return "nominal"
    return None


def normalize_rating(record: Any, index: int, current_model_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(record, dict):
        return [], [reject_record(f"cur_rating_{index:06d}", "unsupported_record_type", "rating record must be a JSON object", record)]
    target_type = record.get("target_type")
    target = record.get("refdes") or record.get("branch_id") or record.get("rail_name") or record.get("target_id")
    record_id = f"cur_rating_{safe_id(target_type)}_{safe_id(target)}_{safe_id(record.get('pin'))}_{index:06d}"
    if not isinstance(target_type, str) or not target_type or target is None:
        return [], [reject_record(record_id, "missing_target", "rating record is missing target_type or target identity", record)]
    if "value" not in record:
        return [], [reject_record(record_id, "missing_value", "rating record is missing value", record)]
    normalized, _, reason = normalized_current_value(record.get("value"), record.get("unit"))
    if reason:
        return [], [reject_record(record_id, reason, f"rating value cannot be normalized to amps: {reason}", record)]
    assert normalized is not None
    return [normalized_record(
        record_id=record_id,
        record_type="rating",
        target_type=target_type,
        value=normalized,
        unit="A",
        original_value=record.get("value"),
        original_unit=record.get("unit"),
        current_type=rating_current_type(record),
        source_record=record,
        current_model_path=current_model_path,
        usable_for_calculation=False,
        source_index=index,
    )], []


def normalize_current_model(
    *,
    project: str,
    current_model_path: Path,
    missing_data_manifest_path: Path | None,
    branch_topology_enriched_path: Path | None,
    rail_relationships_path: Path | None,
    role_resolution_path: Path | None,
) -> dict[str, Any]:
    current_model = load_json(current_model_path)
    if not isinstance(current_model, dict):
        raise ValueError(f"current-model artifact must be a JSON object: {current_model_path}")

    warnings: list[str] = []
    errors: list[str] = []
    manifest: dict[str, Any] | None = None
    if missing_data_manifest_path is not None:
        if missing_data_manifest_path.exists():
            loaded = load_json(missing_data_manifest_path)
            if not isinstance(loaded, dict):
                raise ValueError(f"missing-data-manifest artifact must be a JSON object: {missing_data_manifest_path}")
            manifest = loaded
        else:
            warnings.append(f"optional missing-data-manifest input missing: {missing_data_manifest_path}")

    optional_artifacts = [
        source_artifact("branch_topology_enriched", branch_topology_enriched_path, None, "Optional context; not used for current inference.") if branch_topology_enriched_path else None,
        source_artifact("rail_relationships", rail_relationships_path, None, "Optional context; not used for current allocation.") if rail_relationships_path else None,
        source_artifact("role_resolution", role_resolution_path, None, "Optional context; not used for current inference.") if role_resolution_path else None,
        source_artifact("missing_data_manifest", missing_data_manifest_path, None, "Optional best-effort linkage context.") if missing_data_manifest_path else None,
    ]

    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    source_index = 0
    input_record_count = 0
    for rows, normalizer in (
        (as_list(current_model.get("branch_currents")), normalize_branch_current),
        (as_list(current_model.get("rail_currents")), normalize_rail_current),
        (as_list(current_model.get("component_currents")), normalize_component_current),
        (as_list(current_model.get("ratings")), normalize_rating),
    ):
        for row in rows:
            input_record_count += 1
            source_index += 1
            rows_normalized, rows_rejected = normalizer(row, source_index, current_model_path)
            normalized.extend(rows_normalized)
            rejected.extend(rows_rejected)

    unresolved_references: list[dict[str, Any]] = []
    for record in normalized:
        item_ids, group_ids, link_warnings = link_manifest_items(record, manifest)
        record["missing_data_manifest_item_ids"] = item_ids
        record["missing_data_group_ids"] = group_ids
        record["warnings"].extend(link_warnings)
        if link_warnings:
            record["human_review_needed"] = True
            for warning in link_warnings:
                unresolved_references.append({
                    "record_id": record["record_id"],
                    "reference_type": "missing_data_manifest",
                    "detail": warning,
                })

    all_record_warnings = [warning for record in normalized for warning in as_list(record.get("warnings"))]
    warnings.extend(all_record_warnings)
    summary = {
        "input_record_count": input_record_count,
        "normalized_count": len(normalized),
        "rejected_count": len(rejected),
        "branch_current_count": sum(1 for record in normalized if record.get("record_type") == "branch_current"),
        "rail_current_count": sum(1 for record in normalized if record.get("record_type") == "rail_current"),
        "component_current_count": sum(1 for record in normalized if record.get("record_type") == "component_current"),
        "rating_count": sum(1 for record in normalized if record.get("record_type") == "rating"),
        "directly_usable_branch_current_count": sum(1 for record in normalized if record.get("record_type") == "branch_current" and record.get("usable_for_calculation") is True),
        "human_review_count": sum(1 for record in normalized if record.get("human_review_needed") is True),
        "unresolved_reference_count": len(unresolved_references),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    return {
        "project": project,
        "generated_at_utc": utc_now(),
        "execution_pass": True,
        "current_model_ingest_pass": not errors,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": [
            source_artifact("current_model", current_model_path, None, "Explicit PR19 current model input.")
        ] + [artifact for artifact in optional_artifacts if artifact is not None],
        "normalized_currents": sorted(normalized, key=lambda record: record["record_id"]),
        "rejected_currents": sorted(rejected, key=lambda record: str(record.get("record_id"))),
        "unresolved_references": sorted(unresolved_references, key=lambda record: (record["record_id"], record["detail"])),
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize explicit current model data.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--current-model", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--branch-topology-enriched", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--role-resolution", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    current_model_path = Path(args.current_model or default_path("exports/{project}-current-model.json", project))
    out_path = Path(args.out or default_path("exports/{project}-current-models-normalized.json", project))
    manifest_path = Path(args.missing_data_manifest) if args.missing_data_manifest else None
    branch_path = Path(args.branch_topology_enriched) if args.branch_topology_enriched else None
    rail_path = Path(args.rail_relationships) if args.rail_relationships else None
    role_path = Path(args.role_resolution) if args.role_resolution else None

    try:
        if not current_model_path.exists():
            raise FileNotFoundError(f"missing current-model JSON: {current_model_path}")
        artifact = normalize_current_model(
            project=project,
            current_model_path=current_model_path,
            missing_data_manifest_path=manifest_path,
            branch_topology_enriched_path=branch_path,
            rail_relationships_path=rail_path,
            role_resolution_path=role_path,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "current model ingest: "
        f"input={summary['input_record_count']} "
        f"normalized={summary['normalized_count']} "
        f"rejected={summary['rejected_count']} "
        f"usable_branch={summary['directly_usable_branch_current_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["current_model_ingest_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
