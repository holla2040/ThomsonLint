#!/usr/bin/env python3
"""parse_tcfx_stackup.py

Parses Cadence Allegro/OrCAD Technology Files (.tcfx) to extract physical
stackup layers, and merges the data back into the standard ThomsonLint stackup JSON.

This parser resolves null material properties in the stackup JSON by extracting:
- Layer thicknesses (normalized to target units)
- Dielectric constants (Dk)
- Loss tangents (Df)
- Material names
- Copper weights

The extracted data enables physical-math verification (impedance, thermal, etc.)
in the Saturn PCB verification engine.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Generator


def _local_name(tag: str) -> str:
    """Removes XML namespaces to simplify local tag evaluation."""
    return tag.split('}')[-1] if '}' in tag else tag


def _to_float(val: Any) -> float | None:
    """Safely converts value to float, returns None on failure."""
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


class TCFXParser:
    """Namespace-tolerant parser for Cadence technology XML files."""
    
    def __init__(self, tcfx_path: Path):
        self.tcfx_path = tcfx_path
        self.tree = ET.parse(tcfx_path)
        self.root = self.tree.getroot()
        self.units = self._parse_units()
        self.raw_layers = list(self._parse_layers())

    def _parse_units(self) -> str:
        """Determines dimension units from the technology file header."""
        for elem in self.root.iter():
            if _local_name(elem.tag) == "precision":
                units = elem.attrib.get("units")
                if units:
                    return units.upper()
        return "MIL"  # Default fallback for Cadence

    def _parse_layers(self) -> Generator[dict[str, Any], None, None]:
        """Traverses the XML to locate and parse stackup layers from the x-section."""
        dielectric_counter = 0
        
        for x_sec in self.root.iter():
            if _local_name(x_sec.tag) != "x-section":
                continue
            
            for children in x_sec:
                if _local_name(children.tag) != "children":
                    continue
                
                for obj in children:
                    if _local_name(obj.tag) != "object":
                        continue
                    
                    obj_type = obj.attrib.get("Type")
                    layer_data: dict[str, Any] = {"type": obj_type}
                    
                    # Parse attributes
                    for attr in obj:
                        if _local_name(attr.tag) != "attribute":
                            continue
                        
                        attr_name = attr.attrib.get("Name")
                        val_node = next((c for c in attr if _local_name(c.tag) == "value"), None)
                        if val_node is None:
                            continue
                        
                        val = val_node.attrib.get("Value")
                        if attr_name:
                            layer_data[attr_name] = val
                    
                    # Generate layer name for layers without CDS_LAYER_NAME
                    name = layer_data.get("CDS_LAYER_NAME")
                    
                    # Handle Dielectric layers (no name in TCFX but critical for impedance)
                    if obj_type == "Dielectric" and not name:
                        dielectric_counter += 1
                        name = f"DIELECTRIC_{dielectric_counter}"
                    elif obj_type == "Surface" and not name:
                        name = "SURFACE_BOUNDARY"
                    
                    # Skip layers without meaningful data (except surfaces)
                    if not name and obj_type not in ("Surface", "Dielectric"):
                        continue
                    
                    # Yield all physical layers (Conductor, Plane, Dielectric, Mask, Surface)
                    yield {
                        "name": name,
                        "type": obj_type,
                        "material": layer_data.get("CDS_LAYER_MATERIAL"),
                        "thickness": _to_float(layer_data.get("CDS_LAYER_THICKNESS")),
                        "dielectric_constant": _to_float(layer_data.get("CDS_LAYER_DIELECTRIC_CONSTANT")),
                        "loss_tangent": _to_float(layer_data.get("CDS_LAYER_LOSS_TANGENT")),
                        "function": layer_data.get("CDS_LAYER_FUNCTION"),
                    }


def merge_tcfx_into_stack(tcfx_parser: TCFXParser, stack_data: dict[str, Any]) -> dict[str, Any]:
    """
    Merges technology file stackup properties into standard stackup JSON structure.
    
    This function builds a complete physical stackup from the TCFX file, including
    dielectric layers that are critical for impedance calculations but not present
    in IPC-2581 exports.
    
    Args:
        tcfx_parser: Parsed TCFX data
        stack_data: Target stackup JSON dictionary
    
    Returns:
        Updated stackup dictionary with complete physical stackup
    """
    target_units = (stack_data.get("units") or "INCH").upper()
    source_units = tcfx_parser.units
    
    # Setup scale factor to normalize tech file dimensions (mils) to target JSON units
    scale_factor = 1.0
    if source_units == "MIL" and target_units in ("INCH", "IN"):
        scale_factor = 0.001
    elif source_units == "MIL" and target_units in ("MM", "MILLIMETER"):
        scale_factor = 0.0254
    elif source_units in ("MM", "MILLIMETER") and target_units in ("INCH", "IN"):
        scale_factor = 1.0 / 25.4
    
    # Build lookup of existing IPC-2581 layers for metadata (function, side, polarity)
    existing_layers_map = {}
    layer_stack = stack_data.get("layer_stack", [])
    if not layer_stack:
        layer_stack = stack_data.get("layers", [])
    for layer in layer_stack:
        name = layer.get("name")
        if name:
            existing_layers_map[name.upper()] = layer
    
    # Build complete physical stackup from TCFX (includes dielectric layers)
    physical_stackup = []
    sequence_counter = 1
    
    for tcfx_layer in tcfx_parser.raw_layers:
        layer_name = tcfx_layer.get("name")
        layer_type = tcfx_layer.get("type")
        
        # Skip Surface boundary layers (AIR)
        if layer_type == "Surface":
            continue
        
        # Apply unit scaling to thickness
        thickness_val = tcfx_layer.get("thickness")
        if thickness_val is not None:
            thickness_val = round(thickness_val * scale_factor, 6)
        
        # Determine layer function based on TCFX type
        function = tcfx_layer.get("function")
        if not function:
            if layer_type == "Conductor":
                function = "CONDUCTOR"
            elif layer_type == "Plane":
                function = "PLANE"
            elif layer_type == "Dielectric":
                function = "DIELECTRIC"
            elif layer_type == "Mask":
                function = tcfx_layer.get("function") or "SOLDERMASK"
        
        # Get existing layer metadata if available
        existing = existing_layers_map.get(layer_name.upper() if layer_name else "")
        
        # Build physical layer entry
        layer_entry = {
            "name": layer_name,
            "sequence": sequence_counter,
            "type": layer_type,
            "material": tcfx_layer.get("material"),
            "thickness": thickness_val,
            "dielectric_constant": tcfx_layer.get("dielectric_constant"),
            "loss_tangent": tcfx_layer.get("loss_tangent"),
            "function": function,
            "side": existing.get("side") if existing else _infer_side(layer_name, layer_type),
            "polarity": existing.get("polarity", "POSITIVE") if existing else "POSITIVE",
        }
        
        # For copper layers, also set copper_thickness
        if layer_type in ("Conductor", "Plane"):
            layer_entry["copper_thickness"] = thickness_val
        
        physical_stackup.append(layer_entry)
        sequence_counter += 1
    
    # Store both the physical stackup and preserve non-physical layers
    non_physical_layers = [
        layer for layer in layer_stack 
        if layer.get("function") in ("DOCUMENT", "DRILL", "ASSEMBLY", "SILKSCREEN", 
                                      "PASTEMASK", "BOARD_OUTLINE", None)
        and layer.get("name", "").upper() not in {l.get("name", "").upper() for l in physical_stackup if l.get("name")}
    ]
    
    # Combine physical stackup with non-physical layers
    complete_layer_stack = physical_stackup + non_physical_layers
    
    # Update stackup metadata
    stack_data["physical_stackup"] = physical_stackup  # Pure physical stackup for impedance calcs
    stack_data["layer_stack"] = complete_layer_stack   # Complete layer list
    stack_data["layers"] = complete_layer_stack
    
    # Count dielectric and copper layers
    dielectric_count = sum(1 for l in physical_stackup if l.get("type") == "Dielectric")
    copper_count = sum(1 for l in physical_stackup if l.get("type") in ("Conductor", "Plane"))
    
    # Update quality metadata
    quality = stack_data.setdefault("stackup_data_quality", {})
    quality["material_thickness_available"] = True
    quality["dielectric_material_available"] = dielectric_count > 0
    quality["copper_weight_available"] = copper_count > 0
    quality["source"] = "ipc2581_merged_with_allegro_tcfx"
    quality["physical_stackup_complete"] = True
    quality["dielectric_layer_count"] = dielectric_count
    quality["copper_layer_count"] = copper_count
    
    # Clear old warnings
    if "warnings" in quality:
        quality["warnings"] = [w for w in quality["warnings"] if "unavailable" not in w.lower()]
    
    if "warnings" in stack_data:
        stack_data["warnings"] = [
            w for w in stack_data["warnings"] 
            if "STACKUP_UNAVAILABLE" not in w.get("code", "")
        ]
        
    return stack_data


def _infer_side(layer_name: str | None, layer_type: str | None) -> str:
    """Infer layer side from name or type."""
    if not layer_name:
        return "INTERNAL"
    
    name_upper = layer_name.upper()
    if "TOP" in name_upper or name_upper == "TOP":
        return "TOP"
    elif "BOTTOM" in name_upper or "BOT" in name_upper or name_upper == "BOTTOM":
        return "BOTTOM"
    else:
        return "INTERNAL"


def merge_tcfx_if_available(project_root: Path, stack_data: dict[str, Any]) -> dict[str, Any]:
    """
    Automatically searches for and merges TCFX data if found.
    
    This function is called by thomson_bundle_converter.py to automatically
    enrich stackup data when a .tcfx file is present.
    
    Args:
        project_root: Project root directory
        stack_data: Stackup JSON dictionary
    
    Returns:
        Updated stackup dictionary (with or without TCFX merge)
    """
    # Search for TCFX files in common locations
    tcfx_candidates = []
    tcfx_candidates.extend(list(project_root.glob("*.tcfx")))
    tcfx_candidates.extend(list(project_root.glob("*.tcfx.txt")))
    
    input_dir = project_root / "input"
    if input_dir.exists():
        tcfx_candidates.extend(list(input_dir.glob("*.tcfx")))
        tcfx_candidates.extend(list(input_dir.glob("*.tcfx.txt")))
    
    pre_conv_dir = project_root / "pre_conversion"
    if pre_conv_dir.exists():
        tcfx_candidates.extend(list(pre_conv_dir.glob("*.tcfx")))
        tcfx_candidates.extend(list(pre_conv_dir.glob("*.tcfx.txt")))
    
    if not tcfx_candidates:
        return stack_data
    
    # Use the first found TCFX file
    tcfx_path = tcfx_candidates[0]
    
    try:
        tcfx_parser = TCFXParser(tcfx_path)
        merged_data = merge_tcfx_into_stack(tcfx_parser, stack_data)
        
        # Add merge info to stackup metadata
        if "tcfx_merge" not in merged_data:
            # Try to get relative path, fall back to absolute if not under project_root
            try:
                tcfx_rel_path = str(tcfx_path.relative_to(project_root))
            except ValueError:
                tcfx_rel_path = str(tcfx_path)
            
            merged_data["tcfx_merge"] = {
                "status": "SUCCESS",
                "tcfx_file": tcfx_rel_path,
                "layers_parsed": len(tcfx_parser.raw_layers),
                "layers_updated": sum(1 for layer in merged_data.get("layer_stack", []) 
                                     if layer.get("thickness") is not None)
            }
        
        return merged_data
    except Exception as e:
        # Add error info but don't fail the conversion
        if "tcfx_merge" not in stack_data:
            # Try to get relative path, fall back to absolute if not under project_root
            try:
                tcfx_rel_path = str(tcfx_path.relative_to(project_root))
            except ValueError:
                tcfx_rel_path = str(tcfx_path)
            
            stack_data["tcfx_merge"] = {
                "status": "ERROR",
                "tcfx_file": tcfx_rel_path,
                "error": str(e)
            }
        return stack_data


def main():
    """CLI entry point for TCFX stackup merger."""
    parser = argparse.ArgumentParser(
        description="Merge Cadence Allegro/OrCAD TCFX Stackup Data into ThomsonLint Stackup JSON"
    )
    parser.add_argument("tcfx_file", help="Path to input .tcfx or .tcfx.txt file")
    parser.add_argument("stack_json", help="Path to stackup JSON file (e.g., *-thomson-export-stack.json)")
    parser.add_argument("--output", help="Optional output path (defaults to overwriting stack_json)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    
    args = parser.parse_args()
    
    tcfx_path = Path(args.tcfx_file)
    stack_path = Path(args.stack_json)
    out_path = Path(args.output) if args.output else stack_path
    
    # Validate inputs
    if not tcfx_path.exists():
        print(f"Error: Technology file not found: {tcfx_path}", file=sys.stderr)
        sys.exit(1)
        
    if not stack_path.exists():
        print(f"Error: Target stackup JSON not found: {stack_path}", file=sys.stderr)
        sys.exit(1)
        
    # Parse tech file
    try:
        tcfx_parser = TCFXParser(tcfx_path)
    except Exception as e:
        print(f"Error: Failed to parse XML tech file: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Read target JSON
    try:
        with open(stack_path, "r", encoding="utf-8") as f:
            stack_data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to read stackup JSON: {e}", file=sys.stderr)
        sys.exit(1)
        
    # Merge and serialize
    merged_data = merge_tcfx_into_stack(tcfx_parser, stack_data)
    
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, indent=2)
        
        if args.json:
            result = {
                "status": "SUCCESS",
                "tcfx_file": str(tcfx_path),
                "stack_json": str(stack_path),
                "output": str(out_path),
                "layers_parsed": len(tcfx_parser.raw_layers),
                "units": tcfx_parser.units
            }
            print(json.dumps(result, indent=2))
        else:
            print(f"Success: Merged physical stackup from {tcfx_path.name} into {out_path.name}")
            print(f"  Parsed {len(tcfx_parser.raw_layers)} layers from TCFX")
            print(f"  Units: {tcfx_parser.units}")
            
    except Exception as e:
        print(f"Error: Failed to write output JSON: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
