#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "ipc2581-adapter-0.3"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def iter_by_local_name(root: ET.Element, *names: str):
    wanted = {n.lower() for n in names}
    for e in root.iter():
        if local_name(e.tag).lower() in wanted:
            yield e


def find_by_local_name(root: ET.Element, *names: str):
    return next(iter_by_local_name(root, *names), None)


def get_attr_any(elem: ET.Element, *names: str, default: str = "") -> str:
    want = {n.lower().replace("_", "") for n in names}
    for k, v in elem.attrib.items():
        nk = local_name(k).lower().replace("_", "")
        if nk in want:
            return v
    return default


def f_any(elem: ET.Element, *names: str, default: float = 0.0) -> float:
    try:
        return float(get_attr_any(elem, *names, default=str(default)))
    except Exception:
        return default


@dataclass
class ExtractionReport:
    warnings: list[str]
    errors: list[str]
    unsupported_features: list[str]


def parse_ipc2581(path: Path) -> ET.Element:
    tree = ET.parse(path)
    return tree.getroot()


def extract_ipc2581_metadata(root: ET.Element, source_file: str, project: str) -> dict[str, Any]:
    tool = "unknown"
    txt = ET.tostring(root, encoding="unicode", method="xml")[:1500].lower()
    if "altium" in txt:
        tool = "Altium"
    return {
        "project": project,
        "source_format": "ipc2581",
        "source_file": source_file,
        "source_tool": tool,
        "converter": VERSION,
        "conversion_timestamp": now_iso(),
    }


def extract_ipc2581_components(root: ET.Element, source_file: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in iter_by_local_name(root, "Component", "ComponentInstance", "ComponentRef"):
        ref = get_attr_any(e, "refdes", "designator", "name")
        if not ref:
            continue
        out.append({
            "refdes": ref,
            "value": get_attr_any(e, "value", "partvalue", default=None) or None,
            "footprint": get_attr_any(e, "package", "packageref", "footprint", default=None) or None,
            "part_number": get_attr_any(e, "partnumber", "mpn", default=None) or None,
            "source": {
                "source_format": "ipc2581", "source_file": source_file,
                "source_element": local_name(e.tag), "source_attributes": dict(e.attrib),
                "extraction_confidence": "medium",
            },
        })
    return out


def extract_ipc2581_nets(root: ET.Element, source_file: str) -> list[dict[str, Any]]:
    nets = []
    for n in iter_by_local_name(root, "Net", "ElectricalNet", "LogicalNet"):
        name = get_attr_any(n, "name", "net", "netname")
        if not name:
            continue
        nodes = []
        for p in n.iter():
            if p is n:
                continue
            if local_name(p.tag).lower() in {"pin", "pinref", "node", "connection", "connect"}:
                ref = get_attr_any(p, "refdes", "componentref", "component")
                pin = get_attr_any(p, "pin", "pinref", "pad", "name")
                if ref and pin:
                    nodes.append({"refdes": ref, "pin": pin})
        nets.append({"name": name, "nodes": nodes, "node_count": len(nodes), "source": {"source_element": local_name(n.tag), "source_file": source_file}})
    return nets


def extract_ipc2581_layers(root: ET.Element) -> list[dict[str, Any]]:
    layers = []
    seen = set()
    for e in iter_by_local_name(root, "Layer", "StackupLayer", "ConductorLayer", "DielectricLayer"):
        name = get_attr_any(e, "name", "id", "layerref")
        if not name or name in seen:
            continue
        seen.add(name)
        ltype = get_attr_any(e, "type", "layertype", "function", default="unknown")
        layers.append({"name": name, "type": ltype, "thickness_mm": f_any(e, "thickness", default=0.0)})
    return layers


def extract_ipc2581_stackup(root: ET.Element) -> dict[str, Any]:
    return {"layers": extract_ipc2581_layers(root)}


def extract_ipc2581_placements(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for e in iter_by_local_name(root, "Component", "ComponentInstance", "Placement"):
        ref = get_attr_any(e, "refdes", "designator", "name")
        if not ref:
            continue
        out.append({"refdes": ref, "x_mm": f_any(e, "x", "xloc"), "y_mm": f_any(e, "y", "yloc"), "rotation": f_any(e, "rotation", "angle")})
    return out


def extract_ipc2581_vias(root: ET.Element) -> list[dict[str, Any]]:
    return [{"x_mm": f_any(v, "x"), "y_mm": f_any(v, "y"), "drill_mm": f_any(v, "drill", "hole"), "net": get_attr_any(v, "net", "netname", default=None) or None} for v in iter_by_local_name(root, "Via", "BlindVia", "BuriedVia")]


def extract_ipc2581_tracks_or_segments(root: ET.Element) -> list[dict[str, Any]]:
    out = []
    for t in iter_by_local_name(root, "Segment", "Trace", "Line"):
        x1, y1, x2, y2 = f_any(t, "x1", "startx"), f_any(t, "y1", "starty"), f_any(t, "x2", "endx"), f_any(t, "y2", "endy")
        out.append({"x1_mm": x1, "y1_mm": y1, "x2_mm": x2, "y2_mm": y2, "length_mm": math.hypot(x2-x1, y2-y1), "net": get_attr_any(t, "net", "netname", default=None) or None})
    return out


def build_board_export(metadata, components, nets, layers, placements, vias, segments):
    return {"metadata": metadata, "components": components, "nets": nets, "layers": layers, "placements": placements, "vias": vias, "segments": segments}


def build_stack_export(metadata, stackup):
    return {"metadata": metadata, "stackup": stackup, "layers": stackup.get("layers", [])}


def _json_safe(o: Any) -> bool:
    if isinstance(o, dict):
        return all(_json_safe(k) and _json_safe(v) for k, v in o.items())
    if isinstance(o, list):
        return all(_json_safe(x) for x in o)
    if isinstance(o, float):
        return math.isfinite(o)
    return True


def validate_board_export(board: dict[str, Any]) -> list[str]:
    w = []
    if not board.get("components"):
        w.append("board has zero components")
    if not board.get("nets"):
        w.append("board has zero nets")
    if not board.get("layers"):
        w.append("board has zero layers")
    known = {c.get("refdes") for c in board.get("components", [])}
    for p in board.get("placements", []):
        if p.get("refdes") not in known:
            w.append(f"placement refdes not in components: {p.get('refdes')}")
    if not _json_safe(board):
        w.append("board contains non-JSON-safe values (NaN/Inf)")
    return w


def validate_stack_export(stack: dict[str, Any]) -> list[str]:
    w = []
    if not stack.get("layers"):
        w.append("stack has zero layers")
    return w


def write_outputs(project: str, output: Path, board: dict[str, Any], stack: dict[str, Any], report: dict[str, Any], pretty: bool):
    output.mkdir(parents=True, exist_ok=True)
    ind = 2 if pretty else None
    files = {
        "board": output / f"{project}-thomson-export-brd.json",
        "stack": output / f"{project}-thomson-export-stack.json",
        "report_json": output / f"{project}-conversion-report.json",
        "report_md": output / f"{project}-conversion-report.md",
    }
    files["board"].write_text(json.dumps(board, indent=ind), encoding="utf-8")
    files["stack"].write_text(json.dumps(stack, indent=ind), encoding="utf-8")
    files["report_json"].write_text(json.dumps(report, indent=ind), encoding="utf-8")
    files["report_md"].write_text("\n".join(["# IPC-2581 Conversion Report", f"- project: {project}", f"- warnings: {len(report['warnings'])}"]), encoding="utf-8")
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ipc2581")
    ap.add_argument("--project", required=False)
    ap.add_argument("--output", default="exports")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--warnings-as-errors", action="store_true")
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    src = Path(args.ipc2581)
    if not src.exists():
        print("ERROR: IPC-2581 file missing", file=sys.stderr); return 2
    if src.stat().st_size == 0:
        print("ERROR: IPC-2581 file is empty", file=sys.stderr); return 2
    try:
        root = parse_ipc2581(src)
    except ET.ParseError as e:
        print(f"ERROR: failed to parse XML: {e}", file=sys.stderr); return 2
    if args.inspect:
        tags = sorted({local_name(e.tag) for e in root.iter()})
        print("Discovered tags:", ", ".join(tags[:100]))
    project = args.project or src.stem
    metadata = extract_ipc2581_metadata(root, str(src), project)
    components = extract_ipc2581_components(root, str(src))
    nets = extract_ipc2581_nets(root, str(src))
    layers = extract_ipc2581_layers(root)
    stackup = extract_ipc2581_stackup(root)
    placements = extract_ipc2581_placements(root)
    vias = extract_ipc2581_vias(root)
    segments = extract_ipc2581_tracks_or_segments(root)
    board = build_board_export(metadata, components, nets, layers, placements, vias, segments)
    stack = build_stack_export(metadata, stackup)
    warnings = validate_board_export(board) + validate_stack_export(stack)
    report = {"metadata": metadata, "inputs": {"ipc2581": str(src)}, "counts": {"board_components": len(components), "board_nets": len(nets), "layers": len(layers), "placements": len(placements), "tracks_segments": len(segments), "vias": len(vias), "drills": len([v for v in vias if v.get('drill_mm')])}, "warnings": warnings, "errors": [], "unsupported_features": ["schematic-derived intent from IPC-2581 not available"], "validation": {"best_effort_thomsonlint_contract": True}}
    if not args.dry_run and not args.report_only:
        write_outputs(project, Path(args.output), board, stack, report, args.pretty)
    elif not args.dry_run and args.report_only:
        write_outputs(project, Path(args.output), {}, {}, report, args.pretty)
    if warnings:
        for w in warnings: print(f"WARNING: {w}", file=sys.stderr)
    if args.warnings_as_errors and warnings:
        return 1
    if args.strict and any(x in warnings for x in ["board has zero components", "board has zero nets", "board has zero layers"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
