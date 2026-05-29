#!/usr/bin/env python3
"""parse_tcfx_stackup.py

Unified stackup parser for ThomsonLint. Supports:

  - Cadence Allegro/OrCAD Technology Files (.tcfx / .tcfx.txt)
  - Altium Designer Stackup files (.stackup)

Both parsers expose the same interface (raw_layers / units) and route through
the shared merge_tcfx_into_stack() function so that the downstream stackup JSON
is format-agnostic.

The parser resolves null material properties in the stackup JSON by extracting:
- Layer thicknesses (normalized to target units)
- Dielectric constants (Dk)
- Loss tangents (Df)
- Material names
- Copper weights
"""
from __future__ import annotations

import argparse
import json
import re
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


# ─────────────────────────────────────────────────────────────────────────────
# Altium Designer .stackup parser
# ─────────────────────────────────────────────────────────────────────────────

# LAYER_V8_<index><attribute>  — index is one or more digits, attribute begins
# with a letter or '$' (never a digit), so greedy \d+ unambiguously captures
# the index regardless of digit count (e.g. index 10 vs index 1).
_ALTIUM_LAYER_KEY_RE = re.compile(r'^LAYER_V8_(\d+)(.+)$')

# Altium DIELTYPE values
_ALTIUM_DIELTYPE_CORE = 1
_ALTIUM_DIELTYPE_PREPREG = 2
_ALTIUM_DIELTYPE_SOLDERMASK = 3


def _parse_altium_unit_value(val_str: str) -> tuple[float | None, str]:
    """Parse an Altium value string such as '1.4mil' or '46mil' or '0.4mil'.

    Returns (numeric_value, unit_string_upper) or (None, '') when unparseable.
    The unit string is normalised to uppercase (e.g. 'MIL', 'MM', 'OZ').
    """
    if not val_str:
        return None, ""
    m = re.match(r'^([+-]?[0-9]*\.?[0-9]+)\s*([a-zA-Z%]*)$', val_str.strip())
    if m:
        try:
            return float(m.group(1)), m.group(2).upper()
        except ValueError:
            pass
    return None, ""


class AltiumStackupParser:
    """Parser for Altium Designer .stackup files.

    The .stackup format is a single line of pipe-delimited ``KEY=VALUE`` pairs.
    This class exposes the same ``raw_layers`` / ``units`` interface as
    ``TCFXParser`` so that ``merge_tcfx_into_stack()`` can consume either
    format without modification.

    Layer type mapping (from Altium DIELTYPE):
      - ``COPTHICK`` present                    → ``Conductor``
      - ``DIELHEIGHT`` + ``DIELTYPE=1``         → ``Dielectric`` (core)
      - ``DIELHEIGHT`` + ``DIELTYPE=2``         → ``Dielectric`` (prepreg)
      - ``DIELHEIGHT`` + ``DIELTYPE=3``         → ``Mask`` (soldermask)
      - neither ``COPTHICK`` nor ``DIELHEIGHT`` → ``Surface`` (overlay/silkscreen)
    """

    def __init__(self, stackup_path: Path):
        self.stackup_path = stackup_path
        # utf-8-sig strips the BOM that Altium often prepends
        text = stackup_path.read_text(encoding="utf-8-sig", errors="ignore").strip()
        self._kv: dict[str, str] = self._parse_kv(text)
        self.units, self.raw_layers = self._extract_layers()

    @staticmethod
    def _parse_kv(text: str) -> dict[str, str]:
        """Split pipe-delimited ``KEY=VALUE`` tokens into a dict.

        Each ``|``-separated token is split on the *first* ``=`` only so that
        values containing ``=`` (e.g. base-64 fragments) are preserved intact.
        """
        kv: dict[str, str] = {}
        for token in text.split("|"):
            token = token.strip()
            if "=" in token:
                k, _, v = token.partition("=")
                kv[k.strip()] = v.strip()
        return kv

    def _extract_layers(self) -> tuple[str, list[dict[str, Any]]]:
        """Group KV pairs by layer index and produce the standard raw_layers list."""
        # Bucket attributes by integer layer index
        layers_raw: dict[int, dict[str, str]] = {}
        for key, val in self._kv.items():
            m = _ALTIUM_LAYER_KEY_RE.match(key)
            if not m:
                continue
            idx = int(m.group(1))
            attr = m.group(2)
            # Skip substack-context keys that embed a UUID in braces — they
            # duplicate NAME/context info and are not needed for physical data.
            if "{" in attr:
                continue
            layers_raw.setdefault(idx, {})[attr] = val

        if not layers_raw:
            return "MIL", []

        # Detect the source unit from the first thickness value found
        detected_unit = "MIL"
        for attrs in layers_raw.values():
            for uk in ("COPTHICK", "DIELHEIGHT", "$LSM$Thickness"):
                if uk in attrs:
                    _, u = _parse_altium_unit_value(attrs[uk])
                    if u:
                        detected_unit = u
                    break
            else:
                continue
            break

        raw_layers: list[dict[str, Any]] = []
        for idx in sorted(layers_raw.keys()):
            attrs = layers_raw[idx]
            name = attrs.get("NAME")

            # Determine layer type from available keys
            has_copper = "COPTHICK" in attrs
            has_diel = "DIELHEIGHT" in attrs
            dieltype_str = attrs.get("DIELTYPE", "")
            dieltype = int(dieltype_str) if dieltype_str.isdigit() else None

            if has_copper:
                layer_type = "Conductor"
                thickness_str = attrs.get("COPTHICK") or attrs.get("$LSM$Thickness")
            elif has_diel:
                layer_type = "Mask" if dieltype == _ALTIUM_DIELTYPE_SOLDERMASK else "Dielectric"
                thickness_str = attrs.get("DIELHEIGHT") or attrs.get("$LSM$Thickness")
            else:
                layer_type = "Surface"
                thickness_str = None

            thickness, _ = _parse_altium_unit_value(thickness_str) if thickness_str else (None, "")

            # Dielectric constant — prefer the direct key, fall back to $LSM$
            dk = _to_float(attrs.get("DIELCONST") or attrs.get("$LSM$DielectricConstant"))

            # Loss tangent (only the $LSM$ key carries this)
            df = _to_float(attrs.get("$LSM$LossTangent"))

            # Material name
            material = attrs.get("DIELMATERIAL") or attrs.get("$LSM$Material") or None

            # Flag fields that are absent but expected for this layer type
            unresolved: list[str] = []
            if thickness is None and layer_type != "Surface":
                unresolved.append("thickness")
            if material is None and layer_type in ("Dielectric", "Conductor", "Mask"):
                unresolved.append("material")
            if dk is None and layer_type in ("Dielectric", "Mask"):
                unresolved.append("dielectric_constant")

            entry: dict[str, Any] = {
                "name": name,
                "type": layer_type,
                "material": material,
                "thickness": thickness,
                "dielectric_constant": dk,
                "loss_tangent": df,
                "function": None,  # resolved downstream by merge_tcfx_into_stack
            }
            if unresolved:
                entry["unresolved_fields"] = unresolved

            raw_layers.append(entry)

        return detected_unit, raw_layers


def _load_stackup_parser(stackup_path: Path) -> TCFXParser | AltiumStackupParser:
    """Route a stackup file to the appropriate parser based on extension.

    Supported extensions:
      - ``.tcfx``     / ``.tcfx.txt`` → ``TCFXParser``
      - ``.stackup``                  → ``AltiumStackupParser``

    Raises ``ValueError`` for unrecognised extensions.
    """
    name_lower = stackup_path.name.lower()
    if name_lower.endswith(".tcfx") or name_lower.endswith(".tcfx.txt"):
        return TCFXParser(stackup_path)
    if name_lower.endswith(".stackup"):
        return AltiumStackupParser(stackup_path)
    raise ValueError(
        f"Unsupported stackup file extension: {stackup_path.suffix!r}. "
        "Expected .tcfx, .tcfx.txt, or .stackup."
    )


def merge_tcfx_into_stack(tcfx_parser: TCFXParser | AltiumStackupParser, stack_data: dict[str, Any], *, source_label: str | None = None) -> dict[str, Any]:
    """Merge stackup parser output into the standard ThomsonLint stackup JSON.

    Accepts both ``TCFXParser`` and ``AltiumStackupParser`` instances — they
    share the same ``raw_layers`` / ``units`` interface.

    Args:
        tcfx_parser:  Parsed stackup data (TCFX or Altium).
        stack_data:   Target stackup JSON dictionary to enrich.
        source_label: Optional override for ``stackup_data_quality.source``.
                      Defaults to ``"ipc2581_merged_with_allegro_tcfx"`` for
                      ``TCFXParser`` and ``"ipc2581_merged_with_altium_stackup"``
                      for ``AltiumStackupParser``.

    Returns:
        Updated stackup dictionary with complete physical stackup.
    """
    if source_label is None:
        source_label = (
            "ipc2581_merged_with_altium_stackup"
            if isinstance(tcfx_parser, AltiumStackupParser)
            else "ipc2581_merged_with_allegro_tcfx"
        )
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
    quality["source"] = source_label
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
    """Automatically search for and merge a stackup file if one is found.

    Searches the project root and common sub-directories for ``.tcfx``,
    ``.tcfx.txt``, and ``.stackup`` files.  ``.tcfx`` / ``.tcfx.txt`` take
    precedence over ``.stackup`` so that OrCAD projects are unaffected.

    Args:
        project_root: Project root directory.
        stack_data:   Stackup JSON dictionary.

    Returns:
        Updated stackup dictionary (with or without merge).
    """
    search_dirs = [project_root]
    for sub in ("input", "pre_conversion"):
        d = project_root / sub
        if d.exists():
            search_dirs.append(d)

    tcfx_candidates: list[Path] = []
    altium_candidates: list[Path] = []
    for d in search_dirs:
        tcfx_candidates.extend(d.glob("*.tcfx"))
        tcfx_candidates.extend(d.glob("*.tcfx.txt"))
        altium_candidates.extend(d.glob("*.stackup"))

    # Prefer TCFX over Altium when both exist in the same project
    if tcfx_candidates:
        chosen_path = tcfx_candidates[0]
        merge_key = "tcfx_merge"
    elif altium_candidates:
        chosen_path = altium_candidates[0]
        merge_key = "altium_stackup_merge"
    else:
        return stack_data

    try:
        stackup_parser = _load_stackup_parser(chosen_path)
        merged_data = merge_tcfx_into_stack(stackup_parser, stack_data)

        if merge_key not in merged_data:
            try:
                rel_path = str(chosen_path.relative_to(project_root))
            except ValueError:
                rel_path = str(chosen_path)

            merged_data[merge_key] = {
                "status": "SUCCESS",
                "source_file": rel_path,
                "layers_parsed": len(stackup_parser.raw_layers),
                "layers_updated": sum(
                    1 for layer in merged_data.get("layer_stack", [])
                    if layer.get("thickness") is not None
                ),
            }

        return merged_data

    except Exception as e:
        if merge_key not in stack_data:
            try:
                rel_path = str(chosen_path.relative_to(project_root))
            except ValueError:
                rel_path = str(chosen_path)

            stack_data[merge_key] = {
                "status": "ERROR",
                "source_file": rel_path,
                "error": str(e),
            }
        return stack_data


def main():
    """CLI entry point for stackup merger (supports .tcfx and .stackup)."""
    parser = argparse.ArgumentParser(
        description=(
            "Merge physical stackup data into a ThomsonLint stackup JSON. "
            "Accepts Cadence Allegro/OrCAD .tcfx files and Altium .stackup files."
        )
    )
    parser.add_argument(
        "stackup_file",
        help="Path to input stackup file (.tcfx, .tcfx.txt, or .stackup)",
    )
    parser.add_argument(
        "stack_json",
        help="Path to target stackup JSON (e.g., *-thomson-export-stack.json)",
    )
    parser.add_argument(
        "--output",
        help="Optional output path (defaults to overwriting stack_json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    stackup_path = Path(args.stackup_file)
    stack_path = Path(args.stack_json)
    out_path = Path(args.output) if args.output else stack_path

    if not stackup_path.exists():
        print(f"Error: Stackup file not found: {stackup_path}", file=sys.stderr)
        sys.exit(1)

    if not stack_path.exists():
        print(f"Error: Target stackup JSON not found: {stack_path}", file=sys.stderr)
        sys.exit(1)

    try:
        stackup_parser = _load_stackup_parser(stackup_path)
    except (ValueError, Exception) as e:
        print(f"Error: Failed to parse stackup file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(stack_path, encoding="utf-8") as f:
            stack_data = json.load(f)
    except Exception as e:
        print(f"Error: Failed to read stackup JSON: {e}", file=sys.stderr)
        sys.exit(1)

    merged_data = merge_tcfx_into_stack(stackup_parser, stack_data)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, indent=2)

        if args.json:
            result = {
                "status": "SUCCESS",
                "source_file": str(stackup_path),
                "source_format": (
                    "altium_stackup"
                    if isinstance(stackup_parser, AltiumStackupParser)
                    else "allegro_tcfx"
                ),
                "stack_json": str(stack_path),
                "output": str(out_path),
                "layers_parsed": len(stackup_parser.raw_layers),
                "units": stackup_parser.units,
            }
            print(json.dumps(result, indent=2))
        else:
            fmt = (
                "Altium .stackup"
                if isinstance(stackup_parser, AltiumStackupParser)
                else "Cadence .tcfx"
            )
            print(
                f"Success: Merged physical stackup from {stackup_path.name} "
                f"({fmt}) into {out_path.name}"
            )
            print(f"  Parsed {len(stackup_parser.raw_layers)} layers")
            print(f"  Units: {stackup_parser.units}")

    except Exception as e:
        print(f"Error: Failed to write output JSON: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
