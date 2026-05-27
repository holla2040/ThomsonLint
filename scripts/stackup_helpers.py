#!/usr/bin/env python3
"""ThomsonLint Stackup Analysis Engine

Deterministic parsing and validation of PCB stackup metadata from CSV and JSON files.
Provides structural verification that LLMs cannot reliably perform on raw stackup data
(symmetry validation, thickness summation, reference plane adjacency checks).

Target Rules:
- HS_MAT_001: High-speed signal layer reference plane verification
- DFM_STACKUP_001: Finished thickness tolerance validation
- DFM_STACKUP_002: Dielectric symmetry verification

All outputs are LLM-optimized JSON with precise layer names, thicknesses, and rule IDs.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data Classes for Structured Output
# ---------------------------------------------------------------------------

@dataclass
class StackupLayer:
    """A single layer in the stackup."""
    layer_index: int
    layer_name: str
    layer_type: str  # SIGNAL, PLANE, CORE, PREPREG, SOLDERMASK, SILKSCREEN
    material: str | None
    thickness_mil: float | None
    copper_oz: float | None
    dielectric_dk: float | None  # Dielectric constant
    dielectric_df: float | None  # Dissipation factor
    function: str | None = None  # CONDUCTOR, PLANE, DIELECTRIC, etc.


@dataclass
class ThicknessResult:
    """Results of finished thickness calculation."""
    status: str = "PASS"
    total_thickness_mil: float = 0.0
    total_thickness_mm: float = 0.0
    target_thickness_mil: float = 63.0  # 1.6mm standard
    tolerance_pct: float = 10.0
    within_tolerance: bool = True
    copper_thickness_mil: float = 0.0
    dielectric_thickness_mil: float = 0.0
    other_thickness_mil: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class SymmetryViolation:
    """A stackup symmetry violation."""
    layer_pair: str
    top_layer_name: str
    bottom_layer_name: str
    top_thickness_mil: float | None
    bottom_thickness_mil: float | None
    top_type: str
    bottom_type: str
    issue: str
    rule_id: str = "DFM_STACKUP_002"


@dataclass
class SymmetryResult:
    """Results of dielectric symmetry check."""
    status: str = "PASS"
    layer_count: int = 0
    pairs_checked: int = 0
    asymmetric_pairs: list[SymmetryViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ReferencePlaneViolation:
    """A signal layer without adjacent reference plane."""
    layer_name: str
    layer_index: int
    adjacent_above: str | None
    adjacent_below: str | None
    above_type: str | None
    below_type: str | None
    issue: str
    rule_id: str = "HS_MAT_001"


@dataclass
class ReferencePlaneResult:
    """Results of adjacent reference plane check."""
    status: str = "PASS"
    signal_layers_found: int = 0
    properly_referenced: int = 0
    unreferenced_signal_layers: list[ReferencePlaneViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SchemaValidationResult:
    """Results of CSV schema validation."""
    status: str = "PASS"
    required_columns: list[str] = field(default_factory=list)
    found_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    row_count: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass
class StackupAnalysisOutput:
    """Complete stackup analysis output."""
    status: str = "PASS"
    source_file: str | None = None
    source_format: str | None = None  # csv, json
    layer_count: int = 0
    layers: list[StackupLayer] = field(default_factory=list)
    schema_validation: SchemaValidationResult | None = None
    thickness_result: ThicknessResult | None = None
    symmetry_result: SymmetryResult | None = None
    reference_plane_result: ReferencePlaneResult | None = None
    evidence_limitations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing Functions
# ---------------------------------------------------------------------------

REQUIRED_CSV_COLUMNS = [
    "layer_index",
    "layer_name", 
    "layer_type",
    "material",
    "thickness_mil",
    "copper_oz",
    "dielectric_dk",
    "dielectric_df"
]


def _to_float(v: Any) -> float | None:
    """Safely convert to float."""
    if v is None or v == "" or v == "N/A" or v == "n/a":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    """Safely convert to int."""
    if v is None or v == "" or v == "N/A" or v == "n/a":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _normalize_layer_type(raw_type: str | None) -> str:
    """Normalize layer type to standard categories."""
    if not raw_type:
        return "UNKNOWN"
    
    t = raw_type.upper().strip()
    
    # Signal/conductor layers
    if any(x in t for x in ["SIGNAL", "CONDUCTOR", "ROUTE", "ROUTING"]):
        return "SIGNAL"
    
    # Plane layers (ground/power)
    if any(x in t for x in ["PLANE", "GROUND", "GND", "POWER", "PWR", "VCC"]):
        return "PLANE"
    
    # Core (laminate)
    if "CORE" in t:
        return "CORE"
    
    # Prepreg
    if any(x in t for x in ["PREPREG", "PP", "PRE-PREG"]):
        return "PREPREG"
    
    # Soldermask
    if any(x in t for x in ["SOLDERMASK", "SOLDER", "SM", "MASK"]):
        return "SOLDERMASK"
    
    # Silkscreen
    if any(x in t for x in ["SILK", "SILKSCREEN", "LEGEND", "SS"]):
        return "SILKSCREEN"
    
    # Paste
    if any(x in t for x in ["PASTE", "STENCIL"]):
        return "PASTE"
    
    # Copper weight indicator
    if any(x in t for x in ["COPPER", "CU", "FOIL"]):
        return "COPPER"
    
    # Dielectric
    if any(x in t for x in ["DIELECTRIC", "DIEL"]):
        return "DIELECTRIC"
    
    return t


def parse_stackup_csv(path: Path) -> tuple[list[StackupLayer], SchemaValidationResult]:
    """Parse a stackup CSV file into structured layers.
    
    Expected columns: layer_index, layer_name, layer_type, material, 
                     thickness_mil, copper_oz, dielectric_dk, dielectric_df
    
    Args:
        path: Path to CSV file
        
    Returns:
        Tuple of (layers list, schema validation result)
    """
    layers = []
    validation = SchemaValidationResult(required_columns=REQUIRED_CSV_COLUMNS.copy())
    
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        # Try to detect delimiter
        sample = f.read(2048)
        f.seek(0)
        
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.DictReader(f, dialect=dialect)
        
        # Check columns
        found_cols = reader.fieldnames or []
        validation.found_columns = list(found_cols)
        
        # Normalize column names (lowercase, strip whitespace)
        col_map = {c.lower().strip(): c for c in found_cols}
        
        for req in REQUIRED_CSV_COLUMNS:
            if req.lower() not in col_map:
                validation.missing_columns.append(req)
        
        for found in found_cols:
            if found.lower().strip() not in [r.lower() for r in REQUIRED_CSV_COLUMNS]:
                validation.extra_columns.append(found)
        
        if validation.missing_columns:
            validation.status = "WARNING"
            validation.notes.append(f"Missing columns: {validation.missing_columns}")
        
        # Parse rows
        for row_num, row in enumerate(reader, start=1):
            validation.row_count += 1
            
            # Extract values with flexible column name matching
            def get_val(key: str) -> str | None:
                # Try exact match first
                if key in row:
                    return row[key]
                # Try case-insensitive
                for k, v in row.items():
                    if k.lower().strip() == key.lower():
                        return v
                return None
            
            layer_idx = _to_int(get_val("layer_index"))
            if layer_idx is None:
                layer_idx = row_num  # Use row number as fallback
            
            layer = StackupLayer(
                layer_index=layer_idx,
                layer_name=get_val("layer_name") or f"Layer_{row_num}",
                layer_type=_normalize_layer_type(get_val("layer_type")),
                material=get_val("material"),
                thickness_mil=_to_float(get_val("thickness_mil")),
                copper_oz=_to_float(get_val("copper_oz")),
                dielectric_dk=_to_float(get_val("dielectric_dk")),
                dielectric_df=_to_float(get_val("dielectric_df"))
            )
            layers.append(layer)
    
    return layers, validation


def parse_stackup_json(path: Path) -> tuple[list[StackupLayer], SchemaValidationResult]:
    """Parse a stackup JSON file into structured layers.
    
    Supports multiple JSON formats:
    - {"layers": [...]} or {"layer_stack": [...]}
    - Direct array of layer objects
    
    Args:
        path: Path to JSON file
        
    Returns:
        Tuple of (layers list, schema validation result)
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    layers = []
    validation = SchemaValidationResult(required_columns=["name", "type/function", "thickness"])
    
    # Extract layer array
    raw_layers = []
    if isinstance(data, list):
        raw_layers = data
    elif isinstance(data, dict):
        raw_layers = data.get("layers", []) or data.get("layer_stack", [])
    
    validation.row_count = len(raw_layers)
    
    for idx, raw in enumerate(raw_layers, start=1):
        if not isinstance(raw, dict):
            continue
        
        # Extract with flexible key matching
        name = raw.get("name") or raw.get("layer_name") or f"Layer_{idx}"
        layer_type = raw.get("layer_type") or raw.get("type") or raw.get("function") or "UNKNOWN"
        
        # Thickness: try multiple possible keys
        thickness = None
        for key in ["thickness_mil", "thickness", "thickness_mm"]:
            val = _to_float(raw.get(key))
            if val is not None:
                thickness = val
                # Convert mm to mil if needed
                if "mm" in key:
                    thickness = val * 39.3701
                break
        
        # Copper weight
        copper_oz = None
        for key in ["copper_oz", "copper_thickness", "copper_weight"]:
            val = _to_float(raw.get(key))
            if val is not None:
                copper_oz = val
                break
        
        layer = StackupLayer(
            layer_index=idx,
            layer_name=name,
            layer_type=_normalize_layer_type(layer_type),
            material=raw.get("material"),
            thickness_mil=thickness,
            copper_oz=copper_oz,
            dielectric_dk=_to_float(raw.get("dielectric_constant") or raw.get("dk")),
            dielectric_df=_to_float(raw.get("dissipation_factor") or raw.get("df")),
            function=raw.get("function") or raw.get("side")
        )
        layers.append(layer)
    
    # Check for missing thickness data
    missing_thickness = sum(1 for l in layers if l.thickness_mil is None)
    if missing_thickness > 0:
        validation.status = "WARNING"
        validation.notes.append(f"{missing_thickness}/{len(layers)} layers missing thickness data")
    
    if not layers:
        validation.status = "WARNING"
        validation.notes.append("No layer data found in JSON")
    
    return layers, validation


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------


def calculate_finished_thickness(layers: list[StackupLayer], 
                                  target_mil: float = 63.0,
                                  tolerance_pct: float = 10.0) -> ThicknessResult:
    """Calculate total board thickness and verify against target.
    
    Standard PCB thickness is 1.6mm (63 mils) ± 10%.
    
    Args:
        layers: List of stackup layers
        target_mil: Target thickness in mils (default: 63 = 1.6mm)
        tolerance_pct: Tolerance percentage (default: 10%)
        
    Returns:
        ThicknessResult with total thickness and tolerance check
    """
    result = ThicknessResult(
        target_thickness_mil=target_mil,
        tolerance_pct=tolerance_pct
    )
    
    copper_total = 0.0
    dielectric_total = 0.0
    other_total = 0.0
    
    missing_count = 0
    
    for layer in layers:
        t = layer.thickness_mil
        if t is None:
            missing_count += 1
            continue
        
        lt = layer.layer_type.upper()
        
        if lt in ("SIGNAL", "PLANE", "COPPER"):
            copper_total += t
        elif lt in ("CORE", "PREPREG", "DIELECTRIC"):
            dielectric_total += t
        else:
            other_total += t
    
    result.copper_thickness_mil = round(copper_total, 3)
    result.dielectric_thickness_mil = round(dielectric_total, 3)
    result.other_thickness_mil = round(other_total, 3)
    result.total_thickness_mil = round(copper_total + dielectric_total + other_total, 3)
    result.total_thickness_mm = round(result.total_thickness_mil / 39.3701, 4)
    
    if missing_count > 0:
        result.notes.append(f"{missing_count} layers missing thickness data")
    
    if result.total_thickness_mil == 0:
        result.status = "SKIPPED"
        result.notes.append("No thickness data available for calculation")
        return result
    
    # Check tolerance
    min_allowed = target_mil * (1 - tolerance_pct / 100)
    max_allowed = target_mil * (1 + tolerance_pct / 100)
    
    result.within_tolerance = min_allowed <= result.total_thickness_mil <= max_allowed
    
    if not result.within_tolerance:
        result.status = "WARNING"
        deviation_pct = abs(result.total_thickness_mil - target_mil) / target_mil * 100
        result.notes.append(
            f"Thickness {result.total_thickness_mil:.1f} mil deviates "
            f"{deviation_pct:.1f}% from target {target_mil:.1f} mil"
        )
    
    return result


def verify_dielectric_symmetry(layers: list[StackupLayer]) -> SymmetryResult:
    """Verify that dielectric layers are symmetric around the centerline.
    
    Asymmetric stackups can cause board warping during thermal cycles.
    
    Args:
        layers: List of stackup layers (ordered from top to bottom)
        
    Returns:
        SymmetryResult with asymmetric pairs identified
    """
    result = SymmetryResult(layer_count=len(layers))
    
    if len(layers) < 2:
        result.notes.append("Insufficient layers for symmetry check")
        return result
    
    # Filter to dielectric-related layers (core, prepreg)
    dielectric_layers = [
        l for l in layers 
        if l.layer_type.upper() in ("CORE", "PREPREG", "DIELECTRIC")
    ]
    
    if len(dielectric_layers) < 2:
        result.notes.append("Insufficient dielectric layers for symmetry check")
        return result
    
    # Check pairs from outside in
    n = len(layers)
    half = n // 2
    
    for i in range(half):
        top_layer = layers[i]
        bottom_layer = layers[n - 1 - i]
        
        result.pairs_checked += 1
        
        # Compare types
        type_match = top_layer.layer_type == bottom_layer.layer_type
        
        # Compare thicknesses (if available)
        thickness_match = True
        if top_layer.thickness_mil is not None and bottom_layer.thickness_mil is not None:
            # Allow 5% thickness variation
            avg = (top_layer.thickness_mil + bottom_layer.thickness_mil) / 2
            diff_pct = abs(top_layer.thickness_mil - bottom_layer.thickness_mil) / avg * 100 if avg > 0 else 0
            thickness_match = diff_pct <= 5.0
        
        if not type_match or not thickness_match:
            issues = []
            if not type_match:
                issues.append(f"Type mismatch: {top_layer.layer_type} vs {bottom_layer.layer_type}")
            if not thickness_match:
                issues.append(
                    f"Thickness mismatch: {top_layer.thickness_mil} mil vs {bottom_layer.thickness_mil} mil"
                )
            
            result.asymmetric_pairs.append(SymmetryViolation(
                layer_pair=f"L{i+1}_to_L{n-i}",
                top_layer_name=top_layer.layer_name,
                bottom_layer_name=bottom_layer.layer_name,
                top_thickness_mil=top_layer.thickness_mil,
                bottom_thickness_mil=bottom_layer.thickness_mil,
                top_type=top_layer.layer_type,
                bottom_type=bottom_layer.layer_type,
                issue="; ".join(issues)
            ))
    
    if result.asymmetric_pairs:
        result.status = "FAIL"
    
    return result


def verify_adjacent_reference_planes(layers: list[StackupLayer]) -> ReferencePlaneResult:
    """Verify that signal layers are adjacent to reference planes.
    
    Per HS_MAT_001: High-speed signal layers require adjacent solid
    reference planes (ground or power) for controlled impedance and
    proper return path.
    
    Args:
        layers: List of stackup layers (ordered from top to bottom)
        
    Returns:
        ReferencePlaneResult with unreferenced signal layers
    """
    result = ReferencePlaneResult()
    
    # Filter to copper layers only
    copper_layers = [
        (i, l) for i, l in enumerate(layers)
        if l.layer_type.upper() in ("SIGNAL", "PLANE", "CONDUCTOR")
    ]
    
    if not copper_layers:
        result.notes.append("No copper layers found in stackup")
        return result
    
    for idx, (layer_idx, layer) in enumerate(copper_layers):
        if layer.layer_type.upper() != "SIGNAL":
            continue
        
        result.signal_layers_found += 1
        
        # Find adjacent layers (in the copper layer list)
        above_type = None
        below_type = None
        above_name = None
        below_name = None
        
        if idx > 0:
            above_name = copper_layers[idx - 1][1].layer_name
            above_type = copper_layers[idx - 1][1].layer_type
        
        if idx < len(copper_layers) - 1:
            below_name = copper_layers[idx + 1][1].layer_name
            below_type = copper_layers[idx + 1][1].layer_type
        
        # Check if at least one adjacent is a plane
        has_reference_above = above_type and above_type.upper() == "PLANE"
        has_reference_below = below_type and below_type.upper() == "PLANE"
        
        if has_reference_above or has_reference_below:
            result.properly_referenced += 1
        else:
            issue = "Signal layer lacks adjacent reference plane"
            if above_type == "SIGNAL" and below_type == "SIGNAL":
                issue = "Signal layer sandwiched between signal layers (high crosstalk risk, no solid return path)"
            elif above_type == "SIGNAL" or below_type == "SIGNAL":
                issue = "Signal layer adjacent to another signal layer on one side"
            
            result.unreferenced_signal_layers.append(ReferencePlaneViolation(
                layer_name=layer.layer_name,
                layer_index=layer_idx,
                adjacent_above=above_name,
                adjacent_below=below_name,
                above_type=above_type,
                below_type=below_type,
                issue=issue
            ))
    
    if result.unreferenced_signal_layers:
        result.status = "WARNING"
    
    return result


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------


def format_output(output: StackupAnalysisOutput, json_mode: bool) -> str:
    """Format analysis output as JSON or human-readable text."""
    result: dict[str, Any] = {
        "status": output.status,
        "source_file": output.source_file,
        "source_format": output.source_format,
        "layer_count": output.layer_count,
    }
    
    if output.evidence_limitations:
        result["evidence_limitations"] = output.evidence_limitations
    
    if output.schema_validation:
        sv = output.schema_validation
        result["schema_validation"] = {
            "status": sv.status,
            "required_columns": sv.required_columns,
            "found_columns": sv.found_columns,
            "missing_columns": sv.missing_columns,
            "row_count": sv.row_count,
            "notes": sv.notes
        }
    
    if output.thickness_result:
        tr = output.thickness_result
        result["finished_thickness"] = {
            "status": tr.status,
            "total_thickness_mil": tr.total_thickness_mil,
            "total_thickness_mm": tr.total_thickness_mm,
            "target_thickness_mil": tr.target_thickness_mil,
            "tolerance_pct": tr.tolerance_pct,
            "within_tolerance": tr.within_tolerance,
            "breakdown": {
                "copper_mil": tr.copper_thickness_mil,
                "dielectric_mil": tr.dielectric_thickness_mil,
                "other_mil": tr.other_thickness_mil
            },
            "notes": tr.notes
        }
    
    if output.symmetry_result:
        sr = output.symmetry_result
        result["symmetry_check"] = {
            "status": sr.status,
            "layer_count": sr.layer_count,
            "pairs_checked": sr.pairs_checked,
            "asymmetric_count": len(sr.asymmetric_pairs),
            "asymmetric_pairs": [
                {
                    "layer_pair": ap.layer_pair,
                    "top_layer": ap.top_layer_name,
                    "bottom_layer": ap.bottom_layer_name,
                    "top_thickness_mil": ap.top_thickness_mil,
                    "bottom_thickness_mil": ap.bottom_thickness_mil,
                    "top_type": ap.top_type,
                    "bottom_type": ap.bottom_type,
                    "issue": ap.issue,
                    "rule_id": ap.rule_id
                }
                for ap in sr.asymmetric_pairs
            ],
            "notes": sr.notes
        }
    
    if output.reference_plane_result:
        rp = output.reference_plane_result
        result["adjacent_plane_check"] = {
            "status": rp.status,
            "signal_layers_found": rp.signal_layers_found,
            "properly_referenced": rp.properly_referenced,
            "unreferenced_count": len(rp.unreferenced_signal_layers),
            "unreferenced_signal_layers": [
                {
                    "layer_name": ul.layer_name,
                    "layer_index": ul.layer_index,
                    "adjacent_above": ul.adjacent_above,
                    "adjacent_below": ul.adjacent_below,
                    "above_type": ul.above_type,
                    "below_type": ul.below_type,
                    "issue": ul.issue,
                    "rule_id": ul.rule_id
                }
                for ul in rp.unreferenced_signal_layers
            ],
            "notes": rp.notes
        }
    
    if output.layers:
        result["layers"] = [
            {
                "index": l.layer_index,
                "name": l.layer_name,
                "type": l.layer_type,
                "material": l.material,
                "thickness_mil": l.thickness_mil,
                "copper_oz": l.copper_oz,
                "dielectric_dk": l.dielectric_dk,
                "dielectric_df": l.dielectric_df
            }
            for l in output.layers
        ]
    
    if json_mode:
        return json.dumps(result, indent=2)
    
    # Human-readable format
    lines = []
    lines.append(f"=== Stackup Analysis: {output.source_file} ===")
    lines.append(f"Status: {output.status}")
    lines.append(f"Format: {output.source_format}")
    lines.append(f"Layer Count: {output.layer_count}")
    lines.append("")
    
    if output.evidence_limitations:
        lines.append("Evidence Limitations:")
        for lim in output.evidence_limitations:
            lines.append(f"  - {lim}")
        lines.append("")
    
    if output.thickness_result:
        tr = output.thickness_result
        lines.append(f"--- Finished Thickness [{tr.status}] ---")
        lines.append(f"  Total: {tr.total_thickness_mil:.1f} mil ({tr.total_thickness_mm:.3f} mm)")
        lines.append(f"  Target: {tr.target_thickness_mil:.1f} mil ± {tr.tolerance_pct}%")
        lines.append(f"  Within Tolerance: {tr.within_tolerance}")
        if tr.notes:
            for n in tr.notes:
                lines.append(f"  Note: {n}")
        lines.append("")
    
    if output.symmetry_result:
        sr = output.symmetry_result
        lines.append(f"--- Symmetry Check [{sr.status}] ---")
        lines.append(f"  Pairs Checked: {sr.pairs_checked}")
        lines.append(f"  Asymmetric: {len(sr.asymmetric_pairs)}")
        for ap in sr.asymmetric_pairs[:5]:
            lines.append(f"    {ap.layer_pair}: {ap.issue}")
        lines.append("")
    
    if output.reference_plane_result:
        rp = output.reference_plane_result
        lines.append(f"--- Reference Plane Check [{rp.status}] ---")
        lines.append(f"  Signal Layers: {rp.signal_layers_found}")
        lines.append(f"  Properly Referenced: {rp.properly_referenced}")
        for ul in rp.unreferenced_signal_layers[:5]:
            lines.append(f"    {ul.layer_name}: {ul.issue}")
        lines.append("")
    
    lines.append("\n--- JSON Output ---")
    lines.append(json.dumps(result, indent=2))
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File Loading
# ---------------------------------------------------------------------------


def load_stackup_file(path: str | Path) -> tuple[list[StackupLayer], SchemaValidationResult, str]:
    """
    Load stackup data from CSV or JSON file.
    
    Returns (layers, validation_result, format_type)
    """
    path = Path(path)
    
    if not path.exists():
        raise FileNotFoundError(f"Stackup file not found: {path}")
    
    suffix = path.suffix.lower()
    
    if suffix == ".csv":
        layers, validation = parse_stackup_csv(path)
        return layers, validation, "csv"
    elif suffix == ".json":
        layers, validation = parse_stackup_json(path)
        return layers, validation, "json"
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .csv or .json")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="ThomsonLint Stackup Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stackup_helpers.py input/stackup.csv --validate-stackup --json
  python stackup_helpers.py exports/proj-stack.json --check-symmetry
  python stackup_helpers.py input/stackup.csv --check-reference-planes --json
        """
    )
    
    parser.add_argument("stackup_file", help="Path to stackup CSV or JSON file")
    parser.add_argument("--validate-stackup", action="store_true",
                        help="Run all stackup validation checks")
    parser.add_argument("--check-schema", action="store_true",
                        help="Validate CSV column schema")
    parser.add_argument("--check-thickness", action="store_true",
                        help="Calculate and verify finished thickness (DFM_STACKUP_001)")
    parser.add_argument("--target-thickness", type=float, default=63.0,
                        help="Target thickness in mils (default: 63 = 1.6mm)")
    parser.add_argument("--thickness-tolerance", type=float, default=10.0,
                        help="Thickness tolerance percentage (default: 10)")
    parser.add_argument("--check-symmetry", action="store_true",
                        help="Verify dielectric symmetry (DFM_STACKUP_002)")
    parser.add_argument("--check-reference-planes", action="store_true",
                        help="Verify signal layer reference planes (HS_MAT_001)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    
    args = parser.parse_args()
    
    output = StackupAnalysisOutput()
    
    # Load stackup file
    try:
        layers, validation, fmt = load_stackup_file(args.stackup_file)
        output.source_file = args.stackup_file
        output.source_format = fmt
        output.layer_count = len(layers)
        output.layers = layers
        output.schema_validation = validation
    except FileNotFoundError as e:
        error = {
            "status": "ERROR",
            "error": str(e),
            "stackup_file": args.stackup_file
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = {
            "status": "ERROR",
            "error": f"Failed to parse stackup: {e}",
            "stackup_file": args.stackup_file
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Determine which checks to run
    run_all = args.validate_stackup
    run_schema = args.check_schema or run_all
    run_thickness = args.check_thickness or run_all
    run_symmetry = args.check_symmetry or run_all
    run_ref_planes = args.check_reference_planes or run_all
    
    # If no specific check requested, run all
    if not any([args.check_schema, args.check_thickness, args.check_symmetry, 
                args.check_reference_planes, args.validate_stackup]):
        run_schema = run_thickness = run_symmetry = run_ref_planes = True
    
    has_failures = False
    
    # Schema validation was already done during parsing
    if run_schema and output.schema_validation:
        if output.schema_validation.status == "WARNING":
            has_failures = True
    
    # Thickness check
    if run_thickness:
        output.thickness_result = calculate_finished_thickness(
            layers,
            target_mil=args.target_thickness,
            tolerance_pct=args.thickness_tolerance
        )
        if output.thickness_result.status in ("FAIL", "WARNING"):
            has_failures = True
    
    # Symmetry check
    if run_symmetry:
        output.symmetry_result = verify_dielectric_symmetry(layers)
        if output.symmetry_result.status == "FAIL":
            has_failures = True
    
    # Reference plane check
    if run_ref_planes:
        output.reference_plane_result = verify_adjacent_reference_planes(layers)
        if output.reference_plane_result.status in ("FAIL", "WARNING"):
            has_failures = True
    
    # Check for evidence limitations
    thickness_available = any(l.thickness_mil is not None for l in layers)
    if not thickness_available:
        output.evidence_limitations.append("No thickness data available in stackup file")
    
    output.status = "FAIL" if has_failures else "PASS"
    
    print(format_output(output, args.json))
    sys.exit(0)  # Exit 0 even with failures - reserve non-zero for errors


if __name__ == "__main__":
    main()
