#!/usr/bin/env python3
"""Create evidence-only topology-aware geometry review records.

PR 10 scope only: combine topology, copper association, branch topology, and
stackup artifacts into deterministic geometry evidence. This script does not
calculate ampacity, current density, thermal rise, voltage drop, compliance, or
final findings.
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
NON_COPPER_LAYER_TOKENS = {
    "MASK",
    "SOLDER_MASK",
    "SILKSCREEN",
    "PASTE",
    "ASSEMBLY",
    "DOCUMENT",
    "DRILL",
    "OUTLINE",
    "DIELECTRIC",
}


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


def key_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def safe_slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def first_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    alias_keys = {key_name(alias) for alias in aliases}
    for key, value in row.items():
        if key_name(key) in alias_keys and value not in (None, ""):
            return value
    return None


def is_copper_layer(layer: dict[str, Any]) -> bool:
    material = str(layer.get("material") or "").upper()
    function = str(layer.get("function") or "").upper()
    layer_type = str(layer.get("type") or "").upper()
    if {material, function, layer_type}.intersection(NON_COPPER_LAYER_TOKENS):
        return False
    return material == "COPPER" or function in {"CONDUCTOR", "PLANE"} or layer_type in {"CONDUCTOR", "PLANE"}


def normalize_stackup_layers(stackup: dict[str, Any]) -> list[dict[str, Any]]:
    source_rows: list[Any] = []
    for key in ("physical_stackup", "layer_stack", "layers"):
        value = stackup.get(key)
        if isinstance(value, list) and value:
            source_rows = value
            break

    layers: list[dict[str, Any]] = []
    for idx, raw in enumerate(source_rows, 1):
        if not isinstance(raw, dict):
            continue
        name = first_value(raw, ("name", "layer", "layer_name", "layerRef"))
        layer = {
            "layer_name": str(name) if name is not None else f"layer_{idx:06d}",
            "sequence": raw.get("sequence") if isinstance(raw.get("sequence"), int) else idx,
            "function": raw.get("function"),
            "side": raw.get("side"),
            "type": raw.get("type"),
            "material": raw.get("material"),
            "copper_thickness": raw.get("copper_thickness", raw.get("thickness")),
            "is_copper": False,
        }
        layer["is_copper"] = is_copper_layer(layer)
        layers.append(layer)
    return layers


def stackup_index(stackup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layers = normalize_stackup_layers(stackup)
    by_key: dict[str, dict[str, Any]] = {}
    for layer in layers:
        name = layer.get("layer_name")
        if isinstance(name, str):
            by_key[name] = layer
            by_key[name.upper()] = layer
            by_key[safe_slug(name)] = layer
    return by_key


def lookup_layer(index: dict[str, dict[str, Any]], layer_name: Any) -> dict[str, Any] | None:
    if not isinstance(layer_name, str) or not layer_name:
        return None
    return index.get(layer_name) or index.get(layer_name.upper()) or index.get(safe_slug(layer_name))


def review_id(branch_id: str) -> str:
    return f"geo_{branch_id}"


def evidence_id(branch_id: str, evidence_type: str) -> str:
    return f"ev_geo_{branch_id}_{safe_slug(evidence_type)}"


def unresolved_id(branch_id: str, unresolved_type: str) -> str:
    return f"unres_geo_{branch_id}_{safe_slug(unresolved_type)}"


def evidence_record(
    branch: dict[str, Any],
    evidence_type: str,
    value: Any,
    unit: str | None,
    source: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id(str(branch.get("branch_id")), evidence_type),
        "branch_id": branch.get("branch_id"),
        "net_name": branch.get("net_name"),
        "evidence_type": evidence_type,
        "value": value,
        "unit": unit,
        "source": source,
        "notes": notes,
    }


def unresolved_record(branch: dict[str, Any], unresolved_type: str, notes: str) -> dict[str, Any]:
    return {
        "id": unresolved_id(str(branch.get("branch_id")), unresolved_type),
        "type": unresolved_type,
        "branch_id": branch.get("branch_id"),
        "net_name": branch.get("net_name"),
        "human_review_needed": True,
        "notes": notes,
    }


def branch_geometry(branch: dict[str, Any]) -> dict[str, Any]:
    geometry = branch.get("geometry_summary")
    if not isinstance(geometry, dict):
        geometry = {}
    return {
        "units": geometry.get("units"),
        "known_width_count": geometry.get("known_width_count", 0),
        "min_width": geometry.get("min_width"),
        "max_width": geometry.get("max_width"),
        "total_length": geometry.get("total_length"),
        "total_area": geometry.get("total_area"),
        "bbox": geometry.get("bbox"),
        "has_trace_like_geometry": bool(geometry.get("has_trace_like_geometry")),
        "has_plane_like_geometry": bool(geometry.get("has_plane_like_geometry")),
        "has_vias": bool(geometry.get("has_vias")),
    }


def current_context(branch: dict[str, Any]) -> dict[str, Any]:
    basis = branch.get("current_basis") if isinstance(branch.get("current_basis"), str) else "unresolved"
    estimated_current = branch.get("estimated_current_a")
    return {
        "current_model_ref": branch.get("current_model_ref"),
        "estimated_current_a": estimated_current,
        "current_basis": basis,
        "current_known": estimated_current is not None and basis != "unresolved",
    }


def stackup_context(layer_name: Any, layer: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "primary_layer": layer_name,
        "is_copper_layer": bool(layer and layer.get("is_copper")),
        "copper_thickness": layer.get("copper_thickness") if layer else None,
        "layer_function": layer.get("function") if layer else None,
        "side": layer.get("side") if layer else None,
    }


def geometry_unresolved(branch: dict[str, Any], geometry: dict[str, Any]) -> list[dict[str, Any]]:
    branch_type = branch.get("branch_type")
    unresolved: list[dict[str, Any]] = []
    if branch_type == "trace_group":
        if not geometry.get("known_width_count"):
            unresolved.append(unresolved_record(branch, "missing_width", "Trace branch has no known width evidence."))
        if geometry.get("total_length") is None:
            unresolved.append(unresolved_record(branch, "missing_length", "Trace branch has no total length evidence."))
    elif branch_type == "plane_region":
        if geometry.get("total_area") is None and geometry.get("bbox") is None:
            unresolved.append(unresolved_record(branch, "missing_area", "Plane branch has no area or bbox evidence."))
    elif branch_type == "via_cluster":
        if not geometry.get("known_width_count") and geometry.get("min_width") is None:
            unresolved.append(unresolved_record(branch, "missing_width", "Via cluster has no width or diameter evidence."))
    elif branch_type == "pad_group":
        if geometry.get("total_area") is None and geometry.get("bbox") is None:
            unresolved.append(unresolved_record(branch, "missing_area", "Pad group has no area or bbox evidence."))
    elif branch_type in {"mixed_net_group", "unknown"}:
        unresolved.append(unresolved_record(branch, "mixed_unknown", "Branch has mixed or unknown geometry type."))
    return unresolved


def build_unresolved(branch: dict[str, Any], layer: dict[str, Any] | None, geometry: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    if branch.get("topology_net_type") == "power" and not ctx["current_known"]:
        unresolved.append(unresolved_record(branch, "current_unknown", "Power branch current context is unresolved."))
    if not branch.get("layer"):
        unresolved.append(unresolved_record(branch, "missing_layer", "Branch does not identify a primary layer."))
    elif layer is None:
        unresolved.append(unresolved_record(branch, "missing_layer", "Branch layer is not present in the stackup artifact."))
    elif not layer.get("is_copper"):
        unresolved.append(unresolved_record(branch, "non_copper_layer", "Branch primary layer is not classified as copper."))
    unresolved.extend(geometry_unresolved(branch, geometry))

    for flag in branch.get("unresolved_flags", []):
        if isinstance(flag, str):
            unresolved.append(unresolved_record(branch, f"upstream_{flag}", f"Upstream branch topology unresolved flag: {flag}."))

    deduped: dict[str, dict[str, Any]] = {}
    for item in unresolved:
        deduped[item["id"]] = item
    return list(deduped.values())


def classify_review_status(branch: dict[str, Any], unresolved: list[dict[str, Any]], ctx: dict[str, Any]) -> str:
    unresolved_types = {item.get("type") for item in unresolved}
    if branch.get("topology_net_type") == "power" and not ctx["current_known"]:
        return "needs_current_model"
    if unresolved_types.intersection({"missing_layer", "non_copper_layer", "missing_width", "missing_length", "missing_area", "mixed_unknown"}):
        return "geometry_incomplete"
    if branch.get("topology_net_type") in {"power", "ground", "chassis", "earth"}:
        return "ready_for_later_calculation"
    return "evidence_only"


def build_evidence(branch: dict[str, Any], layer: dict[str, Any] | None, geometry: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    unit = geometry.get("units")
    evidence = [
        evidence_record(branch, "object_count", branch.get("object_count", 0), None, "branch_topology", "Branch copper object count."),
        evidence_record(branch, "current_context", ctx, None, "branch_topology", "Branch current context copied without calculation."),
    ]
    if geometry.get("known_width_count"):
        evidence.append(evidence_record(branch, "width", {"min_width": geometry.get("min_width"), "max_width": geometry.get("max_width")}, unit, "branch_topology", "Known branch width range."))
    if geometry.get("total_length") is not None:
        evidence.append(evidence_record(branch, "length", geometry.get("total_length"), unit, "branch_topology", "Known branch total length."))
    if geometry.get("total_area") is not None:
        evidence.append(evidence_record(branch, "area", geometry.get("total_area"), unit, "branch_topology", "Known branch total area."))
    if geometry.get("bbox") is not None:
        evidence.append(evidence_record(branch, "bbox", geometry.get("bbox"), unit, "branch_topology", "Known branch bounding box."))
    if layer is not None:
        evidence.append(evidence_record(branch, "stackup", {
            "layer_name": layer.get("layer_name"),
            "function": layer.get("function"),
            "side": layer.get("side"),
            "is_copper": layer.get("is_copper"),
        }, None, "stackup", "Stackup layer classification for branch primary layer."))
        if layer.get("copper_thickness") is not None:
            evidence.append(evidence_record(branch, "stackup_copper_thickness", layer.get("copper_thickness"), None, "stackup", "Copper thickness copied from stackup artifact."))
    else:
        evidence.append(evidence_record(branch, "layer_missing", branch.get("layer"), None, "stackup", "Branch primary layer was not found in stackup."))
    return evidence


def build_review_record(branch: dict[str, Any], layer: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    geometry = branch_geometry(branch)
    ctx = current_context(branch)
    unresolved = build_unresolved(branch, layer, geometry, ctx)
    evidence = build_evidence(branch, layer, geometry, ctx)
    status = classify_review_status(branch, unresolved, ctx)
    record_warnings = [item["notes"] for item in unresolved]
    record = {
        "review_id": review_id(str(branch.get("branch_id"))),
        "branch_id": branch.get("branch_id"),
        "net_name": branch.get("net_name"),
        "topology_net_type": branch.get("topology_net_type"),
        "branch_type": branch.get("branch_type"),
        "layer": branch.get("layer"),
        "layers": branch.get("layers") if isinstance(branch.get("layers"), list) else [],
        "object_count": branch.get("object_count", 0),
        "geometry": geometry,
        "stackup": stackup_context(branch.get("layer"), layer),
        "current_context": ctx,
        "review_status": status,
        "evidence": [item["evidence_id"] for item in evidence],
        "unresolved_flags": sorted({item["type"] for item in unresolved}),
        "warnings": record_warnings,
    }
    return record, evidence, unresolved


def summarize(
    branches: list[dict[str, Any]],
    records: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    warnings: list[str],
    errors: list[str],
) -> dict[str, int]:
    def branch_count(branch_type: str) -> int:
        return sum(1 for branch in branches if branch.get("branch_type") == branch_type)

    def record_net_count(types: set[str]) -> int:
        return sum(1 for record in records if record.get("topology_net_type") in types)

    return {
        "branch_count": len(branches),
        "review_record_count": len(records),
        "power_branch_review_count": record_net_count({"power"}),
        "ground_branch_review_count": record_net_count({"ground", "chassis", "earth"}),
        "signal_branch_review_count": record_net_count({"signal"}),
        "trace_group_count": branch_count("trace_group"),
        "plane_region_count": branch_count("plane_region"),
        "via_cluster_count": branch_count("via_cluster"),
        "pad_group_count": branch_count("pad_group"),
        "current_known_branch_count": sum(1 for record in records if record["current_context"]["current_known"]),
        "current_unknown_branch_count": sum(1 for record in records if not record["current_context"]["current_known"]),
        "width_known_branch_count": sum(1 for record in records if record["geometry"].get("known_width_count")),
        "geometry_incomplete_branch_count": sum(1 for record in records if record.get("review_status") == "geometry_incomplete"),
        "stackup_copper_layer_count": sum(1 for layer in layers if layer.get("is_copper")),
        "evidence_record_count": len(evidence),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }


def build_artifact(
    project: str,
    topology_path: Path,
    copper_path: Path,
    branch_path: Path,
    stackup_path: Path,
    *,
    strict: bool,
) -> dict[str, Any]:
    topology = load_json(topology_path)
    copper_association = load_json(copper_path)
    branch_topology = load_json(branch_path)
    stackup = load_json(stackup_path)
    for label, value, path in (
        ("topology", topology, topology_path),
        ("copper association", copper_association, copper_path),
        ("branch topology", branch_topology, branch_path),
        ("stackup", stackup, stackup_path),
    ):
        if not isinstance(value, dict):
            raise ValueError(f"{label} JSON must be an object: {path}")

    branches = [row for row in branch_topology.get("branches", []) if isinstance(row, dict)]
    layers = normalize_stackup_layers(stackup)
    layer_index = stackup_index(stackup)
    warnings: list[str] = []
    errors: list[str] = []
    review_records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    if not layers:
        warnings.append("no stackup layers extracted")

    for branch in sorted(branches, key=lambda row: str(row.get("branch_id") or "")):
        layer = lookup_layer(layer_index, branch.get("layer"))
        record, evidence, items = build_review_record(branch, layer)
        review_records.append(record)
        evidence_records.extend(evidence)
        unresolved.extend(items)

    unresolved_by_id = {item["id"]: item for item in unresolved}
    unresolved = list(unresolved_by_id.values())
    if unresolved:
        warnings.append(f"{len(unresolved)} unresolved topology geometry review item(s)")

    if strict:
        unknown_current = sorted(
            record["branch_id"]
            for record in review_records
            if record.get("topology_net_type") == "power" and not record["current_context"]["current_known"]
        )
        if unknown_current:
            errors.append(f"strict mode: power branch current unknown: {', '.join(unknown_current[:20])}")
        power_trace_missing = sorted(
            record["branch_id"]
            for record in review_records
            if record.get("topology_net_type") == "power"
            and record.get("branch_type") == "trace_group"
            and (not record["geometry"].get("known_width_count") or record["geometry"].get("total_length") is None)
        )
        if power_trace_missing:
            errors.append(f"strict mode: power trace branch missing width/length: {', '.join(power_trace_missing[:20])}")
        power_layer_issue = sorted(
            record["branch_id"]
            for record in review_records
            if record.get("topology_net_type") == "power"
            and (not record["stackup"].get("primary_layer") or not record["stackup"].get("is_copper_layer"))
        )
        if power_layer_issue:
            errors.append(f"strict mode: power branch on missing/non-copper layer: {', '.join(power_layer_issue[:20])}")

    summary = summarize(branches, review_records, evidence_records, layers, warnings, errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "topology": str(topology_path),
            "copper_association": str(copper_path),
            "branch_topology": str(branch_path),
            "stackup": str(stackup_path),
        },
        "summary": summary,
        "review_records": review_records,
        "evidence_records": evidence_records,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "geometry_review_pass": not errors,
        "human_review_needed": bool(unresolved or warnings or errors),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create topology-aware geometry review evidence.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--copper-association", default=None)
    parser.add_argument("--branch-topology", default=None)
    parser.add_argument("--stackup", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    topology_path = Path(args.topology or default_path("exports/{project}-topology-map.json", project))
    copper_path = Path(args.copper_association or default_path("exports/{project}-copper-net-association.json", project))
    branch_path = Path(args.branch_topology or default_path("exports/{project}-branch-topology.json", project))
    stackup_path = Path(args.stackup or default_path("exports/{project}-thomson-export-stack.json", project))
    out_path = Path(args.out or default_path("exports/{project}-topology-geometry-review.json", project))

    try:
        for label, path in (
            ("topology", topology_path),
            ("copper association", copper_path),
            ("branch topology", branch_path),
            ("stackup", stackup_path),
        ):
            if not path.exists():
                raise FileNotFoundError(f"missing {label} JSON: {path}")
        artifact = build_artifact(project, topology_path, copper_path, branch_path, stackup_path, strict=args.strict)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology geometry review: "
        f"records={summary['review_record_count']} "
        f"evidence={summary['evidence_record_count']} "
        f"unresolved={len(artifact['unresolved'])} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["geometry_review_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
