#!/usr/bin/env python3
"""Associate board copper objects with topology nets.

PR 8 scope only: consume converter board/stackup JSON and a topology map, then
produce a deterministic net-level copper association artifact. This script does
not calculate current density, ampacity, thermal rise, or branch paths.
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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    alias_keys = {key_name(alias) for alias in aliases}
    for key, value in row.items():
        if key_name(key) in alias_keys and value not in (None, ""):
            return value
    return None


def stable_id(prefix: str, index: int) -> str:
    return f"{prefix}_{index:06d}"


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def normalize_net(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_pin(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_copper_layer(layer: dict[str, Any]) -> bool:
    material = str(layer.get("material") or "").upper()
    function = str(layer.get("function") or "").upper()
    layer_type = str(layer.get("type") or "").upper()
    combined = {material, function, layer_type}
    if combined.intersection(NON_COPPER_LAYER_TOKENS):
        return False
    return material == "COPPER" or function in {"CONDUCTOR", "PLANE"} or layer_type in {"CONDUCTOR", "PLANE"}


def normalize_layer_records(stackup: dict[str, Any]) -> list[dict[str, Any]]:
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


def topology_index(topology: dict[str, Any]) -> dict[str, Any]:
    nets = {
        row.get("net_name"): row.get("net_type")
        for row in topology.get("nets", [])
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }
    pins_by_ref = {}
    pins_by_tuple = {}
    for pin in topology.get("pins", []):
        if not isinstance(pin, dict):
            continue
        pin_ref = pin.get("pin_ref")
        refdes = pin.get("refdes")
        pin_num = normalize_pin(pin.get("pin"))
        net_name = normalize_net(pin.get("net_name"))
        if isinstance(pin_ref, str) and net_name:
            pins_by_ref[pin_ref] = net_name
        if isinstance(refdes, str) and pin_num and net_name:
            pins_by_tuple[(refdes, pin_num)] = net_name
    power_rails = {
        rail.get("net_name")
        for rail in topology.get("power_rails", [])
        if isinstance(rail, dict) and isinstance(rail.get("net_name"), str)
    }
    return {
        "nets": nets,
        "net_names": set(nets),
        "pins_by_ref": pins_by_ref,
        "pins_by_tuple": pins_by_tuple,
        "power_rails": power_rails,
        "ground_nets": {name for name, net_type in nets.items() if net_type in {"ground", "chassis", "earth"}},
    }


def explicit_net(row: dict[str, Any]) -> str | None:
    return normalize_net(first_value(row, ("net", "net_name", "netName", "name")))


def row_layer(row: dict[str, Any]) -> str | None:
    value = first_value(row, ("layer", "layer_name", "layerRef"))
    return str(value).strip() if value not in (None, "") else None


def row_refdes_pin(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    refdes = first_value(row, ("refdes", "reference", "designator", "component_ref", "componentRef"))
    pin = first_value(row, ("pin", "pin_number", "pinNumber", "pad", "pad_number", "padNumber"))
    pin_ref = first_value(row, ("pin_ref", "pinRef"))
    return (
        str(refdes).strip() if refdes not in (None, "") else None,
        normalize_pin(pin),
        str(pin_ref).strip() if pin_ref not in (None, "") else None,
    )


def geometry_for(row: dict[str, Any], object_type: str, units: str | None) -> dict[str, Any]:
    shape = "unknown"
    if object_type == "trace":
        shape = "line"
    elif object_type == "via":
        shape = "circle"
    elif object_type in {"polygon", "plane", "region"}:
        shape = "polygon"
    elif object_type == "pad":
        shape = str(row.get("resolved_shape") or row.get("shape") or "unknown")

    width = row.get("line_width")
    if width is None:
        width = row.get("resolved_width", row.get("width", row.get("diameter", row.get("resolved_diameter"))))

    return {
        "available": any(key in row for key in ("points", "bbox", "x", "y", "line_width", "length", "resolved_shape", "diameter", "resolved_diameter")),
        "units": row.get("line_width_units") or row.get("length_units") or row.get("resolved_units") or row.get("diameter_units") or units,
        "shape": shape,
        "bbox": row.get("bbox"),
        "length": row.get("length"),
        "width": width,
        "area": row.get("area"),
    }


def board_net_names(board: dict[str, Any], copper_objects: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for key, name_key in (("nets", "name"), ("physical_nets", "name")):
        rows = board.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    name = normalize_net(row.get(name_key))
                    if name:
                        names.add(name)
    routing = as_dict(board.get("routing_topology_summary"))
    rows = routing.get("nets")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                name = normalize_net(row.get("net"))
                if name:
                    names.add(name)
    for obj in copper_objects:
        name = normalize_net(obj.get("net_name"))
        if name:
            names.add(name)
    return names


def plane_candidate_nets(board: dict[str, Any]) -> set[str]:
    routing = as_dict(board.get("routing_topology_summary"))
    rows = routing.get("nets")
    if not isinstance(rows, list):
        return set()
    return {
        row.get("net")
        for row in rows
        if isinstance(row, dict) and row.get("is_plane_candidate") is True and isinstance(row.get("net"), str)
    }


def collect_rows(board: dict[str, Any], primary_path: tuple[str, str], fallback_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    first = as_dict(board.get(primary_path[0])).get(primary_path[1])
    if isinstance(first, list) and first:
        return [row for row in first if isinstance(row, dict)]
    for key in fallback_keys:
        rows = board.get(key)
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]
        nested = as_dict(board.get("routing_geometry")).get(key)
        if isinstance(nested, list) and nested:
            return [row for row in nested if isinstance(row, dict)]
    return []


def associate_net(row: dict[str, Any], topo: dict[str, Any]) -> tuple[str | None, str, float, list[str]]:
    net_name = explicit_net(row)
    if net_name and net_name in topo["net_names"]:
        return net_name, "explicit_net", 1.0, []
    if net_name:
        return net_name, "explicit_net", 0.4, ["net_not_in_topology"]

    refdes, pin, pin_ref = row_refdes_pin(row)
    if pin_ref and pin_ref in topo["pins_by_ref"]:
        return topo["pins_by_ref"][pin_ref], "pin_net_from_topology", 0.9, []
    if refdes and pin and (refdes, pin) in topo["pins_by_tuple"]:
        return topo["pins_by_tuple"][(refdes, pin)], "component_pin", 0.85, []
    return None, "unknown", 0.0, ["net_unresolved"]


def normalize_copper_object(
    row: dict[str, Any],
    *,
    object_type: str,
    index: int,
    units: str | None,
    topo: dict[str, Any],
) -> dict[str, Any]:
    object_id = row.get("id") if isinstance(row.get("id"), str) else stable_id(object_type, index)
    net_name, basis, confidence, flags = associate_net(row, topo)
    refdes, pin, pin_ref = row_refdes_pin(row)
    if pin_ref is None and refdes and pin:
        pin_ref = f"{refdes}.{pin}"
    return {
        "object_id": object_id,
        "object_type": object_type,
        "net_name": net_name,
        "layer": row_layer(row),
        "refdes": refdes,
        "pin": pin,
        "pin_ref": pin_ref,
        "geometry": geometry_for(row, object_type, units),
        "association_basis": basis,
        "confidence": confidence,
        "unresolved_flags": flags,
    }


def extract_copper_objects(board: dict[str, Any], topo: dict[str, Any], copper_layer_names: set[str]) -> list[dict[str, Any]]:
    units = board.get("units") or as_dict(board.get("routing_geometry")).get("units")
    objects: list[dict[str, Any]] = []
    plane_nets = plane_candidate_nets(board)

    specs = [
        ("trace", ("routing_geometry", "copper_routes"), ("traces", "tracks", "segments", "routes")),
        ("polygon", ("routing_geometry", "copper_polygons"), ("copper_shapes", "polygons", "regions", "planes")),
        ("pad", ("routing_geometry", "copper_pads"), ("pads", "pins", "lands")),
        ("via", ("", ""), ("via_holes", "vias")),
    ]
    counters: Counter[str] = Counter()
    seen_ids: set[tuple[str, str]] = set()
    for base_type, primary, fallbacks in specs:
        rows = collect_rows(board, primary, fallbacks)
        for row in rows:
            if row.get("feature_domain") not in (None, "copper"):
                continue
            layer = row_layer(row)
            if layer and copper_layer_names and base_type != "via" and layer not in copper_layer_names:
                continue
            object_type = base_type
            if base_type == "polygon":
                net = explicit_net(row)
                if row.get("object_type") == "plane" or row.get("type") == "plane" or net in plane_nets or layer in copper_layer_names and str(layer).upper().startswith("LAYER"):
                    object_type = "plane" if net in plane_nets else "polygon"
            counters[object_type] += 1
            obj = normalize_copper_object(row, object_type=object_type, index=counters[object_type], units=units, topo=topo)
            key = (object_type, obj["object_id"])
            if key in seen_ids:
                obj["object_id"] = stable_id(object_type, counters[object_type])
                key = (object_type, obj["object_id"])
            seen_ids.add(key)
            objects.append(obj)
    return objects


def build_net_associations(topology: dict[str, Any], copper_objects: list[dict[str, Any]], board_nets: set[str]) -> list[dict[str, Any]]:
    objects_by_net: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obj in copper_objects:
        if obj.get("net_name"):
            objects_by_net[obj["net_name"]].append(obj)

    associations: list[dict[str, Any]] = []
    for net in topology.get("nets", []):
        if not isinstance(net, dict) or not isinstance(net.get("net_name"), str):
            continue
        net_name = net["net_name"]
        objs = objects_by_net.get(net_name, [])
        object_refs = [obj["object_id"] for obj in objs]
        pin_refs = sorted({obj["pin_ref"] for obj in objs if obj.get("pin_ref")})
        layers = sorted({obj["layer"] for obj in objs if obj.get("layer")})
        object_types = {obj.get("object_type") for obj in objs}
        flags = []
        if not objs:
            flags.append("no_copper_objects")
        associations.append({
            "net_name": net_name,
            "topology_net_type": net.get("net_type"),
            "board_net_present": net_name in board_nets,
            "copper_object_refs": object_refs,
            "pin_refs": pin_refs,
            "layers": layers,
            "object_count": len(objs),
            "has_plane_like_geometry": bool(object_types.intersection({"plane", "polygon", "region"})),
            "has_trace_like_geometry": "trace" in object_types,
            "has_vias": "via" in object_types,
            "unresolved_flags": flags,
        })
    return associations


def summarize(
    topo: dict[str, Any],
    board_nets: set[str],
    net_associations: list[dict[str, Any]],
    copper_objects: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    warnings: list[str],
    errors: list[str],
) -> dict[str, int]:
    topology_nets = set(topo["net_names"])
    matched_nets = {row["net_name"] for row in net_associations if row["board_net_present"] or row["object_count"] > 0}
    associated = [obj for obj in copper_objects if obj.get("net_name") in topology_nets and obj.get("association_basis") != "unknown"]
    by_type = dict(topo["nets"])

    def count_net_type(net_type_set: set[str]) -> int:
        return sum(1 for obj in associated if by_type.get(obj.get("net_name")) in net_type_set)

    return {
        "topology_net_count": len(topology_nets),
        "board_net_count": len(board_nets),
        "matched_net_count": len(matched_nets),
        "unmatched_topology_net_count": len(topology_nets - matched_nets),
        "unmatched_board_net_count": len(board_nets - topology_nets),
        "copper_object_count": len(copper_objects),
        "associated_copper_object_count": len(associated),
        "unassociated_copper_object_count": len(copper_objects) - len(associated),
        "layer_count": len(layers),
        "copper_layer_count": sum(1 for layer in layers if layer["is_copper"]),
        "power_net_copper_object_count": count_net_type({"power"}),
        "ground_net_copper_object_count": count_net_type({"ground", "chassis", "earth"}),
        "signal_net_copper_object_count": count_net_type({"signal"}),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }


def build_artifact(project: str, board_path: Path, stackup_path: Path, topology_path: Path, *, strict: bool) -> dict[str, Any]:
    board = load_json(board_path)
    stackup = load_json(stackup_path)
    topology = load_json(topology_path)
    if not isinstance(board, dict):
        raise ValueError(f"board JSON must be an object: {board_path}")
    if not isinstance(stackup, dict):
        raise ValueError(f"stackup JSON must be an object: {stackup_path}")
    if not isinstance(topology, dict):
        raise ValueError(f"topology JSON must be an object: {topology_path}")

    warnings: list[str] = []
    errors: list[str] = []
    topo = topology_index(topology)
    layers = normalize_layer_records(stackup)
    copper_layer_names = {layer["layer_name"] for layer in layers if layer["is_copper"]}
    if not layers:
        warnings.append("no stackup layers extracted")
    if not copper_layer_names:
        warnings.append("no copper layers detected from stackup")

    copper_objects = extract_copper_objects(board, topo, copper_layer_names)
    board_nets = board_net_names(board, copper_objects)
    net_associations = build_net_associations(topology, copper_objects, board_nets)
    topology_net_names = topo["net_names"]
    unmatched_topology_nets = sorted(
        row["net_name"] for row in net_associations if row["object_count"] == 0 and not row["board_net_present"]
    )
    unmatched_board_nets = sorted(board_nets - topology_net_names)
    unassociated_copper_objects = [
        obj["object_id"]
        for obj in copper_objects
        if obj.get("net_name") not in topology_net_names or obj.get("association_basis") == "unknown"
    ]

    if unmatched_topology_nets:
        warnings.append(f"{len(unmatched_topology_nets)} topology net(s) have no board copper association")
    if unmatched_board_nets:
        warnings.append(f"{len(unmatched_board_nets)} board net(s) are not present in topology")
    if unassociated_copper_objects:
        warnings.append(f"{len(unassociated_copper_objects)} copper object(s) could not be associated to topology nets")

    if strict:
        if not copper_objects:
            errors.append("strict mode: no extractable copper objects")
        power_without_copper = [
            row["net_name"]
            for row in net_associations
            if row["topology_net_type"] == "power" and row["object_count"] == 0
        ]
        if power_without_copper:
            errors.append(f"strict mode: power rail(s) without associated copper: {', '.join(power_without_copper)}")
        explicit_unknown = [
            obj["object_id"]
            for obj in copper_objects
            if "net_not_in_topology" in obj.get("unresolved_flags", [])
        ]
        if explicit_unknown:
            errors.append(f"strict mode: explicit-net copper object(s) not found in topology: {', '.join(explicit_unknown[:20])}")

    summary = summarize(topo, board_nets, net_associations, copper_objects, layers, warnings, errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "board": str(board_path),
            "stackup": str(stackup_path),
            "topology": str(topology_path),
        },
        "summary": summary,
        "layers": layers,
        "net_associations": net_associations,
        "copper_objects": copper_objects,
        "unmatched_topology_nets": unmatched_topology_nets,
        "unmatched_board_nets": unmatched_board_nets,
        "unassociated_copper_objects": unassociated_copper_objects,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "association_pass": not errors,
        "human_review_needed": bool(warnings or errors),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Associate board copper objects with topology nets.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--board", default=None)
    parser.add_argument("--stackup", default=None)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    board_path = Path(args.board or default_path("exports/{project}-thomson-export-brd.json", project))
    stackup_path = Path(args.stackup or default_path("exports/{project}-thomson-export-stack.json", project))
    topology_path = Path(args.topology or default_path("exports/{project}-topology-map.json", project))
    out_path = Path(args.out or default_path("exports/{project}-copper-net-association.json", project))

    try:
        for label, path in (("board", board_path), ("stackup", stackup_path), ("topology", topology_path)):
            if not path.exists():
                raise FileNotFoundError(f"missing {label} JSON: {path}")
        artifact = build_artifact(project, board_path, stackup_path, topology_path, strict=args.strict)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "board copper association: "
        f"copper_objects={summary['copper_object_count']} "
        f"associated={summary['associated_copper_object_count']} "
        f"matched_nets={summary['matched_net_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["association_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
