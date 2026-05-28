#!/usr/bin/env python3
"""Build conservative branch topology candidates from copper associations.

PR 9 scope only: group copper objects by net/layer/object-family so later
topology-aware checks have deterministic branch candidates. This script does not
solve routed paths, infer current from geometry, calculate ampacity, compute
current density, estimate voltage drop, run thermal checks, or create findings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"

TRACE_TYPES = {"trace", "route", "track", "segment"}
PLANE_TYPES = {"plane", "polygon", "region", "copper_shape"}
VIA_TYPES = {"via"}
PAD_TYPES = {"pad", "land"}


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


def safe_slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def safe_branch_id(net_name: str, layer: str | None, family: str, index: int) -> str:
    return f"br_{safe_slug(net_name)}_{safe_slug(layer or 'unknown_layer')}_{safe_slug(family)}_{index:06d}"


def to_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def topology_indexes(topology: dict[str, Any]) -> dict[str, Any]:
    nets = {
        row.get("net_name"): row.get("net_type")
        for row in topology.get("nets", [])
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }
    power_rails = {
        row.get("net_name")
        for row in topology.get("power_rails", [])
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }

    source_refs_by_net: dict[str, list[str]] = defaultdict(list)
    for node in topology.get("source_nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("net_name"), str):
            continue
        ref = node.get("node_id") or node.get("refdes")
        if isinstance(ref, str) and ref not in source_refs_by_net[node["net_name"]]:
            source_refs_by_net[node["net_name"]].append(ref)

    sink_refs_by_net: dict[str, list[str]] = defaultdict(list)
    sink_current_by_net: dict[str, str] = {}
    for node in topology.get("sink_nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("net_name"), str):
            continue
        ref = node.get("node_id") or node.get("refdes")
        if isinstance(ref, str) and ref not in sink_refs_by_net[node["net_name"]]:
            sink_refs_by_net[node["net_name"]].append(ref)
        current_ref = node.get("current_model_ref")
        if isinstance(current_ref, str):
            sink_current_by_net.setdefault(node["net_name"], current_ref)

    current_models_by_id = {
        model.get("model_id"): model
        for model in topology.get("current_models", [])
        if isinstance(model, dict) and isinstance(model.get("model_id"), str)
    }
    rail_current_by_net: dict[str, str] = {}
    for model_id, model in current_models_by_id.items():
        target = model.get("target")
        if isinstance(target, str) and target.startswith("rail:"):
            rail_current_by_net[target[len("rail:"):]] = model_id

    return {
        "nets": nets,
        "power_rails": power_rails,
        "source_refs_by_net": source_refs_by_net,
        "sink_refs_by_net": sink_refs_by_net,
        "sink_current_by_net": sink_current_by_net,
        "rail_current_by_net": rail_current_by_net,
        "current_models_by_id": current_models_by_id,
    }


def object_family(copper_object: dict[str, Any]) -> str:
    obj_type = str(copper_object.get("object_type") or "").lower()
    geometry = copper_object.get("geometry") if isinstance(copper_object.get("geometry"), dict) else {}
    if obj_type in TRACE_TYPES:
        return "trace_group"
    if obj_type in PLANE_TYPES or geometry.get("shape") == "polygon":
        return "plane_region"
    if obj_type in VIA_TYPES:
        return "via_cluster"
    if obj_type in PAD_TYPES:
        return "pad_group"
    if not obj_type:
        return "unknown"
    return "unknown"


def bbox_union(bboxes: list[dict[str, Any]]) -> dict[str, float] | None:
    parsed = []
    for bbox in bboxes:
        if not isinstance(bbox, dict):
            continue
        min_x = to_number(bbox.get("min_x"))
        min_y = to_number(bbox.get("min_y"))
        max_x = to_number(bbox.get("max_x"))
        max_y = to_number(bbox.get("max_y"))
        if None not in (min_x, min_y, max_x, max_y):
            parsed.append((min_x, min_y, max_x, max_y))
    if not parsed:
        return None
    return {
        "min_x": min(item[0] for item in parsed),
        "min_y": min(item[1] for item in parsed),
        "max_x": max(item[2] for item in parsed),
        "max_y": max(item[3] for item in parsed),
    }


def aggregate_geometry(objects: list[dict[str, Any]]) -> dict[str, Any]:
    geometries = [obj.get("geometry") for obj in objects if isinstance(obj.get("geometry"), dict)]
    widths = [to_number(geom.get("width")) for geom in geometries]
    widths = [value for value in widths if value is not None]
    lengths = [to_number(geom.get("length")) for geom in geometries]
    lengths = [value for value in lengths if value is not None]
    areas = [to_number(geom.get("area")) for geom in geometries]
    areas = [value for value in areas if value is not None]
    units = next((geom.get("units") for geom in geometries if geom.get("units")), None)
    families = {object_family(obj) for obj in objects}
    return {
        "units": units,
        "known_width_count": len(widths),
        "min_width": min(widths) if widths else None,
        "max_width": max(widths) if widths else None,
        "total_length": sum(lengths) if lengths else None,
        "total_area": sum(areas) if areas else None,
        "bbox": bbox_union([geom.get("bbox") for geom in geometries if isinstance(geom.get("bbox"), dict)]),
        "has_trace_like_geometry": "trace_group" in families,
        "has_plane_like_geometry": "plane_region" in families,
        "has_vias": "via_cluster" in families,
    }


def association_basis(objects: list[dict[str, Any]]) -> str:
    bases = {obj.get("association_basis") for obj in objects}
    bases.discard(None)
    if not bases:
        return "unknown"
    if bases == {"explicit_net"}:
        return "explicit_net_group"
    if bases.issubset({"pin_net_from_topology", "component_pin"}):
        return "pin_net_group"
    if "unknown" in bases:
        return "unknown"
    return "mixed_association"


def associated_objects(copper_association: dict[str, Any], topology_net_names: set[str]) -> list[dict[str, Any]]:
    objects = []
    for obj in copper_association.get("copper_objects", []):
        if not isinstance(obj, dict):
            continue
        if obj.get("association_basis") == "unknown":
            continue
        net_name = obj.get("net_name")
        if isinstance(net_name, str) and net_name in topology_net_names:
            objects.append(obj)
    return objects


def group_copper_objects(copper_objects: list[dict[str, Any]]) -> dict[tuple[str, str | None, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for obj in copper_objects:
        net_name = obj.get("net_name")
        if not isinstance(net_name, str):
            continue
        family = object_family(obj)
        layer = obj.get("layer") if isinstance(obj.get("layer"), str) and obj.get("layer") else None
        if layer is None or family == "unknown":
            family = "mixed_net_group" if layer is None else "unknown"
        groups[(net_name, layer, family)].append(obj)
    return groups


def choose_current_model_ref(net_name: str, topo: dict[str, Any]) -> tuple[str | None, str]:
    model_id = topo["rail_current_by_net"].get(net_name) or topo["sink_current_by_net"].get(net_name)
    if not model_id:
        return None, "unresolved"
    model = topo["current_models_by_id"].get(model_id)
    if not isinstance(model, dict):
        return model_id, "unresolved"
    basis = model.get("basis")
    return model_id, basis if isinstance(basis, str) else "unresolved"


def unresolved_item(
    item_id: str,
    item_type: str,
    *,
    net_name: str | None = None,
    branch_id: str | None = None,
    object_id: str | None = None,
    notes: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "net_name": net_name,
        "branch_id": branch_id,
        "object_id": object_id,
        "human_review_needed": True,
        "notes": notes,
    }


def build_branches(topology: dict[str, Any], copper_association: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[dict[str, Any]]]:
    topo = topology_indexes(topology)
    copper_objects = associated_objects(copper_association, set(topo["nets"]))
    groups = group_copper_objects(copper_objects)
    group_counts: Counter[tuple[str, str | None, str]] = Counter()
    branches: list[dict[str, Any]] = []
    net_branch_index: dict[str, list[str]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []

    for key in sorted(groups, key=lambda item: (item[0], item[1] or "", item[2])):
        net_name, layer, family = key
        objects = sorted(groups[key], key=lambda obj: str(obj.get("object_id") or ""))
        group_counts[key] += 1
        branch_id = safe_branch_id(net_name, layer, family, group_counts[key])
        net_type = topo["nets"].get(net_name, "unknown")
        source_refs = sorted(topo["source_refs_by_net"].get(net_name, []))
        sink_refs = sorted(topo["sink_refs_by_net"].get(net_name, []))
        current_model_ref, current_basis = choose_current_model_ref(net_name, topo)
        geometry_summary = aggregate_geometry(objects)
        pin_refs = sorted({obj.get("pin_ref") for obj in objects if isinstance(obj.get("pin_ref"), str)})
        branch_flags: list[str] = []

        if net_type == "power" and current_basis == "unresolved":
            branch_flags.append("branch_current_unknown")
            unresolved.append(unresolved_item(
                f"unres_{branch_id}_current_unknown",
                "branch_current_unknown",
                net_name=net_name,
                branch_id=branch_id,
                notes="Power branch has no resolved current model; current remains unresolved.",
            ))
        if net_type == "power" and (not source_refs or not sink_refs):
            branch_flags.append("source_sink_not_resolved")
            unresolved.append(unresolved_item(
                f"unres_{branch_id}_source_sink",
                "source_sink_not_resolved",
                net_name=net_name,
                branch_id=branch_id,
                notes="Power branch source/sink ordering is not deterministically resolved.",
            ))
        if family in {"mixed_net_group", "unknown"}:
            branch_flags.append("mixed_or_unknown_grouping")
            unresolved.append(unresolved_item(
                f"unres_{branch_id}_mixed_grouping",
                "mixed_or_unknown_grouping",
                net_name=net_name,
                branch_id=branch_id,
                notes="Branch grouping used mixed or unknown copper object metadata.",
            ))

        for obj in objects:
            object_id = obj.get("object_id")
            geometry = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else None
            if not obj.get("layer"):
                branch_flags.append("missing_layer")
                unresolved.append(unresolved_item(
                    f"unres_{safe_slug(object_id)}_missing_layer",
                    "missing_layer",
                    net_name=net_name,
                    branch_id=branch_id,
                    object_id=object_id if isinstance(object_id, str) else None,
                    notes="Associated copper object does not include a layer.",
                ))
            if not geometry or geometry.get("available") is not True:
                branch_flags.append("missing_geometry")
                unresolved.append(unresolved_item(
                    f"unres_{safe_slug(object_id)}_missing_geometry",
                    "missing_geometry",
                    net_name=net_name,
                    branch_id=branch_id,
                    object_id=object_id if isinstance(object_id, str) else None,
                    notes="Associated copper object does not include available geometry metadata.",
                ))

        branch = {
            "branch_id": branch_id,
            "net_name": net_name,
            "topology_net_type": net_type,
            "branch_type": family,
            "layer": layer,
            "layers": sorted({obj.get("layer") for obj in objects if isinstance(obj.get("layer"), str)}),
            "copper_object_refs": [obj.get("object_id") for obj in objects if isinstance(obj.get("object_id"), str)],
            "pin_refs": pin_refs,
            "source_refs": source_refs,
            "sink_refs": sink_refs,
            "object_count": len(objects),
            "geometry_summary": geometry_summary,
            "current_model_ref": current_model_ref,
            "estimated_current_a": None,
            "current_basis": current_basis,
            "thermal_model_ref": None,
            "association_basis": association_basis(objects),
            "confidence": min([float(obj.get("confidence", 0.0)) for obj in objects] or [0.0]),
            "unresolved_flags": sorted(set(branch_flags)),
        }
        branches.append(branch)
        net_branch_index[net_name].append(branch_id)

    for net_name in sorted(topo["power_rails"]):
        if not net_branch_index.get(net_name):
            unresolved.append(unresolved_item(
                f"unres_{safe_slug(net_name)}_no_branch",
                "no_branch",
                net_name=net_name,
                notes="Power rail has no branch candidates from associated copper objects.",
            ))

    unresolved_by_id = {item["id"]: item for item in unresolved}
    return branches, dict(sorted(net_branch_index.items())), list(unresolved_by_id.values())


def summarize(topology: dict[str, Any], copper_association: dict[str, Any], branches: list[dict[str, Any]], unresolved: list[dict[str, Any]], warnings: list[str], errors: list[str]) -> dict[str, int]:
    copper_objects = copper_association.get("copper_objects") if isinstance(copper_association.get("copper_objects"), list) else []
    associated = [
        obj for obj in copper_objects
        if isinstance(obj, dict) and obj.get("association_basis") != "unknown" and obj.get("net_name")
    ]

    def count_net_type(types: set[str]) -> int:
        return sum(1 for branch in branches if branch.get("topology_net_type") in types)

    def count_branch_type(branch_type: str) -> int:
        return sum(1 for branch in branches if branch.get("branch_type") == branch_type)

    return {
        "topology_net_count": len(topology.get("nets", [])) if isinstance(topology.get("nets"), list) else 0,
        "copper_object_count": len(copper_objects),
        "associated_copper_object_count": len(associated),
        "branch_count": len(branches),
        "power_branch_count": count_net_type({"power"}),
        "ground_branch_count": count_net_type({"ground", "chassis", "earth"}),
        "signal_branch_count": count_net_type({"signal"}),
        "trace_branch_count": count_branch_type("trace_group"),
        "plane_branch_count": count_branch_type("plane_region"),
        "via_cluster_count": count_branch_type("via_cluster"),
        "unresolved_branch_count": len({item.get("branch_id") for item in unresolved if item.get("branch_id")}),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }


def build_artifact(project: str, topology_path: Path, copper_path: Path, *, strict: bool) -> dict[str, Any]:
    topology = load_json(topology_path)
    copper_association = load_json(copper_path)
    if not isinstance(topology, dict):
        raise ValueError(f"topology JSON must be an object: {topology_path}")
    if not isinstance(copper_association, dict):
        raise ValueError(f"copper association JSON must be an object: {copper_path}")

    warnings: list[str] = []
    errors: list[str] = []
    branches, net_branch_index, unresolved = build_branches(topology, copper_association)
    if unresolved:
        warnings.append(f"{len(unresolved)} unresolved branch topology item(s)")

    if strict:
        no_branch_power = sorted(
            item.get("net_name")
            for item in unresolved
            if item.get("type") == "no_branch" and isinstance(item.get("net_name"), str)
        )
        if no_branch_power:
            errors.append(f"strict mode: power rail(s) without branch candidates: {', '.join(no_branch_power)}")

        power_missing_metadata = sorted({
            item.get("object_id")
            for item in unresolved
            if item.get("type") in {"missing_layer", "missing_geometry"}
            and item.get("object_id")
            and any(branch.get("branch_id") == item.get("branch_id") and branch.get("topology_net_type") == "power" for branch in branches)
        })
        if power_missing_metadata:
            errors.append(f"strict mode: power copper object(s) missing layer/geometry: {', '.join(power_missing_metadata[:20])}")

        unresolved_power_current = sorted(
            branch["branch_id"]
            for branch in branches
            if branch.get("topology_net_type") == "power" and branch.get("current_basis") == "unresolved"
        )
        if unresolved_power_current:
            errors.append(f"strict mode: power branch current unresolved: {', '.join(unresolved_power_current[:20])}")

    summary = summarize(topology, copper_association, branches, unresolved, warnings, errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "topology": str(topology_path),
            "copper_association": str(copper_path),
        },
        "summary": summary,
        "branches": branches,
        "net_branch_index": net_branch_index,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "branch_topology_pass": not errors,
        "human_review_needed": bool(unresolved or warnings or errors),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build conservative branch topology candidates.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--copper-association", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    topology_path = Path(args.topology or default_path("exports/{project}-topology-map.json", project))
    copper_path = Path(args.copper_association or default_path("exports/{project}-copper-net-association.json", project))
    out_path = Path(args.out or default_path("exports/{project}-branch-topology.json", project))

    try:
        if not topology_path.exists():
            raise FileNotFoundError(f"missing topology JSON: {topology_path}")
        if not copper_path.exists():
            raise FileNotFoundError(f"missing copper association JSON: {copper_path}")
        artifact = build_artifact(project, topology_path, copper_path, strict=args.strict)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "branch topology: "
        f"branches={summary['branch_count']} "
        f"power={summary['power_branch_count']} "
        f"unresolved={len(artifact['unresolved'])} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["branch_topology_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
