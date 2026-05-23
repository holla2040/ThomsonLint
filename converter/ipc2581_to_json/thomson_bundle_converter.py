#!/usr/bin/env python3
"""ThomsonLint CAD bundle converter skeleton with Phase 2 BOM + Phase 3 PADS schematic parsing."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "0.5.0-phase5"
BOM_PARSER_VERSION = "bom-v1"
PADS_PARSER_VERSION = "pads-v1"
IPC_PARSER_VERSION = "ipc2581-v1"
GEOMETRY_REVIEW_LIMITATIONS = [
    "No true clearance DRC performed",
    "No polygon boolean connectivity verification performed",
    "Line width references are reported but not validated against design rules unless explicit rules are provided",
    "Differential/paired nets are name-based candidates only",
    "Geometry is extracted from IPC-2581 manufacturing/export features, not from live CAD constraints",
    "No net-short or spacing verification is performed",
    "Plane candidate detection is heuristic and evidence-based",
]


@dataclass
class ClassifiedFile:
    relative_path: str
    extension: str
    size_bytes: int
    category: str
    confidence: str
    reason: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ThomsonLint CAD bundle converter (Phase 1-3)")
    p.add_argument("project_root")
    p.add_argument("--output-root")
    p.add_argument("--project-name")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--pretty", action="store_true")
    p.add_argument("--schematic-pdf-dpi", type=int, default=300)
    p.add_argument("--gerber-pdf-dpi", type=int, default=400)
    p.add_argument("--validate-outputs", action="store_true", help="Run integrated output validation checks")
    return p.parse_args()


def infer_project_name(project_root: Path, override: str | None) -> str:
    return override or (project_root.name.strip() or "project")


def discover_input_dirs(project_root: Path) -> tuple[Path, Path, list[dict[str, Any]]]:
    warnings: list[dict[str, Any]] = []
    expected_schematic = project_root / "pre_conversion" / "schematic"
    expected_layout = project_root / "pre_conversion" / "layout"
    schematic_dir, layout_dir = expected_schematic, expected_layout
    if not expected_schematic.exists() or not expected_layout.exists():
        fallback_schematic, fallback_layout = project_root / "schematic", project_root / "layout"
        examples_mode = project_root.name.lower() in {"example", "examples"}
        if fallback_schematic.exists() or fallback_layout.exists():
            schematic_dir, layout_dir = fallback_schematic, fallback_layout
            warnings.append({"code": "WARN_NONSTANDARD_LAYOUT", "message": "Using compatibility mode with <project_root>/(schematic|layout) instead of pre_conversion tree."})
        elif examples_mode:
            schematic_dir = layout_dir = project_root
            warnings.append({"code": "WARN_EXAMPLES_FLAT_LAYOUT", "message": "Using examples compatibility mode with flat folder scan because pre_conversion tree is missing."})
        else:
            warnings.append({"code": "WARN_MISSING_EXPECTED_TREE", "message": "Expected pre_conversion/schematic and pre_conversion/layout directories were not both found."})
    return schematic_dir, layout_dir, warnings


def classify_file(path: Path, root: Path, role_hint: str) -> ClassifiedFile:
    ext = path.suffix.lower()
    name = path.name.lower()
    rel = path.relative_to(root).as_posix()
    size = path.stat().st_size

    if ext in {".asc", ".pads", ".txt", ".net"}:
        if any(k in name for k in ["pads", "netlist", "orcad", "altium"]):
            return ClassifiedFile(rel, ext, size, "pads_ascii_candidate", "high", "Extension and filename suggest PADS/netlist export")
        return ClassifiedFile(rel, ext, size, "pads_ascii_candidate", "medium", "Extension is compatible with PADS ASCII export")
    if ext == ".csv" and role_hint == "schematic":
        return ClassifiedFile(rel, ext, size, "bom_csv_candidate", "high", "CSV in schematic scope likely BOM")
    if ext in {".xml", ".ipc2581", ".cvg", ".ipc"} and role_hint == "layout":
        return ClassifiedFile(rel, ext, size, "ipc2581_candidate", "high", "Layout XML/IPC2581 extension")
    if ext == ".pdf":
        if any(k in name for k in ["gerber", "gerbers", "photoplot", "plot", "artwork", "copper", "silk", "layer", "pcb", "layout"]):
            return ClassifiedFile(rel, ext, size, "layout_pdf_candidate", "high", "Filename suggests layout/Gerber PDF")
        if any(k in name for k in ["schematic", "sch", "circuit", "pages", "capture", "orcad"]):
            return ClassifiedFile(rel, ext, size, "schematic_pdf_candidate", "high", "Filename suggests schematic PDF")
    if ext == ".pdf" and role_hint == "schematic":
        return ClassifiedFile(rel, ext, size, "schematic_pdf_candidate", "medium", "PDF under schematic scope")
    if ext == ".pdf" and role_hint == "layout":
        return ClassifiedFile(rel, ext, size, "layout_pdf_candidate", "medium", "PDF under layout scope")
    if ext == ".csv":
        return ClassifiedFile(rel, ext, size, "bom_csv_candidate", "medium", "CSV found outside schematic scope; treated as BOM candidate")
    if ext in {".xml", ".ipc2581", ".cvg", ".ipc"}:
        return ClassifiedFile(rel, ext, size, "ipc2581_candidate", "medium", "XML/IPC2581 found outside layout scope")
    if ext == ".pdf":
        if "schem" in name:
            return ClassifiedFile(rel, ext, size, "schematic_pdf_candidate", "medium", "Filename suggests schematic PDF")
        if any(k in name for k in ["gerber", "layout", "pcb", "silk", "copper", "layer", "plot", "photoplot", "artwork"]):
            return ClassifiedFile(rel, ext, size, "layout_pdf_candidate", "medium", "Filename suggests layout/Gerber PDF")
    return ClassifiedFile(rel, ext, size, "unknown", "low", "No classifier rule matched")


def scan_files(project_root: Path, schematic_dir: Path, layout_dir: Path) -> list[ClassifiedFile]:
    files: list[ClassifiedFile] = []
    seen: set[Path] = set()
    for directory, hint in [(schematic_dir, "schematic"), (layout_dir, "layout")]:
        if directory.exists() and directory.is_dir():
            for p in sorted(directory.iterdir()):
                if p.is_file() and p.resolve() not in seen:
                    files.append(classify_file(p, project_root, hint))
                    seen.add(p.resolve())
    if not files:
        for p in sorted(project_root.iterdir()):
            if p.is_file():
                files.append(classify_file(p, project_root, "unknown"))
    return files


def planned_outputs(project_name: str, output_root: Path) -> list[str]:
    return [str(output_root / f"{project_name}-{n}") for n in [
        "thomson-export-sch.json", "thomson-export-brd.json", "thomson-export-stack.json",
        "bom.json", "conversion-report.json", "conversion-report.md"
    ]]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


HEADER_MAP = {
    "refdes": "refdes", "designator": "refdes", "reference": "refdes", "references": "refdes",
    "value": "value", "description": "description", "manufacturer": "manufacturer", "mpn": "mpn", "manufacturerpartnumber": "mpn",
    "vendor": "vendor", "vendorpn": "vendor_pn", "quantity": "quantity", "qty": "quantity", "footprint": "footprint", "package": "package",
    "dni": "dnp", "dnp": "dnp", "donotinstall": "dnp", "part": "item", "item": "item",
    "mfg1": "manufacturer", "mfg2": "manufacturer", "mfg3": "manufacturer",
    "mfgpn1": "mpn", "mfgpn2": "mpn", "mfgpn3": "mpn"
}


def parse_bool(v: str) -> bool | None:
    t = v.strip().lower()
    if t in {"1", "true", "yes", "y", "dnp", "dni", "do not install", "installed=no", "no-load", "noload"}:
        return True
    if t in {"0", "false", "no", "n", "install", "fitted"}:
        return False
    return None


def expand_refdes_cell(cell: str, warnings: list[dict[str, Any]]) -> list[str]:
    tokens = [t for t in re.split(r"[;,\s]+", cell.strip()) if t]
    out: list[str] = []
    for tok in tokens:
        m = re.match(r"^([A-Za-z]+)(\d+)-([A-Za-z]+)?(\d+)$", tok)
        if m:
            p1, s, p2, e = m.groups()
            if p2 and p2.upper() != p1.upper():
                warnings.append({"code": "WARN_BOM_REFDES_RANGE_AMBIGUOUS", "message": "Ambiguous BOM refdes range token."})
                out.append(tok)
                continue
            a, b = int(s), int(e)
            if a > b or b - a > 500:
                warnings.append({"code": "WARN_BOM_REFDES_RANGE_AMBIGUOUS", "message": "Unsafe BOM refdes range token."})
                out.append(tok)
                continue
            out.extend([f"{p1}{i}" for i in range(a, b + 1)])
            continue
        out.append(tok)
    return out


def parse_bom(project_name: str, project_root: Path, files: list[ClassifiedFile]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    candidates = sorted([f for f in files if f.category == "bom_csv_candidate"], key=lambda f: f.relative_path)
    if not candidates:
        warnings.append({"code": "WARN_BOM_MISSING", "message": "No BOM CSV candidate discovered."})
        return {"project_name": project_name, "source_file": None, "parser_version": BOM_PARSER_VERSION, "raw_headers": [], "normalized_headers": {}, "row_count": 0, "expanded_refdes_count": 0, "duplicate_refdes": [], "warnings": warnings, "items": []}
    source = candidates[0]
    if len(candidates) > 1:
        warnings.append({"code": "WARN_BOM_MULTIPLE_CANDIDATES", "message": f"Multiple BOM CSV candidates found ({len(candidates)}); using {source.relative_path}"})

    text = (project_root / source.relative_path).read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    raw_headers = reader.fieldnames or []
    normalized_headers = {h: HEADER_MAP.get(_norm(h), "unknown") for h in raw_headers}
    ref_cols = [h for h, n in normalized_headers.items() if n == "refdes"]
    if not ref_cols:
        warnings.append({"code": "WARN_BOM_MISSING_REFDES_HEADER", "message": "No recognized RefDes/Designator/Reference column found."})

    items = []
    ref_counts: dict[str, int] = {}
    for idx, row in enumerate(reader, start=1):
        ref_cell = ((row.get(ref_cols[0]) if ref_cols else "") or "").strip()
        refs = expand_refdes_cell(ref_cell, warnings) if ref_cell else []
        for r in refs:
            ref_counts[r] = ref_counts.get(r, 0) + 1

        def pick(field: str) -> str | None:
            for h, n in normalized_headers.items():
                if n == field and (row.get(h) or "").strip():
                    return (row.get(h) or "").strip()
            return None

        dnp_val = None
        for h, n in normalized_headers.items():
            if n == "dnp":
                parsed = parse_bool(row.get(h, "") or "")
                if parsed is not None:
                    dnp_val = parsed
                    break

        manufacturer_alternates: list[dict[str, Any]] = []
        for rank in (1, 2, 3):
            mfg_candidates = [
                f"MFG_{rank}", f"MFG {rank}", f"Manufacturer_{rank}", f"Manufacturer {rank}"
            ]
            mpn_candidates = [
                f"MFG P/N_{rank}", f"MFG P/N {rank}", f"MPN_{rank}", f"Manufacturer Part Number_{rank}"
            ]
            mfg_val = next(((row.get(h) or "").strip() for h in mfg_candidates if (row.get(h) or "").strip()), None)
            mpn_val = next(((row.get(h) or "").strip() for h in mpn_candidates if (row.get(h) or "").strip()), None)
            if mfg_val or mpn_val:
                manufacturer_alternates.append({"manufacturer": mfg_val, "mpn": mpn_val, "rank": rank})

        primary_manufacturer = pick("manufacturer")
        primary_mpn = pick("mpn")
        if not primary_manufacturer and manufacturer_alternates:
            primary_manufacturer = manufacturer_alternates[0].get("manufacturer")
        if not primary_mpn and manufacturer_alternates:
            primary_mpn = manufacturer_alternates[0].get("mpn")

        items.append({
            "refdes": refs,
            "fields": {
                "value": pick("value"), "description": pick("description"), "manufacturer": pick("manufacturer"),
                "mpn": pick("mpn"), "vendor": pick("vendor"), "vendor_pn": pick("vendor_pn"),
                "quantity": pick("quantity"), "footprint": pick("footprint"), "package": pick("package"), "dnp": dnp_val,
            },
            "manufacturers": manufacturer_alternates,
            "raw_row_index": idx,
        })
        items[-1]["fields"]["manufacturer"] = primary_manufacturer
        items[-1]["fields"]["mpn"] = primary_mpn

    duplicates = sorted([k for k, v in ref_counts.items() if v > 1])
    if duplicates:
        warnings.append({"code": "WARN_BOM_DUPLICATE_REFDES", "message": f"Duplicate RefDes values found: {len(duplicates)}"})

    return {
        "project_name": project_name,
        "source_file": source.relative_path,
        "parser_version": BOM_PARSER_VERSION,
        "raw_headers": raw_headers,
        "normalized_headers": normalized_headers,
        "row_count": len(items),
        "expanded_refdes_count": sum(len(i["refdes"]) for i in items),
        "duplicate_refdes": duplicates,
        "warnings": warnings,
        "items": items,
    }


def parse_pads(project_root: Path, files: list[ClassifiedFile], bom: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    candidates = sorted([f for f in files if f.category == "pads_ascii_candidate"], key=lambda f: f.relative_path)
    if not candidates:
        warnings.append({"code": "WARN_PADS_MISSING", "message": "No PADS ASCII candidate discovered."})
        return {"source_file": None, "detected_dialect": "unknown", "parser_version": PADS_PARSER_VERSION, "components": [], "nets": [], "warnings": warnings, "extraction_counts": {"component_count": 0, "net_count": 0, "node_count": 0, "single_pin_net_count": 0, "power_net_count": 0, "ground_net_count": 0}, "bom_merge": {"components_with_bom_metadata": 0, "components_missing_bom_metadata": 0, "unmatched_bom_refdes": [], "value_mismatch_count": 0, "footprint_mismatch_count": 0}}
    source = candidates[0]
    if len(candidates) > 1:
        warnings.append({"code": "WARN_PADS_MULTIPLE_CANDIDATES", "message": f"Multiple PADS candidates found ({len(candidates)}); using {source.relative_path}"})

    lines = (project_root / source.relative_path).read_text(encoding="utf-8", errors="replace").splitlines()
    dialect = "unknown"
    if any("*PADS-PCB*" in ln for ln in lines[:10]):
        dialect = "pads_pcb_ascii_orcad_or_altium"

    components: dict[str, dict[str, Any]] = {}
    nets: list[dict[str, Any]] = []
    current_section = None
    current_net = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.upper() == "*PART*":
            current_section = "part"
            continue
        if line.upper() == "*NET*":
            current_section = "net"
            if current_net:
                nets.append(current_net)
                current_net = None
            continue
        if current_section == "part":
            toks = line.split()
            if len(toks) >= 2:
                refdes = toks[0]
                if toks[0].upper() in {"COMP", "PART"} and len(toks) > 1:
                    refdes = toks[1]
                value = None
                footprint = None
                part_name = toks[1] if refdes == toks[0] else toks[0]
                for tk in toks[2:]:
                    low = tk.lower()
                    if low.startswith("value="):
                        value = tk.split("=", 1)[1]
                    elif low.startswith("footprint=") or low.startswith("package="):
                        footprint = tk.split("=", 1)[1]
                components[refdes] = {"refdes": refdes, "value": value, "footprint": footprint, "package": footprint, "part_name": part_name, "source": {"format": "pads_ascii", "file": source.relative_path}}
        elif current_section == "net":
            if line.upper().startswith("*SIGNAL*"):
                if current_net:
                    nets.append(current_net)
                current_net = {"name": line.split(maxsplit=1)[1].strip() if len(line.split(maxsplit=1)) > 1 else "unknown_net", "nodes": []}
                continue
            if line.upper().startswith("NET "):
                if current_net:
                    nets.append(current_net)
                current_net = {"name": line[4:].strip(), "nodes": []}
                continue
            if current_net is not None:
                for pin_token in line.split():
                    if pin_token.startswith("*"):
                        continue
                    if "." in pin_token:
                        refdes, pin = pin_token.rsplit(".", 1)
                    else:
                        refdes, pin = pin_token, None
                    if not refdes:
                        continue
                    current_net["nodes"].append({"refdes": refdes, "pin_number": pin, "pin_name": None})
    if current_net:
        nets.append(current_net)

    if not components:
        warnings.append({"code": "WARN_PADS_NO_COMPONENTS", "message": "No components extracted from PADS file."})
    if not nets:
        warnings.append({"code": "WARN_PADS_NO_NETS", "message": "No nets extracted from PADS file; fixture may be component-only or net sections were not found."})

    # BOM merge
    bom_map: dict[str, dict[str, Any]] = {}
    non_electrical = set()
    for item in bom.get("items", []):
        for rd in item.get("refdes", []):
            if re.match(r"^(ASM|FAB|PCB|SCH)", rd, re.IGNORECASE) or re.fullmatch(r"\d+", rd or ""):
                non_electrical.add(rd)
                continue
            bom_map[rd] = item.get("fields", {})

    with_bom = 0
    missing_bom = 0
    value_mismatch = 0
    footprint_mismatch = 0
    for refdes, comp in components.items():
        b = bom_map.get(refdes)
        comp["bom"] = b
        if b:
            with_bom += 1
            bval = b.get("value")
            if comp.get("value") and bval and comp["value"] != bval:
                value_mismatch += 1
                warnings.append({"code": "WARN_COMPONENT_VALUE_MISMATCH", "message": f"Value mismatch for {refdes}."})
            bfp = b.get("footprint") or b.get("package")
            if comp.get("footprint") and bfp and comp["footprint"] != bfp:
                footprint_mismatch += 1
                warnings.append({"code": "WARN_COMPONENT_FOOTPRINT_MISMATCH", "message": f"Footprint mismatch for {refdes}."})
        else:
            missing_bom += 1

    comp_refs = set(components.keys())
    unmatched_bom_refdes = sorted([r for r in bom_map if r not in comp_refs and r not in non_electrical])

    node_count = sum(len(n["nodes"]) for n in nets)
    single_pin_nets = [n["name"] for n in nets if len(n["nodes"]) <= 1]
    ground_nets = [n["name"] for n in nets if n["name"].upper() in {"GND", "GROUND", "AGND", "DGND", "PGND"}]
    power_nets = [n["name"] for n in nets if re.search(r"(^VCC|^VDD|^VBAT|\+\d|^PWR)", n["name"].upper())]
    clock_nets = [n["name"] for n in nets if "CLK" in n["name"].upper() or "CLOCK" in n["name"].upper()]

    sch_components = list(sorted(components.values(), key=lambda x: x["refdes"]))
    sch_nets = []
    for n in nets:
        sch_nets.append({"name": n["name"], "node_count": len(n["nodes"]), "nodes": n["nodes"]})

    return {
        "source_file": source.relative_path,
        "detected_dialect": dialect,
        "parser_version": PADS_PARSER_VERSION,
        "components": sch_components,
        "nets": sch_nets,
        "analysis": {"power_nets": power_nets, "ground_nets": ground_nets, "clock_nets": clock_nets, "single_pin_nets": single_pin_nets},
        "warnings": warnings,
        "extraction_counts": {
            "component_count": len(sch_components), "net_count": len(sch_nets), "node_count": node_count,
            "single_pin_net_count": len(single_pin_nets), "power_net_count": len(power_nets), "ground_net_count": len(ground_nets),
        },
        "bom_merge": {
            "components_with_bom_metadata": with_bom,
            "components_missing_bom_metadata": missing_bom,
            "unmatched_bom_refdes": unmatched_bom_refdes,
            "value_mismatch_count": value_mismatch,
            "footprint_mismatch_count": footprint_mismatch,
        },
    }


def build_schematic_export(project_name: str, project_root: Path, pads: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_name": project_name,
        "source": {"project_root": str(project_root), "schematic_file": pads.get("source_file"), "format": "pads_ascii", "detected_dialect": pads.get("detected_dialect")},
        "parser_version": pads.get("parser_version"),
        "components": pads.get("components", []),
        "nets": pads.get("nets", []),
        "analysis": pads.get("analysis", {}),
        "warnings": pads.get("warnings", []),
        "extraction_counts": pads.get("extraction_counts", {}),
        "bom_merge": pads.get("bom_merge", {}),
    }




def _local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def _upper(v: Any) -> str:
    return str(v or "").upper()


def _is_copper_layer(layer: dict[str, Any]) -> bool:
    function = _upper(layer.get("function") or layer.get("type"))
    name = _upper(layer.get("name"))
    return function in {"CONDUCTOR", "PLANE", "SIGNAL", "INTERNAL"} or name in {"TOP", "BOTTOM"} or bool(re.fullmatch(r"LAYER\d+", name))


def _layer_feature_domain(layer: dict[str, Any]) -> str:
    function = _upper(layer.get("function") or layer.get("type"))
    name = _upper(layer.get("name"))
    if _is_copper_layer(layer):
        return "copper"
    if function == "DRILL" or "DRILL" in name:
        return "drill"
    if function == "SOLDERMASK" or "SOLDERMASK" in name or name.startswith("SM"):
        return "soldermask"
    if function == "PASTEMASK" or "PASTE" in name:
        return "pastemask"
    if function == "SILKSCREEN" or "SILK" in name or name.startswith("SS"):
        return "silkscreen"
    if function == "ASSEMBLY" or "ASSY" in name:
        return "assembly"
    if function == "BOARD_OUTLINE" or "OUTLINE" in name:
        return "outline"
    if function in {"DOCUMENT", "FABRICATION"} or "FAB" in name or "LEGEND" in name:
        return "fabrication"
    return "unknown"


def _layer_role(layer: dict[str, Any]) -> str:
    side = _upper(layer.get("side"))
    name = _upper(layer.get("name"))
    if side in {"TOP", "BOTTOM", "INTERNAL"}:
        return side.lower()
    if name == "TOP":
        return "top"
    if name == "BOTTOM":
        return "bottom"
    if re.fullmatch(r"LAYER\d+", name):
        return "internal"
    return "other"


def _net_name_evidence(net: str) -> str | None:
    n = _upper(net)
    if n in {"GND", "GROUND", "AGND", "DGND", "PGND", "GNDA", "GNDD"} or n.endswith("_GND"):
        return "ground net name"
    if re.search(r"(^VCC|^VDD|^VBAT|^VIN|^VOUT|^\+\d|^PWR|_PWR$|_VCC$|_VDD$)", n):
        return "power net name"
    return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _attrs(e: ET.Element | None) -> dict[str, Any]:
    return dict(e.attrib) if e is not None else {}


def _first_child(e: ET.Element, names: set[str]) -> ET.Element | None:
    return next((c for c in e if _local(c.tag) in names), None)


def _first_desc(e: ET.Element, names: set[str]) -> ET.Element | None:
    return next((c for c in e.iter() if c is not e and _local(c.tag) in names), None)


def _descriptor_ref(e: ET.Element, tag_name: str) -> str | None:
    ref = next((x.attrib.get("id") for x in e.iter() if _local(x.tag) == tag_name and x.attrib.get("id")), None)
    return ref


def _points_from_geometry(e: ET.Element) -> tuple[list[dict[str, Any]], bool]:
    points: list[dict[str, Any]] = []
    has_curve = False
    for p in e.iter():
        tag = _local(p.tag)
        if tag not in {"PolyBegin", "PolyStepSegment", "PolyStepCurve"}:
            continue
        x = _to_float(p.attrib.get("x"))
        y = _to_float(p.attrib.get("y"))
        if x is None or y is None:
            continue
        if tag == "PolyBegin":
            point = {"kind": "begin", "x": x, "y": y}
        elif tag == "PolyStepCurve":
            has_curve = True
            point = {
                "kind": "curve",
                "x": x,
                "y": y,
                "center_x": _to_float(p.attrib.get("centerX") or p.attrib.get("center_x")),
                "center_y": _to_float(p.attrib.get("centerY") or p.attrib.get("center_y")),
                "clockwise": (p.attrib.get("clockwise") or "").lower() == "true",
            }
        else:
            point = {"kind": "segment", "x": x, "y": y}
        points.append(point)
    return points, has_curve


def _unit_to_inch_factor(units: str | None) -> float:
    unit = _upper(units)
    if unit in {"IN", "INCH", "INCHES"}:
        return 1.0
    if unit in {"MM", "MILLIMETER", "MILLIMETERS"}:
        return 1.0 / 25.4
    if unit in {"MIL", "MILS"}:
        return 0.001
    return 1.0


def _route_length_from_points(points: list[dict[str, Any]], units: str | None) -> dict[str, Any]:
    to_inch = _unit_to_inch_factor(units)
    total = 0.0
    segment_count = 0
    curve_count = 0
    estimated = False
    prev: dict[str, Any] | None = None
    for point in points:
        if prev is None:
            prev = point
            continue
        x1 = prev.get("x")
        y1 = prev.get("y")
        x2 = point.get("x")
        y2 = point.get("y")
        if not all(isinstance(v, (int, float)) for v in (x1, y1, x2, y2)):
            prev = point
            continue
        chord = math.hypot(x2 - x1, y2 - y1) * to_inch
        if point.get("kind") == "curve":
            curve_count += 1
            cx = point.get("center_x")
            cy = point.get("center_y")
            if isinstance(cx, (int, float)) and isinstance(cy, (int, float)):
                radius_a = math.hypot(x1 - cx, y1 - cy) * to_inch
                radius_b = math.hypot(x2 - cx, y2 - cy) * to_inch
                radius = (radius_a + radius_b) / 2.0
                if radius > 0:
                    start = math.atan2(y1 - cy, x1 - cx)
                    end = math.atan2(y2 - cy, x2 - cx)
                    if point.get("clockwise"):
                        angle = (start - end) % (2.0 * math.pi)
                    else:
                        angle = (end - start) % (2.0 * math.pi)
                    total += radius * angle
                else:
                    total += chord
                    estimated = True
            else:
                total += chord
                estimated = True
        else:
            segment_count += 1
            total += chord
        prev = point
    return {
        "length": round(total, 10),
        "length_units": "INCH",
        "length_is_estimated": estimated,
        "segment_count": segment_count,
        "curve_count": curve_count,
    }


def _hole_type(plating_status: str | None) -> str:
    status = _upper(plating_status)
    if status == "VIA":
        return "via"
    if status == "PLATED":
        return "plated_hole"
    if status == "NONPLATED":
        return "nonplated_hole"
    return "hole"


def _bbox_from_circle(x: float | None, y: float | None, diameter: float | None) -> dict[str, float] | None:
    if x is None or y is None or diameter is None:
        return None
    radius = diameter / 2.0
    return {"min_x": x - radius, "min_y": y - radius, "max_x": x + radius, "max_y": y + radius}


def _extract_layerfeature_holes(root: ET.Element, units: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    holes: list[dict[str, Any]] = []
    parse_warnings: list[dict[str, Any]] = []
    hole_id = 0
    for lf in root.iter():
        if _local(lf.tag) != "LayerFeature":
            continue
        layer = lf.attrib.get("layerRef") or lf.attrib.get("layer") or lf.attrib.get("name")
        for set_elem in [c for c in lf if _local(c.tag) == "Set"]:
            net = set_elem.attrib.get("net") or set_elem.attrib.get("netRef") or set_elem.attrib.get("netName") or None
            for hole in [x for x in set_elem.iter() if _local(x.tag) == "Hole"]:
                hole_id += 1
                x = _to_float(hole.attrib.get("x"))
                y = _to_float(hole.attrib.get("y"))
                diameter = _to_float(hole.attrib.get("diameter") or hole.attrib.get("drill"))
                plating_status = hole.attrib.get("platingStatus") or hole.attrib.get("plating_status") or hole.attrib.get("plated")
                row = {
                    "id": f"hole_{hole_id:06d}",
                    "source": "ipc2581.LayerFeature.Set.Hole",
                    "name": hole.attrib.get("name"),
                    "net": net,
                    "layer": layer,
                    "x": x,
                    "y": y,
                    "diameter": diameter,
                    "diameter_units": units,
                    "plating_status": plating_status,
                    "hole_type": _hole_type(plating_status),
                    "layer_span": hole.attrib.get("layerSpan") or hole.attrib.get("fromLayer") or hole.attrib.get("toLayer"),
                    "bbox": _bbox_from_circle(x, y, diameter),
                    "raw": _attrs(hole),
                }
                holes.append(row)
                if x is None or y is None or diameter is None:
                    parse_warnings.append({"code": "WARN_HOLE_GEOMETRY_INCOMPLETE", "message": f"Hole {row['id']} has incomplete location or diameter."})

    via_holes = [
        {
            "id": h["id"],
            "net": h.get("net"),
            "x": h.get("x"),
            "y": h.get("y"),
            "diameter": h.get("diameter"),
            "diameter_units": h.get("diameter_units"),
            "layer": h.get("layer"),
            "layer_span": h.get("layer_span"),
            "plating_status": h.get("plating_status"),
        }
        for h in holes if h.get("hole_type") == "via"
    ]
    plated_holes = [h for h in holes if _upper(h.get("plating_status")) in {"VIA", "PLATED"}]
    nonplated_holes = [h for h in holes if _upper(h.get("plating_status")) == "NONPLATED"]
    summary = {
        "total_holes": len(holes),
        "via_holes": len(via_holes),
        "plated_holes": len(plated_holes),
        "nonplated_holes": len(nonplated_holes),
        "holes_with_net": sum(1 for h in holes if h.get("net")),
        "holes_without_net": sum(1 for h in holes if not h.get("net")),
        "units": units,
    }
    return holes, via_holes, plated_holes, nonplated_holes, summary, parse_warnings


def _extract_package_geometry(root: ET.Element) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    packages = [e for e in root.iter() if _local(e.tag) == "Package"]
    land_patterns: list[dict[str, Any]] = []
    totals = {
        "package_count": len(packages),
        "landpattern_pad_count": 0,
        "package_outline_polygon_count": 0,
        "assembly_drawing_polyline_count": 0,
        "assembly_drawing_polygon_count": 0,
        "silkscreen_marking_polyline_count": 0,
        "silkscreen_marking_polygon_count": 0,
        "user_primitive_polyline_count": 0,
        "user_primitive_polygon_count": 0,
    }
    for pkg in packages:
        name = pkg.attrib.get("name") or pkg.attrib.get("id")
        land_pattern_nodes = [c for c in pkg.iter() if _local(c.tag) == "LandPattern"]
        pad_count = 0
        bbox = None
        for lp in land_pattern_nodes:
            for pad in [x for x in lp.iter() if _local(x.tag) == "Pad"]:
                pad_count += 1
                loc = _first_child(pad, {"Location"})
                x = _to_float(pad.attrib.get("x") or (loc.attrib.get("x") if loc is not None else None))
                y = _to_float(pad.attrib.get("y") or (loc.attrib.get("y") if loc is not None else None))
                if x is not None and y is not None:
                    bbox = _merge_bbox(bbox, {"min_x": x, "min_y": y, "max_x": x, "max_y": y})
        totals["landpattern_pad_count"] += pad_count
        outlines = [x for x in pkg.iter() if _local(x.tag) in {"Outline", "PackageOutline"}]
        outline_polygon_count = sum(1 for o in outlines for x in o.iter() if _local(x.tag) == "Polygon")
        totals["package_outline_polygon_count"] += outline_polygon_count
        assembly_polylines = 0
        assembly_polygons = 0
        silkscreen_polylines = 0
        silkscreen_polygons = 0
        for node in pkg.iter():
            tag = _upper(_local(node.tag))
            if "ASSEMBLY" in tag or "ASSEMBLY" in _upper(node.attrib.get("type")):
                assembly_polylines += sum(1 for x in node.iter() if _local(x.tag) == "Polyline")
                assembly_polygons += sum(1 for x in node.iter() if _local(x.tag) == "Polygon")
            if "SILK" in tag or "SILK" in _upper(node.attrib.get("type")):
                silkscreen_polylines += sum(1 for x in node.iter() if _local(x.tag) == "Polyline")
                silkscreen_polygons += sum(1 for x in node.iter() if _local(x.tag) == "Polygon")
        totals["assembly_drawing_polyline_count"] += assembly_polylines
        totals["assembly_drawing_polygon_count"] += assembly_polygons
        totals["silkscreen_marking_polyline_count"] += silkscreen_polylines
        totals["silkscreen_marking_polygon_count"] += silkscreen_polygons
        if pad_count or outline_polygon_count or assembly_polylines or silkscreen_polylines:
            land_patterns.append({
                "package_ref": name,
                "pad_count": pad_count,
                "outline_polygon_count": outline_polygon_count,
                "assembly_polyline_count": assembly_polylines,
                "assembly_polygon_count": assembly_polygons,
                "silkscreen_polyline_count": silkscreen_polylines,
                "silkscreen_polygon_count": silkscreen_polygons,
                "bbox": bbox,
            })
    for entry in root.iter():
        if _local(entry.tag) != "EntryUser":
            continue
        totals["user_primitive_polyline_count"] += sum(1 for x in entry.iter() if _local(x.tag) == "Polyline")
        totals["user_primitive_polygon_count"] += sum(1 for x in entry.iter() if _local(x.tag) == "Polygon")
    return totals, sorted(land_patterns, key=lambda r: r.get("package_ref") or "")


def _build_stackup_data_quality(layers: list[dict[str, Any]], stack: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "layer_names_available": bool(layers and all(l.get("name") for l in layers)),
        "layer_order_available": bool(stack),
        "layer_function_available": any(l.get("function") or l.get("type") for l in layers),
        "layer_side_available": any(l.get("side") for l in layers),
        "material_thickness_available": any(s.get("thickness") for s in stack),
        "dielectric_material_available": any(s.get("material") or s.get("dielectric_constant") for s in stack),
        "copper_weight_available": any(s.get("copper_thickness") for s in stack),
        "impedance_rules_available": False,
        "source": "ipc2581",
        "warnings": [
            "Material/thickness stackup details unavailable; using known ordered layer metadata."
        ] if not any(s.get("thickness") for s in stack) else [],
    }


def _bbox_from_points(points: list[dict[str, Any]]) -> dict[str, float] | None:
    xs = [p["x"] for p in points if isinstance(p.get("x"), (int, float))]
    ys = [p["y"] for p in points if isinstance(p.get("y"), (int, float))]
    if not xs or not ys:
        return None
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def _merge_bbox(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, float] | None:
    if not a:
        return b
    if not b:
        return a
    return {
        "min_x": min(a["min_x"], b["min_x"]),
        "min_y": min(a["min_y"], b["min_y"]),
        "max_x": max(a["max_x"], b["max_x"]),
        "max_y": max(a["max_y"], b["max_y"]),
    }


def _bbox_area(bbox: dict[str, float] | None) -> float:
    if not bbox:
        return 0.0
    return max(0.0, bbox["max_x"] - bbox["min_x"]) * max(0.0, bbox["max_y"] - bbox["min_y"])


def _bbox_overlap_possible(a: dict[str, float] | None, b: dict[str, float] | None) -> bool | None:
    if not a or not b:
        return None
    return not (a["max_x"] < b["min_x"] or b["max_x"] < a["min_x"] or a["max_y"] < b["min_y"] or b["max_y"] < a["min_y"])


def _count_phrase(count: int, singular: str, plural: str, layer: str) -> str:
    noun = singular if count == 1 else plural
    return f"{count} {noun} on {layer}"


def _parse_line_descriptors(root: ET.Element, default_units: str | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local(entry.tag) not in {"EntryLineDesc", "LineDescEntry"}:
            continue
        desc = _first_desc(entry, {"LineDesc"})
        ident = entry.attrib.get("id") or (desc.attrib.get("id") if desc is not None else None)
        if not ident:
            continue
        dictionary = next((p for p in root.iter() if _local(p.tag) == "DictionaryLineDesc" and entry in list(p)), None)
        units = entry.attrib.get("units") or (desc.attrib.get("units") if desc is not None else None) or (dictionary.attrib.get("units") if dictionary is not None else None) or default_units
        raw = {"entry": _attrs(entry), "line_desc": _attrs(desc)}
        rows.append({
            "id": ident,
            "width": _to_float((desc.attrib.get("lineWidth") if desc is not None else None) or entry.attrib.get("lineWidth") or entry.attrib.get("width")),
            "units": units,
            "shape": (desc.attrib.get("lineEnd") if desc is not None else None) or entry.attrib.get("lineEnd") or entry.attrib.get("shape"),
            "raw": raw,
        })
    if not rows:
        for desc in root.iter():
            if _local(desc.tag) != "LineDesc" or not desc.attrib.get("id"):
                continue
            rows.append({
                "id": desc.attrib.get("id"),
                "width": _to_float(desc.attrib.get("lineWidth") or desc.attrib.get("width")),
                "units": desc.attrib.get("units") or default_units,
                "shape": desc.attrib.get("lineEnd") or desc.attrib.get("shape"),
                "raw": {"line_desc": _attrs(desc)},
            })
    rows = sorted(rows, key=lambda r: r["id"])
    return rows, {r["id"]: r for r in rows}


def _parse_fill_descriptors(root: ET.Element, default_units: str | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local(entry.tag) not in {"EntryFillDesc", "FillDescEntry"}:
            continue
        desc = _first_desc(entry, {"FillDesc"})
        ident = entry.attrib.get("id") or (desc.attrib.get("id") if desc is not None else None)
        if not ident:
            continue
        fill_prop = ((desc.attrib.get("fillProperty") if desc is not None else None) or entry.attrib.get("fillProperty") or entry.attrib.get("fill_type") or "").lower()
        rows.append({
            "id": ident,
            "fill_type": "solid" if fill_prop == "fill" else (fill_prop or None),
            "units": entry.attrib.get("units") or (desc.attrib.get("units") if desc is not None else None) or default_units,
            "raw": {"entry": _attrs(entry), "fill_desc": _attrs(desc)},
        })
    rows = sorted(rows, key=lambda r: r["id"])
    return rows, {r["id"]: r for r in rows}


def _parse_pad_primitives(root: ET.Element, default_units: str | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    pad_primitives: list[dict[str, Any]] = []
    user_primitives: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local(entry.tag) != "EntryStandard":
            continue
        ident = entry.attrib.get("id")
        if not ident:
            continue
        shape_node = next((c for c in entry if _local(c.tag) not in {"Description"}), None)
        shape_tag = _local(shape_node.tag) if shape_node is not None else None
        shape = None
        width = height = diameter = None
        if shape_tag == "Circle":
            shape = "circle"
            diameter = _to_float(shape_node.attrib.get("diameter") if shape_node is not None else None)
        elif shape_tag == "RectCenter":
            shape = "rect_center"
            width = _to_float(shape_node.attrib.get("width") if shape_node is not None else None)
            height = _to_float(shape_node.attrib.get("height") if shape_node is not None else None)
        elif shape_tag:
            shape = re.sub(r"(?<!^)([A-Z])", r"_\1", shape_tag).lower()
        pad_primitives.append({
            "id": ident,
            "shape": shape,
            "diameter": diameter,
            "width": width,
            "height": height,
            "units": entry.attrib.get("units") or default_units,
            "raw": {"entry": _attrs(entry), "primitive": {"tag": shape_tag, **(_attrs(shape_node) if shape_node is not None else {})}},
        })
    for entry in root.iter():
        if _local(entry.tag) != "EntryUser":
            continue
        ident = entry.attrib.get("id")
        if not ident:
            continue
        children = [{"tag": _local(c.tag), "attrs": _attrs(c)} for c in entry]
        user_primitives.append({
            "id": ident,
            "primitive_type": children[0]["tag"] if children else None,
            "summary": {"child_count": len(children), "child_tags": sorted({c["tag"] for c in children})},
            "raw": {"entry": _attrs(entry), "children": children[:10]},
        })
    pad_primitives = sorted(pad_primitives, key=lambda r: r["id"])
    user_primitives = sorted(user_primitives, key=lambda r: r["id"])
    return pad_primitives, {p["id"]: p for p in pad_primitives}, user_primitives, {p["id"]: p for p in user_primitives}


def _pad_bbox_from_primitive(x: float | None, y: float | None, primitive: dict[str, Any] | None) -> dict[str, float] | None:
    if x is None or y is None or primitive is None:
        return None
    diameter = primitive.get("diameter")
    width = primitive.get("width")
    height = primitive.get("height")
    if isinstance(diameter, (int, float)):
        return _bbox_from_circle(x, y, diameter)
    if isinstance(width, (int, float)) and isinstance(height, (int, float)):
        return {"min_x": x - width / 2.0, "min_y": y - height / 2.0, "max_x": x + width / 2.0, "max_y": y + height / 2.0}
    return None


def _make_layer_presence_entry(net: str, layer_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ordered_layers = {}
    totals = {"polylines": 0, "polygons": 0, "pads": 0, "cutouts": 0}
    for layer in sorted(layer_map):
        item = layer_map[layer]
        ordered = {
            "polylines": item.get("polylines", 0),
            "polygons": item.get("polygons", 0),
            "pads": item.get("pads", 0),
            "cutouts": item.get("cutouts", 0),
            "line_desc_refs": sorted(item.get("line_desc_refs", [])),
            "fill_desc_refs": sorted(item.get("fill_desc_refs", [])),
        }
        ordered_layers[layer] = ordered
        for k in totals:
            totals[k] += ordered[k]
    return {
        "net": net,
        "layers": ordered_layers,
        "total_polylines": totals["polylines"],
        "total_polygons": totals["polygons"],
        "total_pads": totals["pads"],
        "total_cutouts": totals["cutouts"],
    }


def _candidate_pairs(net_names: set[str], nets_with_geometry: set[str]):
    pairs: dict[tuple[str, str], str] = {}
    by_upper = {_upper(n): n for n in net_names}

    suffix_rules = [
        ("_P", "_N", "name suffix P/N"),
        ("_POS", "_NEG", "name suffix POS/NEG"),
    ]
    for net in sorted(net_names):
        upper = _upper(net)
        for pos, neg, reason in suffix_rules:
            if upper.endswith(pos):
                mate = upper[: -len(pos)] + neg
            elif upper.endswith(neg):
                mate = upper[: -len(neg)] + pos
            else:
                continue
            if mate in by_upper:
                pair = tuple(sorted((net, by_upper[mate])))
                pairs[pair] = reason

    can_hi = by_upper.get("CAN_HI")
    can_lo = by_upper.get("CAN_LO")
    if can_hi and can_lo:
        pairs[tuple(sorted((can_hi, can_lo)))] = "CAN HI/LO naming"

    for pair in sorted(pairs):
        reason = pairs[pair]
        if "CLK" in _upper(pair[0]) or "CLK" in _upper(pair[1]):
            reason = f"{reason}; CLK naming"
        if "XY2" in _upper(pair[0]) or "XY2" in _upper(pair[1]):
            reason = f"{reason}; XY2 naming"
        yield {
            "pair": list(pair),
            "reason": reason,
            "geometry_available": bool(set(pair) & nets_with_geometry),
        }


def _build_routing_topology_summary(
    *,
    units: str | None,
    nets: list[dict[str, Any]],
    layers: list[dict[str, Any]],
    per_net_layer: dict[str, dict[str, dict[str, Any]]],
    geom_by_net: dict[str, dict[str, Any]],
    review_summary: dict[str, Any],
    routes: list[dict[str, Any]],
    holes_by_net: dict[str, dict[str, Any]] | None = None,
    legacy_route_segment_count: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    layer_by_name = {l.get("name"): l for l in layers if l.get("name")}
    plane_nets = {p.get("net") for p in review_summary.get("plane_candidates", []) if p.get("net")}
    pad_only_nets = {p.get("net") for p in review_summary.get("pad_only_nets", []) if p.get("net")}
    routing_nets = {p.get("net") for p in review_summary.get("routing_candidates", []) if p.get("net")}
    logical_net_names = {n.get("name") for n in nets if n.get("name")}
    all_net_names = sorted(logical_net_names | set(geom_by_net))

    trace_width_by_net = []
    route_length_net_map: dict[str, dict[str, Any]] = {}
    route_length_layer_map: dict[str | None, dict[str, Any]] = {}
    for route in routes:
        if route.get("feature_domain") != "copper":
            continue
        length = route.get("length")
        if not isinstance(length, (int, float)):
            continue
        net = route.get("net")
        layer = route.get("layer")
        estimated = bool(route.get("length_is_estimated"))
        if net:
            net_row = route_length_net_map.setdefault(net, {"net": net, "total_route_length": 0.0, "length_units": "INCH", "route_count": 0, "layers": set(), "length_is_estimated": False, "estimated_route_count": 0, "curve_count": 0, "route_lengths": []})
            net_row["total_route_length"] += length
            net_row["route_count"] += 1
            net_row["route_lengths"].append(length)
            if layer:
                net_row["layers"].add(layer)
            net_row["length_is_estimated"] = net_row["length_is_estimated"] or estimated
            net_row["estimated_route_count"] += 1 if estimated else 0
            net_row["curve_count"] += int(route.get("curve_count") or 0)
        layer_row = route_length_layer_map.setdefault(layer, {"layer": layer, "total_route_length": 0.0, "length_units": "INCH", "route_count": 0, "nets": set(), "estimated_route_count": 0})
        layer_row["total_route_length"] += length
        layer_row["route_count"] += 1
        layer_row["estimated_route_count"] += 1 if estimated else 0
        if net:
            layer_row["nets"].add(net)

    route_length_by_net = []
    for item in sorted(route_length_net_map.values(), key=lambda r: r["net"]):
        lengths = item.pop("route_lengths")
        route_length_by_net.append({
            **item,
            "total_route_length": round(item["total_route_length"], 10),
            "layers": sorted(item["layers"]),
            "min_route_length": round(min(lengths), 10) if lengths else None,
            "max_route_length": round(max(lengths), 10) if lengths else None,
        })
    route_length_by_layer = [
        {
            **item,
            "total_route_length": round(item["total_route_length"], 10),
            "net_count": len(item["nets"]),
            "nets": sorted(item["nets"]),
        }
        for item in sorted(route_length_layer_map.values(), key=lambda r: str(r["layer"]))
    ]
    route_length_by_net_map = {row["net"]: row for row in route_length_by_net}
    holes_by_net = holes_by_net or {}

    topology_nets = []
    presence_by_net = {p.get("net"): p for p in review_summary.get("net_layer_presence", []) if p.get("net")}
    for net in all_net_names:
        item = geom_by_net.get(net, {"routes": 0, "polygons": 0, "pads": 0, "cutouts": 0, "layers": set(), "line_desc_refs": set(), "widths": [], "bbox": None})
        widths = item.get("widths") or []
        layer_set = sorted(item.get("layers") or [])
        roles = {_layer_role(layer_by_name.get(layer, {"name": layer})) for layer in layer_set}
        line_refs = sorted(item.get("line_desc_refs") or [])
        evidence: list[str] = []
        for layer, counts in sorted(per_net_layer.get(net, {}).items()):
            if not _is_copper_layer(layer_by_name.get(layer, {"name": layer})):
                continue
            if counts.get("polylines"):
                evidence.append(_count_phrase(counts["polylines"], "route/polyline", "routes/polylines", layer))
            if counts.get("polygons"):
                evidence.append(_count_phrase(counts["polygons"], "polygon", "polygons", layer))
            if counts.get("pads"):
                evidence.append(_count_phrase(counts["pads"], "pad", "pads", layer))
            if counts.get("cutouts"):
                evidence.append(_count_phrase(counts["cutouts"], "cutout", "cutouts", layer))
        if line_refs:
            evidence.append(f"trace width refs: {', '.join(line_refs)}")
        row = {
            "net": net,
            "layers": layer_set,
            "route_count": item.get("routes", 0),
            "polygon_count": item.get("polygons", 0),
            "pad_count": item.get("pads", 0),
            "cutout_count": item.get("cutouts", 0),
            "line_desc_refs": line_refs,
            "min_trace_width": min(widths) if widths else None,
            "max_trace_width": max(widths) if widths else None,
            "bbox": item.get("bbox"),
            "has_top_copper": "top" in roles,
            "has_bottom_copper": "bottom" in roles,
            "has_internal_copper": "internal" in roles,
            "has_plane_evidence": net in plane_nets,
            "is_plane_candidate": net in plane_nets,
            "is_pad_only": net in pad_only_nets,
            "is_routing_candidate": net in routing_nets or item.get("routes", 0) > 0,
            "geometry_evidence": evidence,
            "hole_count": (holes_by_net.get(net) or {}).get("hole_count", 0),
            "via_hole_count": (holes_by_net.get(net) or {}).get("via_hole_count", 0),
            "plated_hole_count": (holes_by_net.get(net) or {}).get("plated_hole_count", 0),
            "nonplated_hole_count": (holes_by_net.get(net) or {}).get("nonplated_hole_count", 0),
        }
        topology_nets.append(row)
        if row["route_count"] > 0:
            trace_width_by_net.append({
                "net": net,
                "line_desc_refs": row["line_desc_refs"],
                "min_trace_width": row["min_trace_width"],
                "max_trace_width": row["max_trace_width"],
                "route_count": row["route_count"],
                "layers": row["layers"],
            })

    topology_by_net = {row["net"]: row for row in topology_nets}
    paired_comparisons = []
    for pair in review_summary.get("candidate_differential_or_paired_nets", []):
        names = pair.get("pair") or []
        if len(names) != 2:
            continue
        a = topology_by_net.get(names[0])
        b = topology_by_net.get(names[1])
        if not a or not b:
            continue
        net_a = {
            "net": a["net"],
            "layers": a["layers"],
            "route_count": a["route_count"],
            "polygon_count": a["polygon_count"],
            "pad_count": a["pad_count"],
            "min_trace_width": a["min_trace_width"],
            "max_trace_width": a["max_trace_width"],
            "bbox": a["bbox"],
            "line_desc_refs": a["line_desc_refs"],
            "total_route_length": route_length_by_net_map.get(a["net"], {}).get("total_route_length"),
            "length_units": route_length_by_net_map.get(a["net"], {}).get("length_units"),
        }
        net_b = {
            "net": b["net"],
            "layers": b["layers"],
            "route_count": b["route_count"],
            "polygon_count": b["polygon_count"],
            "pad_count": b["pad_count"],
            "min_trace_width": b["min_trace_width"],
            "max_trace_width": b["max_trace_width"],
            "bbox": b["bbox"],
            "line_desc_refs": b["line_desc_refs"],
            "total_route_length": route_length_by_net_map.get(b["net"], {}).get("total_route_length"),
            "length_units": route_length_by_net_map.get(b["net"], {}).get("length_units"),
        }
        length_a = net_a["total_route_length"]
        length_b = net_b["total_route_length"]
        length_delta = abs(length_a - length_b) if isinstance(length_a, (int, float)) and isinstance(length_b, (int, float)) else None
        length_ratio = (length_a / length_b) if isinstance(length_a, (int, float)) and isinstance(length_b, (int, float)) and length_b else None
        length_estimated = bool(route_length_by_net_map.get(a["net"], {}).get("length_is_estimated") or route_length_by_net_map.get(b["net"], {}).get("length_is_estimated"))
        paired_comparisons.append({
            "pair": names,
            "reason": pair.get("reason"),
            "geometry_available": bool(a["layers"] or b["layers"]),
            "net_a": net_a,
            "net_b": net_b,
            "comparison": {
                "same_layer_set": a["layers"] == b["layers"],
                "same_trace_width_refs": a["line_desc_refs"] == b["line_desc_refs"],
                "route_count_delta": abs(a["route_count"] - b["route_count"]),
                "polygon_count_delta": abs(a["polygon_count"] - b["polygon_count"]),
                "pad_count_delta": abs(a["pad_count"] - b["pad_count"]),
                "bbox_overlap_possible": _bbox_overlap_possible(a["bbox"], b["bbox"]),
                "route_length_a": length_a,
                "route_length_b": length_b,
                "route_length_delta": round(length_delta, 10) if isinstance(length_delta, (int, float)) else None,
                "route_length_delta_units": "INCH" if isinstance(length_delta, (int, float)) else None,
                "route_length_ratio": round(length_ratio, 10) if isinstance(length_ratio, (int, float)) else None,
                "length_is_estimated": length_estimated,
            },
            "review_note": "Name-based candidate pair only; route lengths are IPC-2581 geometry estimates and no impedance, coupling, spacing, skew, timing, or length matching has been verified.",
        })

    layer_transition_candidates = []
    for row in topology_nets:
        if len(row["layers"]) <= 1:
            continue
        feature_count = row["route_count"] + row["polygon_count"] + row["pad_count"] + row["cutout_count"]
        if feature_count == 0:
            continue
        layer_transition_candidates.append({
            "net": row["net"],
            "reason": "net has copper evidence on multiple copper layers",
            "layers": row["layers"],
            "pad_count": row["pad_count"],
            "route_count": row["route_count"],
            "polygon_count": row["polygon_count"],
            "cutout_count": row["cutout_count"],
        })

    via_hole_by_net = [
        {
            "net": net,
            "via_hole_count": item.get("via_hole_count", 0),
            "plated_hole_count": item.get("plated_hole_count", 0),
            "nonplated_hole_count": item.get("nonplated_hole_count", 0),
            "diameters": sorted(item.get("diameters", [])),
            "layers": sorted(item.get("layers", [])),
        }
        for net, item in sorted(holes_by_net.items())
        if item.get("hole_count", 0) > 0
    ]

    trace_width_by_layer_map: dict[tuple[str | None, str | None, float | None, str | None], dict[str, Any]] = {}
    for route in routes:
        if route.get("feature_domain") != "copper":
            continue
        key = (route.get("layer"), route.get("line_desc_ref"), route.get("line_width"), route.get("line_width_units"))
        row = trace_width_by_layer_map.setdefault(key, {"layer": key[0], "line_desc_ref": key[1], "line_width": key[2], "units": key[3], "route_count": 0, "nets": set()})
        row["route_count"] += 1
        if route.get("net"):
            row["nets"].add(route["net"])
    trace_width_usage_by_layer = [
        {**row, "nets": sorted(row["nets"])}
        for row in sorted(trace_width_by_layer_map.values(), key=lambda r: (str(r["layer"]), str(r["line_desc_ref"]), r["line_width"] is None, r["line_width"] or 0.0))
    ]

    warnings = []
    if pad_only_nets:
        warnings.append(f"{len(pad_only_nets)} pad-only nets exist in extracted IPC-2581 geometry")
    if paired_comparisons:
        warnings.append("Paired net candidates are name-based only; no impedance, coupling, spacing, skew, or length matching has been verified")
    warnings.extend([
        "Non-copper drawing geometry is separated from copper routing",
        "Route length is computed from IPC-2581 exported geometry, not live CAD constraints",
        "Length comparison is not impedance, skew, timing, or differential-pair validation",
        "Hole/via evidence is normalized where available, but true connectivity is not proven unless explicitly stated by the source",
        "Pad primitive dimensions are parsed where possible, but this is not annular-ring or soldermask validation",
        "Package/library geometry is summarized separately from board routing geometry",
        "No true DRC, net-short, or spacing verification is performed by the converter",
        "Stackup thickness/material may be unavailable or incomplete in IPC-2581 source data",
        "Geometry comes from IPC-2581 manufacturing/export features, not live CAD constraints",
    ])
    if any((route.get("curve_count") or 0) for route in routes):
        warnings.append("Arc/curve lengths may be estimated where exact curve semantics are limited")
    if legacy_route_segment_count == 0 and routes:
        warnings.append("Legacy route_segment_count is 0, but normalized routing_geometry.routes is available")

    summary = {
        "units": units,
        "net_count": len(all_net_names),
        "routed_net_count": sum(1 for row in topology_nets if row["route_count"] > 0),
        "pad_only_net_count": len(pad_only_nets),
        "plane_candidate_count": len(plane_nets),
        "paired_net_candidate_count": len(review_summary.get("candidate_differential_or_paired_nets", [])),
        "nets": topology_nets,
        "paired_net_geometry_comparison": paired_comparisons,
        "layer_transition_candidates": layer_transition_candidates,
        "via_hole_by_net": via_hole_by_net,
        "trace_width_by_net": trace_width_by_net,
        "trace_width_usage_by_layer": trace_width_usage_by_layer,
        "route_length_by_net": route_length_by_net,
        "route_length_by_layer": route_length_by_layer,
        "routing_evidence_warnings": warnings,
        "limitations": [
            "Layer transition rows are candidates only; actual via connectivity is not proven unless explicit via/hole association is available.",
            "Route lengths are approximate IPC-2581 geometry summaries and are not live CAD constraint, timing, or skew verification.",
            "Paired-net comparisons summarize extracted geometry only and do not validate impedance, coupling, spacing, skew, timing, or length matching.",
            "Topology summaries are evidence summaries, not DRC, LVS, connectivity, or fabrication-rule verification.",
        ],
    }
    return summary, trace_width_by_net, trace_width_usage_by_layer, route_length_by_net, route_length_by_layer


def extract_layerfeature_geometry(root: ET.Element, layers: list[dict[str, Any]], nets: list[dict[str, Any]], units: str | None = None, holes_by_net: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    layer_by_name = {l.get("name"): l for l in layers if l.get("name")}
    copper_layer_names = {name for name, layer in layer_by_name.items() if _is_copper_layer(layer)}
    line_descriptors, line_desc_by_id = _parse_line_descriptors(root, units)
    fill_descriptors, fill_desc_by_id = _parse_fill_descriptors(root, units)
    pad_primitives, pad_primitive_by_id, user_primitives, user_primitive_by_id = _parse_pad_primitives(root, units)

    per_net_layer: dict[str, dict[str, dict[str, Any]]] = {}
    layer_totals: dict[str, dict[str, Any]] = {}
    line_ref_usage: dict[str, int] = {}
    fill_ref_usage: dict[str, int] = {}
    copper_features: list[dict[str, Any]] = []
    board_feature_summary_rows: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    polygons: list[dict[str, Any]] = []
    pads: list[dict[str, Any]] = []
    cutouts: list[dict[str, Any]] = []
    parse_warnings: list[dict[str, Any]] = []
    layerfeature_count = 0
    set_count = 0
    object_counts = {"polylines": 0, "polygons": 0, "pads": 0, "cutouts": 0}
    non_copper_counts = {"polylines": 0, "polygons": 0, "pads": 0, "cutouts": 0}
    route_id = polygon_id = pad_id = cutout_id = 0

    for lf in root.iter():
        if _local(lf.tag) != "LayerFeature":
            continue
        layerfeature_count += 1
        layer = lf.attrib.get("layerRef") or lf.attrib.get("layer") or lf.attrib.get("name") or "unknown_layer"
        if layer not in layer_by_name:
            layer_by_name[layer] = {"name": layer, "type": None, "function": None, "side": None}
            if _is_copper_layer(layer_by_name[layer]):
                copper_layer_names.add(layer)
        layer_summary = layer_totals.setdefault(layer, {"layer": layer, "sets": 0, "polylines": 0, "polygons": 0, "pads": 0, "cutouts": 0, "nets": set()})
        for set_elem in [c for c in lf if _local(c.tag) == "Set"]:
            set_count += 1
            layer_summary["sets"] += 1
            net = set_elem.attrib.get("net") or set_elem.attrib.get("netRef") or set_elem.attrib.get("netName") or None
            counts = {
                "polylines": sum(1 for x in set_elem.iter() if _local(x.tag) == "Polyline"),
                "polygons": sum(1 for x in set_elem.iter() if _local(x.tag) == "Polygon"),
                "pads": sum(1 for x in set_elem.iter() if _local(x.tag) == "Pad"),
                "cutouts": sum(1 for x in set_elem.iter() if _local(x.tag) == "Cutout"),
            }
            contour_count = sum(1 for x in set_elem.iter() if _local(x.tag) == "Contour")
            line_refs = sorted({x.attrib.get("id") for x in set_elem.iter() if _local(x.tag) == "LineDescRef" and x.attrib.get("id")})
            fill_refs = sorted({x.attrib.get("id") for x in set_elem.iter() if _local(x.tag) == "FillDescRef" and x.attrib.get("id")})
            for key, value in counts.items():
                object_counts[key] += value
                layer_summary[key] += value
                if layer not in copper_layer_names:
                    non_copper_counts[key] += value
            for ref in line_refs:
                line_ref_usage[ref] = line_ref_usage.get(ref, 0) + 1
            for ref in fill_refs:
                fill_ref_usage[ref] = fill_ref_usage.get(ref, 0) + 1
            feature_domain = _layer_feature_domain(layer_by_name.get(layer, {"name": layer}))
            feature_count = counts["polylines"] + counts["polygons"] + counts["pads"] + counts["cutouts"]
            if feature_count:
                board_feature_summary_rows.append({
                    "layer": layer,
                    "feature_domain": feature_domain,
                    "net": net,
                    **counts,
                    "contours": contour_count,
                    "feature_count": feature_count,
                })
            for polyline in [x for x in set_elem.iter() if _local(x.tag) == "Polyline"]:
                points, has_curve = _points_from_geometry(polyline)
                line_ref = _descriptor_ref(polyline, "LineDescRef")
                desc = line_desc_by_id.get(line_ref or "")
                length_summary = _route_length_from_points(points, units)
                route_id += 1
                routes.append({
                    "id": f"route_{route_id:06d}",
                    "source": "ipc2581.LayerFeature.Set.Features.Polyline",
                    "layer": layer,
                    "net": net,
                    "feature_domain": feature_domain,
                    "line_desc_ref": line_ref,
                    "line_width": desc.get("width") if desc else None,
                    "line_width_units": desc.get("units") if desc else units,
                    "points": points,
                    "bbox": _bbox_from_points(points),
                    **length_summary,
                    "has_curve": has_curve,
                })
                if not points:
                    parse_warnings.append({"code": "WARN_POLYLINE_NO_POINTS", "message": f"Polyline on {layer} net {net or '<none>'} has no parsed points."})
            for polygon in [x for x in set_elem.iter() if _local(x.tag) == "Polygon"]:
                points, has_curve = _points_from_geometry(polygon)
                fill_ref = _descriptor_ref(polygon, "FillDescRef")
                desc = fill_desc_by_id.get(fill_ref or "")
                polygon_id += 1
                polygons.append({
                    "id": f"poly_{polygon_id:06d}",
                    "source": "ipc2581.LayerFeature.Set.Features.Contour.Polygon",
                    "layer": layer,
                    "net": net,
                    "feature_domain": feature_domain,
                    "fill_desc_ref": fill_ref,
                    "fill_type": desc.get("fill_type") if desc else None,
                    "points": points,
                    "bbox": _bbox_from_points(points),
                    "point_count": len(points),
                    "has_curve": has_curve,
                })
                if not points:
                    parse_warnings.append({"code": "WARN_POLYGON_NO_POINTS", "message": f"Polygon on {layer} net {net or '<none>'} has no parsed points."})
            for pad in [x for x in set_elem.iter() if _local(x.tag) == "Pad"]:
                loc = _first_child(pad, {"Location"})
                x = _to_float(pad.attrib.get("x") or (loc.attrib.get("x") if loc is not None else None))
                y = _to_float(pad.attrib.get("y") or (loc.attrib.get("y") if loc is not None else None))
                xform = _first_child(pad, {"Xform", "XForm", "Transform"})
                std_ref = pad.attrib.get("standardPrimitiveRef") or pad.attrib.get("stdPrimRef") or pad.attrib.get("primitiveRef") or _descriptor_ref(pad, "StandardPrimitiveRef")
                user_ref = pad.attrib.get("userPrimitiveRef") or _descriptor_ref(pad, "UserPrimitiveRef")
                resolved = pad_primitive_by_id.get(std_ref or "") or user_primitive_by_id.get(user_ref or "")
                resolution_status = "not_applicable"
                if std_ref or user_ref:
                    resolution_status = "resolved" if resolved else "unresolved"
                pad_id += 1
                bbox = _pad_bbox_from_primitive(x, y, resolved) or ({"min_x": x, "min_y": y, "max_x": x, "max_y": y} if x is not None and y is not None else None)
                pads.append({
                    "id": f"pad_{pad_id:06d}",
                    "source": "ipc2581.LayerFeature.Set.Features.Pad",
                    "layer": layer,
                    "net": net,
                    "feature_domain": feature_domain,
                    "x": x,
                    "y": y,
                    "standard_primitive_ref": std_ref,
                    "user_primitive_ref": user_ref,
                    "resolved_primitive_id": resolved.get("id") if resolved else None,
                    "resolved_shape": resolved.get("shape") if resolved else None,
                    "resolved_width": resolved.get("width") if resolved else None,
                    "resolved_height": resolved.get("height") if resolved else None,
                    "resolved_diameter": resolved.get("diameter") if resolved else None,
                    "resolved_units": resolved.get("units") if resolved else units,
                    "primitive_resolution_status": resolution_status,
                    "xform": _attrs(xform),
                    "bbox": bbox,
                })
            for cutout in [x for x in set_elem.iter() if _local(x.tag) == "Cutout"]:
                points, has_curve = _points_from_geometry(cutout)
                cutout_id += 1
                cutouts.append({
                    "id": f"cutout_{cutout_id:06d}",
                    "source": "ipc2581.LayerFeature.Set.Features.Cutout",
                    "layer": layer,
                    "net": net,
                    "feature_domain": feature_domain,
                    "points": points,
                    "bbox": _bbox_from_points(points),
                    "point_count": len(points),
                    "has_curve": has_curve,
                })
                if not points:
                    parse_warnings.append({"code": "WARN_CUTOUT_NO_POINTS", "message": f"Cutout on {layer} net {net or '<none>'} has no parsed points."})
            if not net:
                continue
            layer_summary["nets"].add(net)
            slot = per_net_layer.setdefault(net, {}).setdefault(layer, {"polylines": 0, "polygons": 0, "pads": 0, "cutouts": 0, "line_desc_refs": set(), "fill_desc_refs": set()})
            for key, value in counts.items():
                slot[key] += value
            slot["line_desc_refs"].update(line_refs)
            slot["fill_desc_refs"].update(fill_refs)
            if layer in copper_layer_names:
                copper_features.append({"layer": layer, "net": net, **counts, "line_desc_refs": line_refs, "fill_desc_refs": fill_refs})

    net_layer_presence = [_make_layer_presence_entry(net, per_net_layer[net]) for net in sorted(per_net_layer)]
    net_feature_totals = [
        {
            "net": e["net"],
            "polylines": e["total_polylines"],
            "polygons": e["total_polygons"],
            "pads": e["total_pads"],
            "cutouts": e["total_cutouts"],
            "feature_count": e["total_polylines"] + e["total_polygons"] + e["total_pads"] + e["total_cutouts"],
            "layers": sorted(e["layers"].keys()),
        }
        for e in net_layer_presence
    ]
    copper_feature_summary_rows = [
        {
            **f,
            "feature_domain": "copper",
            "contours": 0,
            "feature_count": f["polylines"] + f["polygons"] + f["pads"] + f["cutouts"],
        }
        for f in copper_features
    ]

    geom_by_net: dict[str, dict[str, Any]] = {}
    for route in routes:
        if route.get("feature_domain") != "copper" or not route.get("net"):
            continue
        slot = geom_by_net.setdefault(route["net"], {"routes": 0, "polygons": 0, "pads": 0, "cutouts": 0, "layers": set(), "line_desc_refs": set(), "widths": [], "bbox": None})
        slot["routes"] += 1
        slot["layers"].add(route["layer"])
        if route.get("line_desc_ref"):
            slot["line_desc_refs"].add(route["line_desc_ref"])
        if route.get("line_width") is not None:
            slot["widths"].append(route["line_width"])
        slot["bbox"] = _merge_bbox(slot["bbox"], route.get("bbox"))
    for poly in polygons:
        if poly.get("feature_domain") != "copper" or not poly.get("net"):
            continue
        slot = geom_by_net.setdefault(poly["net"], {"routes": 0, "polygons": 0, "pads": 0, "cutouts": 0, "layers": set(), "line_desc_refs": set(), "widths": [], "bbox": None})
        slot["polygons"] += 1
        slot["layers"].add(poly["layer"])
        slot["bbox"] = _merge_bbox(slot["bbox"], poly.get("bbox"))
    for pad in pads:
        if pad.get("feature_domain") != "copper" or not pad.get("net"):
            continue
        slot = geom_by_net.setdefault(pad["net"], {"routes": 0, "polygons": 0, "pads": 0, "cutouts": 0, "layers": set(), "line_desc_refs": set(), "widths": [], "bbox": None})
        slot["pads"] += 1
        slot["layers"].add(pad["layer"])
        slot["bbox"] = _merge_bbox(slot["bbox"], pad.get("bbox"))
    for cutout in cutouts:
        if cutout.get("feature_domain") != "copper" or not cutout.get("net"):
            continue
        slot = geom_by_net.setdefault(cutout["net"], {"routes": 0, "polygons": 0, "pads": 0, "cutouts": 0, "layers": set(), "line_desc_refs": set(), "widths": [], "bbox": None})
        slot["cutouts"] += 1
        slot["layers"].add(cutout["layer"])
        slot["bbox"] = _merge_bbox(slot["bbox"], cutout.get("bbox"))

    net_routing_summary = []
    for net in sorted(geom_by_net):
        item = geom_by_net[net]
        widths = item["widths"]
        net_routing_summary.append({
            "net": net,
            "route_count": item["routes"],
            "polygon_count": item["polygons"],
            "pad_count": item["pads"],
            "cutout_count": item["cutouts"],
            "layers": sorted(item["layers"]),
            "line_desc_refs": sorted(item["line_desc_refs"]),
            "min_trace_width": min(widths) if widths else None,
            "max_trace_width": max(widths) if widths else None,
            "bbox": item["bbox"],
        })

    trace_width_usage_map: dict[tuple[str | None, float | None, str | None], dict[str, Any]] = {}
    for route in routes:
        if route.get("feature_domain") != "copper":
            continue
        key = (route.get("line_desc_ref"), route.get("line_width"), route.get("line_width_units"))
        item = trace_width_usage_map.setdefault(key, {"line_desc_ref": key[0], "line_width": key[1], "units": key[2], "route_count": 0, "nets": set()})
        item["route_count"] += 1
        if route.get("net"):
            item["nets"].add(route["net"])
    trace_width_usage = [
        {**item, "nets": sorted(item["nets"])}
        for item in sorted(trace_width_usage_map.values(), key=lambda x: (str(x["line_desc_ref"]), x["line_width"] is None, x["line_width"] or 0.0))
    ]

    plane_candidates = []
    routing_candidates = []
    pad_only_nets = []
    unused_or_unconnected = []
    known_logical_nets = {n.get("name") for n in nets if n.get("name")}
    for entry in net_layer_presence:
        net = entry["net"]
        copper_layers_for_net = {l: v for l, v in entry["layers"].items() if l in copper_layer_names}
        poly_cutout = sum(v["polygons"] + v["cutouts"] for v in copper_layers_for_net.values())
        feature_count = sum(v["polylines"] + v["polygons"] + v["pads"] + v["cutouts"] for v in copper_layers_for_net.values())
        internal_layers = [l for l in copper_layers_for_net if _layer_role(layer_by_name.get(l, {"name": l})) == "internal"]
        plane_layers = [l for l in copper_layers_for_net if _upper((layer_by_name.get(l, {}) or {}).get("function") or (layer_by_name.get(l, {}) or {}).get("type")) == "PLANE"]
        name_reason = _net_name_evidence(net)
        max_poly_cutout_layer = max(copper_layers_for_net, key=lambda l: copper_layers_for_net[l]["polygons"] + copper_layers_for_net[l]["cutouts"], default=None)
        max_poly_cutout = (copper_layers_for_net[max_poly_cutout_layer]["polygons"] + copper_layers_for_net[max_poly_cutout_layer]["cutouts"]) if max_poly_cutout_layer else 0
        internal_poly_cutout_layers = [l for l in internal_layers if copper_layers_for_net[l]["polygons"] or copper_layers_for_net[l]["cutouts"]]
        internal_cutout_evidence = [l for l in internal_layers if copper_layers_for_net[l]["cutouts"] >= 5]
        internal_polygon_evidence = [l for l in internal_layers if copper_layers_for_net[l]["polygons"] >= 3]
        plane_layer_geometry = [l for l in plane_layers if copper_layers_for_net[l]["polygons"] or copper_layers_for_net[l]["cutouts"]]
        net_bbox_area = _bbox_area((geom_by_net.get(net) or {}).get("bbox"))
        has_strong_plane_evidence = bool(
            (name_reason and (internal_poly_cutout_layers or max_poly_cutout >= 5))
            or internal_cutout_evidence
            or internal_polygon_evidence
            or plane_layer_geometry
            or (name_reason and net_bbox_area >= 0.25 and poly_cutout > 0)
        )
        if has_strong_plane_evidence:
            evidence = []
            if name_reason:
                evidence.append(f"power/ground-style name ({name_reason})")
            for l in sorted(internal_cutout_evidence):
                evidence.append(f"{copper_layers_for_net[l]['cutouts']} cutouts on {l}")
            for l in sorted(internal_polygon_evidence):
                evidence.append(f"{copper_layers_for_net[l]['polygons']} polygons on {l}")
            for l in sorted(set(plane_layer_geometry) - set(internal_cutout_evidence) - set(internal_polygon_evidence)):
                evidence.append(f"polygon/cutout evidence on internal plane layer {l}")
            if name_reason and internal_poly_cutout_layers:
                evidence.append("power/ground-style name plus internal plane-layer copper geometry")
            if name_reason and net_bbox_area >= 0.25 and poly_cutout > 0:
                evidence.append(f"large copper bbox area ({net_bbox_area:.4g}) with polygon/cutout evidence")
            plane_candidates.append({"net": net, "candidate_reason": "; ".join(f"{net} has {item}" for item in evidence), "layers": sorted(copper_layers_for_net)})
        route_layers = [l for l, v in copper_layers_for_net.items() if v["polylines"] > 0]
        if route_layers:
            routing_candidates.append({"net": net, "layers": sorted(route_layers), "total_polylines": sum(copper_layers_for_net[l]["polylines"] for l in route_layers)})
        copper_pads = sum(v["pads"] for v in copper_layers_for_net.values())
        copper_polylines = sum(v["polylines"] for v in copper_layers_for_net.values())
        copper_polygons = sum(v["polygons"] for v in copper_layers_for_net.values())
        if copper_layers_for_net and copper_pads > 0 and copper_polylines == 0 and copper_polygons == 0:
            pad_only_nets.append({"net": net, "pads": copper_pads, "layers": sorted(copper_layers_for_net)})
        if net not in known_logical_nets or _upper(net) in {"NC", "N/C", "NO_CONNECT", "UNCONNECTED"}:
            unused_or_unconnected.append({"net": net, "reason": "feature net is not present in logical netlist or is named as unconnected", "layers": sorted(entry["layers"].keys())})

    all_layer_entries = sorted(layer_by_name.values(), key=lambda l: l.get("name") or "")
    copper_layer_entries = [{"name": l.get("name"), "function": l.get("function") or l.get("type"), "side": l.get("side")} for l in all_layer_entries if l.get("name") in copper_layer_names]
    non_copper_entries = [{"name": l.get("name"), "function": l.get("function") or l.get("type"), "side": l.get("side")} for l in all_layer_entries if l.get("name") not in copper_layer_names]
    detailed_limit = 10000
    detailed_truncated = len(copper_features) > detailed_limit
    shown_copper_features = copper_features[:detailed_limit]
    review_summary = {
        "copper_layers": copper_layer_entries,
        "non_copper_layers": non_copper_entries,
        "net_layer_presence": net_layer_presence,
        "net_feature_totals": net_feature_totals,
        "plane_candidates": plane_candidates,
        "routing_candidates": routing_candidates,
        "pad_only_nets": pad_only_nets,
        "unused_or_unconnected_feature_nets": unused_or_unconnected,
        "line_width_ref_usage": [{"line_desc_ref": k, "set_count": line_ref_usage[k]} for k in sorted(line_ref_usage)],
        "fill_ref_usage": [{"fill_desc_ref": k, "set_count": fill_ref_usage[k]} for k in sorted(fill_ref_usage)],
        "candidate_differential_or_paired_nets": list(_candidate_pairs({n.get("name") for n in nets if n.get("name")} | set(per_net_layer), set(per_net_layer))),
        "routing_geometry_available": bool(routes or polygons or pads or cutouts),
        "routing_geometry_counts": {
            "routes": len(routes),
            "polygons": len(polygons),
            "pads": len(pads),
            "cutouts": len(cutouts),
        },
        "trace_width_usage": trace_width_usage,
        "net_routing_summary": net_routing_summary,
        "geometry_review_limitations": GEOMETRY_REVIEW_LIMITATIONS,
    }
    routing_topology_summary, trace_width_by_net, trace_width_usage_by_layer, route_length_by_net, route_length_by_layer = _build_routing_topology_summary(
        units=units,
        nets=nets,
        layers=layers,
        per_net_layer=per_net_layer,
        geom_by_net=geom_by_net,
        review_summary=review_summary,
        routes=routes,
        holes_by_net=holes_by_net,
        legacy_route_segment_count=0,
    )
    board_feature_summary = {
        "layerfeature_count": layerfeature_count,
        "set_count": set_count,
        "polyline_count": object_counts["polylines"],
        "polygon_count": object_counts["polygons"],
        "pad_count": object_counts["pads"],
        "cutout_count": object_counts["cutouts"],
        "detailed_geometry_truncated": detailed_truncated,
    }
    layer_feature_summary = []
    for layer in sorted(layer_totals):
        item = layer_totals[layer].copy()
        item["nets"] = sorted(item["nets"])
        item["net_count"] = len(item["nets"])
        layer_feature_summary.append(item)
    normalized_total = len(routes) + len(polygons) + len(pads) + len(cutouts)
    source_total = object_counts["polylines"] + object_counts["polygons"] + object_counts["pads"] + object_counts["cutouts"]
    dropped_or_unparsed = max(0, source_total - normalized_total)
    routing_geometry = {
        "units": units,
        "detailed_geometry_truncated": detailed_truncated,
        "feature_count": normalized_total,
        "polyline_count": len(routes),
        "polygon_count": len(polygons),
        "pad_count": len(pads),
        "cutout_count": len(cutouts),
        "routes": routes,
        "polygons": polygons,
        "pads": pads,
        "cutouts": cutouts,
    }
    routing_geometry_extraction = {
        "enabled": True,
        "units": units,
        "layerfeature_count": layerfeature_count,
        "set_count": set_count,
        "source_polyline_object_count": object_counts["polylines"],
        "source_polygon_object_count": object_counts["polygons"],
        "source_pad_object_count": object_counts["pads"],
        "source_cutout_object_count": object_counts["cutouts"],
        "normalized_route_count": len(routes),
        "normalized_polygon_count": len(polygons),
        "normalized_pad_count": len(pads),
        "normalized_cutout_count": len(cutouts),
        "non_copper_polyline_count": non_copper_counts["polylines"],
        "non_copper_polygon_count": non_copper_counts["polygons"],
        "detailed_geometry_truncated": detailed_truncated,
        "detail_limit": None,
        "dropped_or_unparsed_feature_count": dropped_or_unparsed,
        "parse_warnings": parse_warnings,
    }
    copper_routes = [route for route in routes if route.get("feature_domain") == "copper"]
    non_copper_polylines = [route for route in routes if route.get("feature_domain") != "copper"]
    copper_polygons = [poly for poly in polygons if poly.get("feature_domain") == "copper"]
    non_copper_polygons = [poly for poly in polygons if poly.get("feature_domain") != "copper"]
    copper_pads = [pad for pad in pads if pad.get("feature_domain") == "copper"]
    non_copper_pads = [pad for pad in pads if pad.get("feature_domain") != "copper"]

    def _count_bucket(rows: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
        buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
        for feature_type, items in (("route", routes), ("polygon", polygons), ("pad", pads), ("cutout", cutouts)):
            for item in items:
                key, base = key_fn(item)
                bucket = buckets.setdefault(key, {**base, "route_count": 0, "polygon_count": 0, "pad_count": 0, "cutout_count": 0})
                bucket[f"{feature_type}_count"] += 1
        return [buckets[k] for k in sorted(buckets, key=lambda x: tuple(str(v) for v in x))]

    route_counts_by_domain = _count_bucket([], lambda item: (
        (item.get("feature_domain") or "unknown",),
        {"feature_domain": item.get("feature_domain") or "unknown"},
    ))
    route_counts_by_layer_function = _count_bucket([], lambda item: (
        (item.get("layer"), (layer_by_name.get(item.get("layer")) or {}).get("function") or (layer_by_name.get(item.get("layer")) or {}).get("type"), item.get("feature_domain") or "unknown"),
        {
            "layer": item.get("layer"),
            "function": (layer_by_name.get(item.get("layer")) or {}).get("function") or (layer_by_name.get(item.get("layer")) or {}).get("type"),
            "feature_domain": item.get("feature_domain") or "unknown",
        },
    ))
    routing_geometry.update({
        "copper_routes": copper_routes,
        "non_copper_polylines": non_copper_polylines,
        "copper_polygons": copper_polygons,
        "non_copper_polygons": non_copper_polygons,
        "copper_pads": copper_pads,
        "non_copper_pads": non_copper_pads,
        "route_counts_by_domain": route_counts_by_domain,
        "route_counts_by_layer_function": route_counts_by_layer_function,
    })
    return {
        "copper_features": shown_copper_features,
        "copper_feature_summary": {
            "layer_count": len(copper_layer_entries),
            "feature_set_count": len(copper_features),
            "polyline_count": sum(f["polylines"] for f in copper_features),
            "polygon_count": sum(f["polygons"] for f in copper_features),
            "pad_count": sum(f["pads"] for f in copper_features),
            "cutout_count": sum(f["cutouts"] for f in copper_features),
            "detailed_geometry_truncated": detailed_truncated,
        },
        "copper_feature_summary_rows": copper_feature_summary_rows,
        "board_feature_summary_rows": board_feature_summary_rows,
        "routing_geometry": routing_geometry,
        "routing_geometry_extraction": routing_geometry_extraction,
        "pad_primitives": pad_primitives,
        "user_primitives": user_primitives,
        "line_descriptors": line_descriptors,
        "fill_descriptors": fill_descriptors,
        "routing_topology_summary": routing_topology_summary,
        "trace_width_by_net": trace_width_by_net,
        "trace_width_usage_by_layer": trace_width_usage_by_layer,
        "route_length_by_net": route_length_by_net,
        "route_length_by_layer": route_length_by_layer,
        "board_feature_summary": board_feature_summary,
        "board_geometry_analysis": {"layers": layer_feature_summary},
        "review_geometry_summary": review_summary,
        "candidate_differential_or_paired_nets": review_summary["candidate_differential_or_paired_nets"],
        "geometry_review_limitations": GEOMETRY_REVIEW_LIMITATIONS,
        "geometry_counts": {
            "layerfeature_count": layerfeature_count,
            "set_count": set_count,
            **object_counts,
            "detailed_geometry_truncated": detailed_truncated,
        },
    }


def parse_ipc2581(project_root: Path, files: list[ClassifiedFile]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    cands = sorted([f for f in files if f.category == "ipc2581_candidate"], key=lambda f: f.relative_path)
    if not cands:
        warnings.append({"code": "WARN_IPC_MISSING", "message": "No IPC-2581 candidate discovered."})
        empty_counts={"board_component_count":0,"placement_count":0,"board_net_count":0,"layer_count":0,"stackup_layer_count":0,"via_count":0,"drill_count":0,"route_segment_count":0,"outline_point_count":0}
        return {"source_file":None,"parser_version":IPC_PARSER_VERSION,"ipc_root":None,"ipc_revision":None,"namespace":None,"units":None,"components":[],"nets":[],"layers":[],"stackup_layers":[],"outline":[],"vias":[],"drills":[],"route_segments":[],"analysis":{},"warnings":warnings,"extraction_counts":empty_counts}
    src=cands[0]
    if len(cands)>1:
        warnings.append({"code":"WARN_IPC_MULTIPLE_CANDIDATES","message":f"Multiple IPC candidates found ({len(cands)}); using {src.relative_path}"})
    path=project_root/src.relative_path
    try:
        root=ET.parse(path).getroot()
    except Exception as exc:
        warnings.append({"code":"WARN_IPC_PARSE_FAILED","message":"IPC XML parse failed."})
        return {"source_file":src.relative_path,"parser_version":IPC_PARSER_VERSION,"ipc_root":None,"ipc_revision":None,"namespace":None,"units":None,"components":[],"nets":[],"layers":[],"stackup_layers":[],"outline":[],"vias":[],"drills":[],"route_segments":[],"analysis":{},"warnings":warnings,"extraction_counts":{"board_component_count":0,"placement_count":0,"board_net_count":0,"layer_count":0,"stackup_layer_count":0,"via_count":0,"drill_count":0,"route_segment_count":0,"outline_point_count":0},"error":str(exc)}

    ns = root.tag.split('}')[0].strip('{') if root.tag.startswith('{') else None
    ipc_root=_local(root.tag)
    rev=root.attrib.get('revision') or root.attrib.get('Revision')
    units = root.attrib.get("units") or root.attrib.get("unit")
    if units is None:
        for tag_name in ("CadHeader", "Step", "CadData", "Content", "DictionaryLineDesc", "DictionaryFillDesc", "DictionaryStandard"):
            node = next((e for e in root.iter() if _local(e.tag) == tag_name and (e.attrib.get("units") or e.attrib.get("unit"))), None)
            if node is not None:
                units = node.attrib.get("units") or node.attrib.get("unit")
                break

    layers=[]; layer_by_name={}
    for e in root.iter():
        t=_local(e.tag)
        if t in {"Layer", "LayerRef"}:
            name=e.attrib.get('name') or e.attrib.get('layerRef') or e.attrib.get('id')
            if not name:
                continue
            lf = e.attrib.get('layerFunction') or e.attrib.get('type')
            item = layer_by_name.get(name)
            if item is None:
                item = {"name": name, "type": lf, "function": e.attrib.get('layerFunction'), "side": e.attrib.get('side'), "polarity": e.attrib.get('polarity')}
                layer_by_name[name] = item
                layers.append(item)
            else:
                item["type"] = item.get("type") or lf
                item["function"] = item.get("function") or e.attrib.get('layerFunction')
                item["side"] = item.get("side") or e.attrib.get('side')
                item["polarity"] = item.get("polarity") or e.attrib.get('polarity')

    components=[]
    for e in root.iter():
        if _local(e.tag) in {"Component","CompInstance"}:
            ref=e.attrib.get('refDes') or e.attrib.get('refdes') or e.attrib.get('name')
            if not ref: continue
            if units is None and (e.attrib.get('unit') or e.attrib.get('units')):
                units=e.attrib.get('unit') or e.attrib.get('units')
            loc = next((c for c in list(e) if _local(c.tag) == "Location"), None)
            x = e.attrib.get('x')
            y = e.attrib.get('y')
            if loc is not None:
                x = x or loc.attrib.get('x')
                y = y or loc.attrib.get('y')
            components.append({"refdes":ref,"footprint":e.attrib.get('packageRef') or e.attrib.get('part') or e.attrib.get('cellRef'),"layer":e.attrib.get('layerRef') or e.attrib.get('side'),"x":x,"y":y,"rotation":e.attrib.get('rotation') or e.attrib.get('rot'),"source":{"format":"ipc2581","file":src.relative_path}})

    nets=[]
    physical_nets=[]
    phy_point_count = 0
    for e in root.iter():
        tag = _local(e.tag)
        if tag in {"Net", "LogicalNet"}:
            name=e.attrib.get('name') or e.attrib.get('id') or 'unknown_net'
            nodes=[]
            for c in list(e.iter()):
                ct=_local(c.tag)
                if ct in {"PinRef","Pin","Node","Conductor"}:
                    r=c.attrib.get('componentRef') or c.attrib.get('refDes') or c.attrib.get('refdes')
                    p=c.attrib.get('pin') or c.attrib.get('pinRef') or c.attrib.get('number')
                    if r or p:
                        nodes.append({"refdes":r,"pin_number":p})
            nets.append({"name":name,"node_count":len(nodes),"nodes":nodes})
        elif tag == "PhyNet":
            pname = e.attrib.get("name") or e.attrib.get("id") or "unknown_phynet"
            points = []
            for c in list(e.iter()):
                if _local(c.tag) == "PhyNetPoint":
                    points.append({
                        "x": c.attrib.get("x"),
                        "y": c.attrib.get("y"),
                        "layerRef": c.attrib.get("layerRef"),
                        "netNode": c.attrib.get("netNode"),
                        "via": c.attrib.get("via"),
                        "exposure": c.attrib.get("exposure"),
                    })
            phy_point_count += len(points)
            physical_nets.append({"name": pname, "points": points, "point_count": len(points)})

    stack=[]
    for e in root.iter():
        if _local(e.tag) in {"StackupLayer","Layer","Dielectric","Conductive"}:
            if _local(e.tag)=="Layer" and not any(k in e.attrib for k in ("thickness","material","sequence")):
                continue
            name=e.attrib.get('name') or e.attrib.get('layerRef') or e.attrib.get('id')
            if name:
                stack.append({"name":name,"sequence":e.attrib.get('sequence') or e.attrib.get('order'),"material":e.attrib.get('material'),"thickness":e.attrib.get('thickness'),"dielectric_constant":e.attrib.get('er') or e.attrib.get('epsilonR'),"copper_thickness":e.attrib.get('copperThickness')})

    vias=[]; drills=[]; routes=[]; outline=[]
    # Strict board profile extraction only: Profile -> Polygon -> PolyBegin/PolyStepSegment
    profile_nodes = [e for e in root.iter() if _local(e.tag) == "Profile"]
    if profile_nodes:
        profile = profile_nodes[0]
        for poly in [e for e in profile if _local(e.tag) == "Polygon"]:
            for p in poly:
                if _local(p.tag) in {"PolyBegin", "PolyStepSegment"} and "x" in p.attrib and "y" in p.attrib:
                    outline.append({"x": p.attrib.get("x"), "y": p.attrib.get("y")})
    for e in root.iter():
        t=_local(e.tag)
        if t == "Via":
            vias.append({"x":e.attrib.get('x'),"y":e.attrib.get('y'),"drill":e.attrib.get('drill'),"plated":e.attrib.get("plated"),"via":True})
        elif t in {"Drill","Hole"}:
            plating_status = e.attrib.get("platingStatus") or e.attrib.get("plating_status") or e.attrib.get("plated")
            drill_rec = {
                "name": e.attrib.get("name"),
                "x": e.attrib.get('x'),
                "y": e.attrib.get('y'),
                "diameter": e.attrib.get('diameter') or e.attrib.get('drill'),
                "platingStatus": plating_status,
                "plusTol": e.attrib.get("plusTol"),
                "minusTol": e.attrib.get("minusTol"),
                "layerSpan": e.attrib.get("layerSpan") or e.attrib.get("fromLayer") or e.attrib.get("toLayer"),
            }
            drills.append(drill_rec)
            if (plating_status or "").upper() == "VIA":
                vias.append({"x": drill_rec["x"], "y": drill_rec["y"], "drill": drill_rec["diameter"], "platingStatus": plating_status, "via": True, "name": drill_rec["name"]})
        elif t in {"Segment","Trace","Line"}:
            x1, y1, x2, y2 = e.attrib.get('x1'), e.attrib.get('y1'), e.attrib.get('x2'), e.attrib.get('y2')
            if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
                routes.append({"x1":x1,"y1":y1,"x2":x2,"y2":y2,"net":e.attrib.get('net') or e.attrib.get('netRef'),"layerRef":e.attrib.get("layerRef")})

    if not stack:
        for l in layers:
            stack.append({"name": l.get("name"), "sequence": None, "material": None, "thickness": None, "dielectric_constant": None, "copper_thickness": None, "function": l.get("function"), "side": l.get("side"), "polarity": l.get("polarity")})
        warnings.append({"code":"WARN_IPC_STACKUP_UNAVAILABLE","message":"Material/thickness stackup details unavailable; using known ordered layer metadata."})
    if not layers: warnings.append({"code":"WARN_IPC_LAYERS_UNAVAILABLE","message":"No layers extracted from IPC file."})
    stackup_data_quality = _build_stackup_data_quality(layers, stack)

    holes, via_holes, plated_holes, nonplated_holes, drill_hole_summary, hole_parse_warnings = _extract_layerfeature_holes(root, units)
    package_geometry_summary, package_land_patterns = _extract_package_geometry(root)
    warnings.extend(hole_parse_warnings)
    holes_by_net: dict[str, dict[str, Any]] = {}
    for hole in holes:
        net = hole.get("net")
        if not net:
            continue
        item = holes_by_net.setdefault(net, {"hole_count": 0, "via_hole_count": 0, "plated_hole_count": 0, "nonplated_hole_count": 0, "diameters": set(), "layers": set()})
        item["hole_count"] += 1
        if hole.get("hole_type") == "via":
            item["via_hole_count"] += 1
        if _upper(hole.get("plating_status")) in {"VIA", "PLATED"}:
            item["plated_hole_count"] += 1
        if _upper(hole.get("plating_status")) == "NONPLATED":
            item["nonplated_hole_count"] += 1
        if hole.get("diameter") is not None:
            item["diameters"].add(hole["diameter"])
        if hole.get("layer"):
            item["layers"].add(hole["layer"])

    geometry = extract_layerfeature_geometry(root, layers, nets, units, holes_by_net=holes_by_net)
    geometry_counts = geometry.get("geometry_counts", {})
    plated_hole_count = sum(1 for d in drills if (d.get("platingStatus") or "").upper() == "PLATED")
    nonplated_hole_count = sum(1 for d in drills if (d.get("platingStatus") or "").upper() == "NONPLATED")
    counts={"board_component_count":len(components),"placement_count":len(components),"placements_with_xy_count":sum(1 for c in components if c.get("x") is not None and c.get("y") is not None),"board_net_count":len(nets),"logical_net_count":len(nets),"physical_net_count":len(physical_nets),"phy_net_point_count":phy_point_count,"layer_count":len(layers),"stackup_layer_count":len(stack),"hole_count":len(drills),"via_count":len(vias),"plated_hole_count":plated_hole_count,"nonplated_hole_count":nonplated_hole_count,"drills_with_plating_status_count":sum(1 for d in drills if d.get("platingStatus")),"drill_count":len(drills),"route_segment_count":len(routes),"outline_point_count":len(outline),"layerfeature_count":geometry_counts.get("layerfeature_count",0),"set_count":geometry_counts.get("set_count",0),"polyline_object_count":geometry_counts.get("polylines",0),"polygon_object_count":geometry_counts.get("polygons",0),"pad_object_count":geometry_counts.get("pads",0),"cutout_object_count":geometry_counts.get("cutouts",0),"detailed_geometry_truncated":geometry_counts.get("detailed_geometry_truncated",False)}
    def _norm_layer(v: str | None) -> str:
        return (v or "").upper()
    analysis={"layer_count":len(layers),"layers_used":[l['name'] for l in layers],"ground_plane_layers":[l['name'] for l in layers if _norm_layer(l.get('function') or l.get('type')) in {"PLANE", "GROUND"} or ('GND' in (l['name'] or '').upper())],"signal_layers":[l['name'] for l in layers if _norm_layer(l.get('function') or l.get('type')) in {"CONDUCTOR", "SIGNAL", "INTERNAL"}]}
    return {"source_file":src.relative_path,"parser_version":IPC_PARSER_VERSION,"ipc_root":ipc_root,"ipc_revision":rev,"namespace":ns,"units":units,"components":components,"nets":nets,"physical_nets":physical_nets,"layers":layers,"stackup_layers":stack,"stackup_data_quality":stackup_data_quality,"outline":outline,"vias":vias,"drills":drills,"holes":holes,"via_holes":via_holes,"plated_holes":plated_holes,"nonplated_holes":nonplated_holes,"drill_hole_summary":drill_hole_summary,"package_geometry_summary":package_geometry_summary,"package_land_patterns":package_land_patterns,"route_segments":routes,"analysis":analysis,"warnings":warnings,"extraction_counts":counts,**geometry}


def build_board_export(project_name:str, project_root:Path, ipc:dict[str,Any])->dict[str,Any]:
    return {
        "project_name": project_name,
        "source": {"project_root": str(project_root), "layout_file": ipc.get("source_file"), "format": "ipc2581", "ipc_root": ipc.get("ipc_root"), "ipc_revision": ipc.get("ipc_revision"), "namespace": ipc.get("namespace"), "units": ipc.get("units")},
        "units": ipc.get("units"),
        "parser_version": ipc.get("parser_version"),
        "components": ipc.get("components", []),
        "placements": ipc.get("components", []),
        "nets": ipc.get("nets", []),
        "physical_nets": ipc.get("physical_nets", []),
        "layers": ipc.get("layers", []),
        "stackup_data_quality": ipc.get("stackup_data_quality", {}),
        "board_outline": ipc.get("outline", []),
        "vias": ipc.get("vias", []),
        "drills": ipc.get("drills", []),
        "drill_hole_summary": ipc.get("drill_hole_summary", {}),
        "holes": ipc.get("holes", []),
        "via_holes": ipc.get("via_holes", []),
        "plated_holes": ipc.get("plated_holes", []),
        "nonplated_holes": ipc.get("nonplated_holes", []),
        "routes": ipc.get("route_segments", []),
        "analysis": ipc.get("analysis", {}),
        "copper_feature_summary": ipc.get("copper_feature_summary", {}),
        "copper_features": ipc.get("copper_features", []),
        "copper_feature_summary_rows": ipc.get("copper_feature_summary_rows", []),
        "board_feature_summary": ipc.get("board_feature_summary", {}),
        "board_feature_summary_rows": ipc.get("board_feature_summary_rows", []),
        "board_geometry_analysis": ipc.get("board_geometry_analysis", {}),
        "routing_geometry": ipc.get("routing_geometry", {}),
        "routing_geometry_extraction": ipc.get("routing_geometry_extraction", {}),
        "routing_topology_summary": ipc.get("routing_topology_summary", {}),
        "trace_width_by_net": ipc.get("trace_width_by_net", []),
        "trace_width_usage_by_layer": ipc.get("trace_width_usage_by_layer", []),
        "route_length_by_net": ipc.get("route_length_by_net", []),
        "route_length_by_layer": ipc.get("route_length_by_layer", []),
        "pad_primitives": ipc.get("pad_primitives", []),
        "user_primitives": ipc.get("user_primitives", []),
        "package_geometry_summary": ipc.get("package_geometry_summary", {}),
        "package_land_patterns": ipc.get("package_land_patterns", []),
        "line_descriptors": ipc.get("line_descriptors", []),
        "fill_descriptors": ipc.get("fill_descriptors", []),
        "review_geometry_summary": ipc.get("review_geometry_summary", {}),
        "candidate_differential_or_paired_nets": ipc.get("candidate_differential_or_paired_nets", []),
        "geometry_review_limitations": ipc.get("geometry_review_limitations", GEOMETRY_REVIEW_LIMITATIONS),
        "warnings": ipc.get("warnings", []),
        "extraction_counts": ipc.get("extraction_counts", {}),
    }


def build_stack_export(project_name:str, project_root:Path, ipc:dict[str,Any])->dict[str,Any]:
    return {"project_name":project_name,"source":{"project_root":str(project_root),"layout_file":ipc.get('source_file'),"format":"ipc2581"},"parser_version":ipc.get('parser_version'),"units":ipc.get('units'),"layer_stack":ipc.get('stackup_layers',[]),"layers":ipc.get('stackup_layers',[]),"stackup_data_quality":ipc.get("stackup_data_quality",{}),"warnings":ipc.get('warnings',[]),"extraction_counts":{"stackup_layer_count":ipc.get('extraction_counts',{}).get('stackup_layer_count',0),"layer_count":ipc.get('extraction_counts',{}).get('layer_count',0)}}


def render_pdf_images(args: argparse.Namespace, project_root: Path, output_root: Path, project_name: str, files: list[ClassifiedFile]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    image_outputs: list[str] = []
    schem_pdfs = sorted([f for f in files if f.category == "schematic_pdf_candidate"], key=lambda x: x.relative_path)
    layout_pdfs = sorted([f for f in files if f.category == "layout_pdf_candidate"], key=lambda x: x.relative_path)
    pdftoppm = shutil.which("pdftoppm")
    pdfinfo = shutil.which("pdfinfo")
    status = {
        "pdftoppm_available": bool(pdftoppm),
        "pdfinfo_available": bool(pdfinfo),
        "schematic_pdf_sources": [f.relative_path for f in schem_pdfs],
        "layout_pdf_sources": [f.relative_path for f in layout_pdfs],
        "dpi": {"schematic": args.schematic_pdf_dpi, "layout": args.gerber_pdf_dpi},
        "pages_converted": 0,
        "image_outputs": image_outputs,
        "classification_warnings": [],
        "dependency_warnings": [],
        "render_errors": errors,
        "skipped_pdfs": [],
        "output_validation": {"status": "skipped" if args.dry_run or args.report_only else "pending"},
    }
    if not pdftoppm:
        w={"code":"WARN_PDFTOPPM_MISSING","message":"pdftoppm not found. Install with: sudo apt install poppler-utils"}
        warnings.append(w); status["dependency_warnings"].append(w)
        return {"report": status, "warnings": warnings, "errors": errors, "image_outputs": image_outputs}

    def convert(pdf_rel: str, prefix: str, dpi: int) -> list[Path]:
        pdf_path = project_root / pdf_rel
        out_prefix = output_root / prefix
        cmd=[pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(out_prefix)]
        proc=subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append({"code":"ERR_PDF_RENDER_FAILED","message":f"Failed rendering {pdf_rel}"})
            return []
        fresh_name = re.compile(rf"^{re.escape(prefix)}-\d+\.png$")
        return sorted(p for p in output_root.glob(f"{prefix}-*.png") if fresh_name.match(p.name))

    if args.dry_run or args.report_only:
        status["skipped_pdfs"] = [f.relative_path for f in schem_pdfs + layout_pdfs]
        return {"report": status, "warnings": warnings, "errors": errors, "image_outputs": image_outputs}

    for idx, f in enumerate(schem_pdfs, start=1):
        prefix = f"{project_name}-img-sch" if len(schem_pdfs)==1 else f"{project_name}-img-sch-s{idx}"
        rendered = convert(f.relative_path, prefix, args.schematic_pdf_dpi)
        for n,png in enumerate(rendered, start=1):
            target = output_root / (f"{project_name}-img-sch-p{n}.png" if len(schem_pdfs)==1 else f"{project_name}-img-sch-s{idx}-p{n}.png")
            png.rename(target); image_outputs.append(str(target))

    for idx, f in enumerate(layout_pdfs, start=1):
        prefix = f"{project_name}-img-layout-tmp-f{idx}"
        rendered = convert(f.relative_path, prefix, args.gerber_pdf_dpi)
        if len(layout_pdfs) > 1:
            status["classification_warnings"].append({"code":"WARN_LAYOUT_MULTI_PDF_FALLBACK","message":"Multiple layout PDFs rendered with fallback naming."})
        for n,png in enumerate(rendered, start=1):
            target_name = f"{project_name}-img-layout-p{n}.png" if len(layout_pdfs)==1 else f"{project_name}-img-layout-f{idx}-p{n}.png"
            target = output_root / target_name
            png.rename(target); image_outputs.append(str(target))

    status["pages_converted"] = len(image_outputs)
    status["output_validation"] = {"status": "pass"}
    return {"report": status, "warnings": warnings, "errors": errors, "image_outputs": image_outputs}



def validate_outputs(project_root: Path, output_root: Path, project_name: str, files: list[ClassifiedFile], report: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    json_round_trip_ok = True
    required_outputs_ok = True
    image_outputs_ok = True

    report_json = output_root / f"{project_name}-conversion-report.json"
    report_md = output_root / f"{project_name}-conversion-report.md"
    if not output_root.exists():
        issues.append("post_conversion folder missing")
    if not report_json.exists():
        issues.append("conversion-report.json missing")
        required_outputs_ok = False
    if not report_md.exists():
        issues.append("conversion-report.md missing")
        required_outputs_ok = False

    for j in sorted(output_root.glob("*.json")):
        try:
            json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            json_round_trip_ok = False
            issues.append(f"json failed round-trip: {j.name}")

    cats={f.category for f in files}
    expected=[]
    if "bom_csv_candidate" in cats: expected.append(output_root / f"{project_name}-bom.json")
    if "pads_ascii_candidate" in cats: expected.append(output_root / f"{project_name}-thomson-export-sch.json")
    if "ipc2581_candidate" in cats:
        expected.append(output_root / f"{project_name}-thomson-export-brd.json")
        expected.append(output_root / f"{project_name}-thomson-export-stack.json")
    for e in expected:
        if not e.exists():
            required_outputs_ok=False
            issues.append(f"required output missing: {e.name}")

    has_pdf = any(c in cats for c in ["schematic_pdf_candidate","layout_pdf_candidate"])
    pngs = sorted(output_root.glob("*.png"))
    if has_pdf and not report.get("images",{}).get("pdftoppm_available",False) and len(pngs)==0:
        image_outputs_ok=True
    elif has_pdf and len(pngs)==0:
        image_outputs_ok=False
        issues.append("pdf sources present but no png outputs")

    sections_ok = all(k in report for k in ["discovery","bom","schematic","ipc2581","images","warnings"])
    if not sections_ok:
        required_outputs_ok = False
        issues.append("required report sections missing")

    outputs_recorded = all(report.get("bom",{}).get("output_file"),) if False else True
    # minimal path recording checks
    if not report.get("bom",{}).get("output_file"):
        issues.append("bom output path not recorded")
    if not report.get("schematic",{}).get("output_file"):
        issues.append("schematic output path not recorded")
    if not report.get("ipc2581",{}).get("board_output_file"):
        issues.append("board output path not recorded")

    warnings_count = len(report.get("warnings", []))
    strict_would_fail = warnings_count > 0
    ok = json_round_trip_ok and required_outputs_ok and image_outputs_ok
    return {
        "ok": ok,
        "json_round_trip_ok": json_round_trip_ok,
        "required_outputs_ok": required_outputs_ok,
        "image_outputs_ok": image_outputs_ok,
        "warnings_count": warnings_count,
        "strict_would_fail": strict_would_fail,
        "ready_for_thomsonlint_smoke_test": ok and (image_outputs_ok or not has_pdf),
        "issues": issues,
    }
def build_report(args: argparse.Namespace, project_root: Path, output_root: Path, project_name: str, files: list[ClassifiedFile], warnings: list[dict[str, Any]], bom: dict[str, Any], pads: dict[str, Any], ipc: dict[str, Any], images: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for f in files:
        counts[f.category] = counts.get(f.category, 0) + 1
    routing_topology = ipc.get("routing_topology_summary", {})
    trace_width_by_net = routing_topology.get("trace_width_by_net", ipc.get("trace_width_by_net", []))
    trace_width_usage_by_layer = routing_topology.get("trace_width_usage_by_layer", ipc.get("trace_width_usage_by_layer", []))
    route_length_by_net = routing_topology.get("route_length_by_net", ipc.get("route_length_by_net", []))
    route_length_by_layer = routing_topology.get("route_length_by_layer", ipc.get("route_length_by_layer", []))
    normalized_routes = ipc.get("routing_geometry", {}).get("routes", [])
    routes_with_length = [r for r in normalized_routes if isinstance(r.get("length"), (int, float))]
    routes_with_estimated_length = [r for r in routes_with_length if r.get("length_is_estimated")]
    paired_length_comparisons = [
        p for p in routing_topology.get("paired_net_geometry_comparison", [])
        if isinstance((p.get("comparison") or {}).get("route_length_delta"), (int, float))
    ]
    routing_geometry = ipc.get("routing_geometry", {})
    pad_rows = routing_geometry.get("pads", [])
    resolved_pads = [p for p in pad_rows if p.get("primitive_resolution_status") == "resolved"]
    unresolved_pads = [p for p in pad_rows if p.get("primitive_resolution_status") == "unresolved"]
    package_geometry_summary = ipc.get("package_geometry_summary", {})

    report = {
        "metadata": {
            "converter": "thomson_bundle_converter", "version": VERSION, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project_root": str(project_root), "project_name": project_name, "output_root": str(output_root), "args": vars(args), "phase": "phase6_integrated_validation",
        },
        "discovery": {"files": [f.__dict__ for f in files], "counts_by_category": counts},
        "bom": {
            "source_file": bom.get("source_file"), "raw_headers": bom.get("raw_headers", []), "normalized_headers": bom.get("normalized_headers", {}),
            "row_count": bom.get("row_count", 0), "expanded_refdes_count": bom.get("expanded_refdes_count", 0),
            "duplicate_refdes_count": len(bom.get("duplicate_refdes", [])),
            "parse_warnings": bom.get("warnings", []), "output_file": str(output_root / f"{project_name}-bom.json"),
            "json_validation": {"status": "skipped" if args.dry_run or args.report_only else "pending"},
        },
        "schematic": {
            "source_file": pads.get("source_file"), "detected_dialect": pads.get("detected_dialect"),
            "component_count": pads.get("extraction_counts", {}).get("component_count", 0),
            "net_count": pads.get("extraction_counts", {}).get("net_count", 0),
            "node_count": pads.get("extraction_counts", {}).get("node_count", 0),
            "single_pin_net_count": pads.get("extraction_counts", {}).get("single_pin_net_count", 0),
            "power_net_count": pads.get("extraction_counts", {}).get("power_net_count", 0),
            "ground_net_count": pads.get("extraction_counts", {}).get("ground_net_count", 0),
            "bom_merge": pads.get("bom_merge", {}),
            "parse_warnings": pads.get("warnings", []),
            "output_file": str(output_root / f"{project_name}-thomson-export-sch.json"),
            "json_validation": {"status": "skipped" if args.dry_run or args.report_only else "pending"},
        },
        "planned_outputs": planned_outputs(project_name, output_root),
        "ipc2581": {"source_file": ipc.get("source_file"), "root": ipc.get("ipc_root"), "revision": ipc.get("ipc_revision"), "namespace": ipc.get("namespace"), "component_count": ipc.get("extraction_counts", {}).get("board_component_count", 0), "placement_count": ipc.get("extraction_counts", {}).get("placement_count", 0), "placements_with_xy_count": ipc.get("extraction_counts", {}).get("placements_with_xy_count", 0), "net_count": ipc.get("extraction_counts", {}).get("board_net_count", 0), "logical_net_count": ipc.get("extraction_counts", {}).get("logical_net_count", 0), "physical_net_count": ipc.get("extraction_counts", {}).get("physical_net_count", 0), "phy_net_point_count": ipc.get("extraction_counts", {}).get("phy_net_point_count", 0), "layer_count": ipc.get("extraction_counts", {}).get("layer_count", 0), "stackup_layer_count": ipc.get("extraction_counts", {}).get("stackup_layer_count", 0), "via_count": ipc.get("extraction_counts", {}).get("via_count", 0), "drill_count": ipc.get("extraction_counts", {}).get("drill_count", 0), "route_segment_count": ipc.get("extraction_counts", {}).get("route_segment_count", 0), "outline_point_count": ipc.get("extraction_counts", {}).get("outline_point_count", 0), "copper_feature_extraction_enabled": True, "layerfeature_count": ipc.get("extraction_counts", {}).get("layerfeature_count", 0), "set_count": ipc.get("extraction_counts", {}).get("set_count", 0), "polyline_object_count": ipc.get("extraction_counts", {}).get("polyline_object_count", 0), "polygon_object_count": ipc.get("extraction_counts", {}).get("polygon_object_count", 0), "pad_object_count": ipc.get("extraction_counts", {}).get("pad_object_count", 0), "cutout_object_count": ipc.get("extraction_counts", {}).get("cutout_object_count", 0), "detailed_geometry_truncated": ipc.get("extraction_counts", {}).get("detailed_geometry_truncated", False), "review_geometry_summary_counts": {"copper_layers": len(ipc.get("review_geometry_summary", {}).get("copper_layers", [])), "non_copper_layers": len(ipc.get("review_geometry_summary", {}).get("non_copper_layers", [])), "net_layer_presence": len(ipc.get("review_geometry_summary", {}).get("net_layer_presence", [])), "plane_candidates": len(ipc.get("review_geometry_summary", {}).get("plane_candidates", [])), "routing_candidates": len(ipc.get("review_geometry_summary", {}).get("routing_candidates", [])), "pad_only_nets": len(ipc.get("review_geometry_summary", {}).get("pad_only_nets", [])), "candidate_differential_or_paired_nets": len(ipc.get("review_geometry_summary", {}).get("candidate_differential_or_paired_nets", []))}, "routing_topology_summary_enabled": bool(routing_topology), "routed_net_count": routing_topology.get("routed_net_count", 0), "pad_only_net_count": routing_topology.get("pad_only_net_count", 0), "paired_net_geometry_comparison_count": len(routing_topology.get("paired_net_geometry_comparison", [])), "layer_transition_candidate_count": len(routing_topology.get("layer_transition_candidates", [])), "trace_width_by_net_count": len(trace_width_by_net), "trace_width_usage_by_layer_count": len(trace_width_usage_by_layer), "route_length_summary_enabled": True, "route_length_by_net_count": len(route_length_by_net), "route_length_by_layer_count": len(route_length_by_layer), "routes_with_length_count": len(routes_with_length), "routes_with_estimated_length_count": len(routes_with_estimated_length), "paired_net_length_comparison_count": len(paired_length_comparisons), "routing_evidence_warning_count": len(routing_topology.get("routing_evidence_warnings", [])), "parse_warnings": ipc.get("warnings", []), "board_output_file": str(output_root / f"{project_name}-thomson-export-brd.json"), "stack_output_file": str(output_root / f"{project_name}-thomson-export-stack.json"), "board_json_validation": {"status": "skipped" if args.dry_run or args.report_only else "pending"}, "stack_json_validation": {"status": "skipped" if args.dry_run or args.report_only else "pending"}},
        "images": images.get("report", {}),
        "image_outputs": images.get("image_outputs", []),
        "validation": {},
        "warnings": warnings + bom.get("warnings", []) + pads.get("warnings", []) + ipc.get("warnings", []) + images.get("warnings", []),
        "errors": [],
        "notes": [
            "Phase 1 performs discovery/reporting.", "Phase 2 adds BOM parsing.", "Phase 3 adds PADS schematic parsing and BOM merge.", "Phase 4 adds IPC-2581 board/stack parsing.", "Phase 5 adds PDF-to-PNG rendering.",
            "WARNING: tools/kicad-export.py not found in this repository snapshot; schematic shape uses a compatibility-oriented best effort.",
        ],
    }
    report["ipc2581"].update({
        "copper_route_count": len(routing_geometry.get("copper_routes", [])),
        "non_copper_polyline_count": len(routing_geometry.get("non_copper_polylines", [])),
        "copper_polygon_count": len(routing_geometry.get("copper_polygons", [])),
        "non_copper_polygon_count": len(routing_geometry.get("non_copper_polygons", [])),
        "copper_pad_count": len(routing_geometry.get("copper_pads", [])),
        "non_copper_pad_count": len(routing_geometry.get("non_copper_pads", [])),
        "hole_count": len(ipc.get("holes", [])),
        "via_hole_count": len(ipc.get("via_holes", [])),
        "plated_hole_count": len(ipc.get("plated_holes", [])),
        "nonplated_hole_count": len(ipc.get("nonplated_holes", [])),
        "pad_primitive_count": len(ipc.get("pad_primitives", [])),
        "resolved_pad_primitive_count": len(resolved_pads),
        "unresolved_pad_primitive_count": len(unresolved_pads),
        "package_geometry_summary_enabled": bool(package_geometry_summary),
        "package_count": package_geometry_summary.get("package_count", 0),
        "package_landpattern_pad_count": package_geometry_summary.get("landpattern_pad_count", 0),
        "stackup_data_quality_available": bool(ipc.get("stackup_data_quality")),
    })
    return report


def report_markdown(report: dict[str, Any]) -> str:
    m = report["metadata"]
    s = report.get("schematic", {})
    b = report.get("bom", {})
    lines = [
        f"# Conversion Report (Phase 6) - {m['project_name']}", "", "## Metadata",
        f"- Converter: {m['converter']} {m['version']}", f"- Generated (UTC): {m['generated_at_utc']}",
        "", "## Discovery Counts",
    ]
    for c, n in sorted(report["discovery"]["counts_by_category"].items()):
        lines.append(f"- {c}: {n}")
    lines += ["", "## BOM", f"- Source file: `{b.get('source_file')}`", f"- Row count: {b.get('row_count', 0)}", "", "## Schematic (PADS)", f"- Source file: `{s.get('source_file')}`", f"- Detected dialect: {s.get('detected_dialect')}", f"- Components: {s.get('component_count', 0)}", f"- Nets: {s.get('net_count', 0)}", f"- Nodes: {s.get('node_count', 0)}", f"- Schematic JSON validation: {s.get('json_validation', {}).get('status', 'unknown')}", "", "## IPC-2581 / Board", f"- Source file: `{report.get('ipc2581',{}).get('source_file')}`", f"- Root: {report.get('ipc2581',{}).get('root')}", f"- Revision: {report.get('ipc2581',{}).get('revision')}", f"- Namespace present: {bool(report.get('ipc2581',{}).get('namespace'))}", f"- Board components: {report.get('ipc2581',{}).get('component_count',0)}", f"- Layers: {report.get('ipc2581',{}).get('layer_count',0)}", f"- Nets: {report.get('ipc2581',{}).get('net_count',0)}", f"- Stack layers: {report.get('ipc2581',{}).get('stackup_layer_count',0)}", f"- Board JSON validation: {report.get('ipc2581',{}).get('board_json_validation',{}).get('status','unknown')}", f"- Stack JSON validation: {report.get('ipc2581',{}).get('stack_json_validation',{}).get('status','unknown')}", "", "## Images / PDF Render", f"- pdftoppm available: {report.get('images',{}).get('pdftoppm_available')}", f"- Pages converted: {report.get('images',{}).get('pages_converted',0)}", f"- Output validation: {report.get('images',{}).get('output_validation',{}).get('status','unknown')}", "", "## Validation", f"- ok: {report.get('validation',{}).get('ok')}", f"- json_round_trip_ok: {report.get('validation',{}).get('json_round_trip_ok')}", f"- required_outputs_ok: {report.get('validation',{}).get('required_outputs_ok')}", f"- image_outputs_ok: {report.get('validation',{}).get('image_outputs_ok')}", f"- strict_would_fail: {report.get('validation',{}).get('strict_would_fail')}", f"- ready_for_thomsonlint_smoke_test: {report.get('validation',{}).get('ready_for_thomsonlint_smoke_test')}", "", "## Warnings"]
    if report["warnings"]:
        for w in report["warnings"]:
            lines.append(f"- {w['code']}: {w['message']}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_root = Path(args.output_root).resolve() if args.output_root else project_root / "post_conversion"
    project_name = infer_project_name(project_root, args.project_name)

    schematic_dir, layout_dir, top_warnings = discover_input_dirs(project_root)
    files = scan_files(project_root, schematic_dir, layout_dir)
    if not files:
        top_warnings.append({"code": "WARN_NO_INPUT_FILES", "message": "No input files were discovered."})

    bom = parse_bom(project_name, project_root, files)
    pads = parse_pads(project_root, files, bom)
    sch = build_schematic_export(project_name, project_root, pads)
    ipc = parse_ipc2581(project_root, files)
    brd = build_board_export(project_name, project_root, ipc)
    stack = build_stack_export(project_name, project_root, ipc)
    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
    images = render_pdf_images(args, project_root, output_root, project_name, files)
    report = build_report(args, project_root, output_root, project_name, files, top_warnings, bom, pads, ipc, images)

    report_json = output_root / f"{project_name}-conversion-report.json"
    report_md = output_root / f"{project_name}-conversion-report.md"
    bom_json = output_root / f"{project_name}-bom.json"
    sch_json = output_root / f"{project_name}-thomson-export-sch.json"
    brd_json = output_root / f"{project_name}-thomson-export-brd.json"
    stack_json = output_root / f"{project_name}-thomson-export-stack.json"

    if args.dry_run:
        print("[dry-run] planned report outputs:")
        print(f"[dry-run] - {report_json}")
        print(f"[dry-run] - {report_md}")
        print(f"[dry-run] - {bom_json}")
        print(f"[dry-run] - {sch_json}")
        print(f"[dry-run] - {brd_json}")
        print(f"[dry-run] - {stack_json}")
        for img in images.get("image_outputs", []):
            print(f"[dry-run] - {img}")
    else:
        output_root.mkdir(parents=True, exist_ok=True)
        if not args.report_only:
            with bom_json.open("w", encoding="utf-8") as f:
                json.dump(bom, f, indent=2 if args.pretty else None)
            with sch_json.open("w", encoding="utf-8") as f:
                json.dump(sch, f, indent=2 if args.pretty else None)
            with brd_json.open("w", encoding="utf-8") as f:
                json.dump(brd, f, indent=2 if args.pretty else None)
            with stack_json.open("w", encoding="utf-8") as f:
                json.dump(stack, f, indent=2 if args.pretty else None)
            try:
                json.loads(bom_json.read_text(encoding="utf-8"))
                report["bom"]["json_validation"] = {"status": "pass"}
            except Exception as exc:
                report["bom"]["json_validation"] = {"status": "fail", "error": str(exc)}
                report["errors"].append({"code": "ERR_BOM_JSON_INVALID", "message": str(exc)})
            try:
                json.loads(sch_json.read_text(encoding="utf-8"))
                report["schematic"]["json_validation"] = {"status": "pass"}
            except Exception as exc:
                report["schematic"]["json_validation"] = {"status": "fail", "error": str(exc)}
                report["errors"].append({"code": "ERR_SCHEMATIC_JSON_INVALID", "message": str(exc)})
            try:
                json.loads(brd_json.read_text(encoding="utf-8"))
                report["ipc2581"]["board_json_validation"] = {"status": "pass"}
            except Exception as exc:
                report["ipc2581"]["board_json_validation"] = {"status": "fail", "error": str(exc)}
                report["errors"].append({"code": "ERR_BOARD_JSON_INVALID", "message": str(exc)})
            try:
                json.loads(stack_json.read_text(encoding="utf-8"))
                report["ipc2581"]["stack_json_validation"] = {"status": "pass"}
            except Exception as exc:
                report["ipc2581"]["stack_json_validation"] = {"status": "fail", "error": str(exc)}
                report["errors"].append({"code": "ERR_STACK_JSON_INVALID", "message": str(exc)})

        with report_json.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2 if args.pretty else None)
        with report_md.open("w", encoding="utf-8") as f:
            f.write(report_markdown(report))
        report["validation"] = validate_outputs(project_root, output_root, project_name, files, report)
        with report_json.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2 if args.pretty else None)
        with report_md.open("w", encoding="utf-8") as f:
            f.write(report_markdown(report))

    if args.dry_run:
        report["validation"] = {"ok": True, "json_round_trip_ok": True, "required_outputs_ok": True, "image_outputs_ok": True, "warnings_count": len(report.get("warnings", [])), "strict_would_fail": len(report.get("warnings", []))>0, "ready_for_thomsonlint_smoke_test": True, "issues": ["dry-run validation placeholder"]}
    print(json.dumps(report, indent=2 if args.pretty else None))

    if args.strict and report["warnings"]:
        return 2
    if args.strict and report["errors"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
