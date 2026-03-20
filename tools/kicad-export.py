#!/usr/bin/env python3
"""Export KiCad 9 schematic and board data for ThomsonLint AI design review.

Produces JSON files equivalent to the Fusion Electronics ULP export, but by
parsing KiCad S-expression files directly. No KiCad installation required.
Only uses Python standard library.

Usage:
    python tools/kicad-export.py <path-to-.kicad_pro> [--output <dir>]
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

VERSION = "1.0"

# ============================================================================
# S-Expression Parser
# ============================================================================

def tokenize(text):
    """Tokenize KiCad S-expression text into a flat list."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\n\r':
            i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == '"':
            # Quoted string
            j = i + 1
            parts = []
            while j < n:
                ch = text[j]
                if ch == '\\' and j + 1 < n:
                    parts.append(text[j + 1])
                    j += 2
                elif ch == '"':
                    break
                else:
                    parts.append(ch)
                    j += 1
            tokens.append(''.join(parts))
            i = j + 1
        else:
            # Unquoted atom
            j = i
            while j < n and text[j] not in ' \t\n\r()':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse_sexpr(text):
    """Parse KiCad S-expression text into nested Python lists."""
    tokens = tokenize(text)
    idx = [0]

    def _parse():
        if idx[0] >= len(tokens):
            return None
        tok = tokens[idx[0]]
        if tok == '(':
            idx[0] += 1
            lst = []
            while idx[0] < len(tokens) and tokens[idx[0]] != ')':
                child = _parse()
                if child is not None:
                    lst.append(child)
            idx[0] += 1  # consume ')'
            return lst
        else:
            idx[0] += 1
            return tok

    results = []
    while idx[0] < len(tokens):
        r = _parse()
        if r is not None:
            results.append(r)
    return results[0] if len(results) == 1 else results


def find_all(node, tag):
    """Find all child lists whose first element equals tag."""
    if not isinstance(node, list):
        return []
    return [child for child in node if isinstance(child, list) and len(child) > 0 and child[0] == tag]


def find_one(node, tag):
    """Find the first child list whose first element equals tag."""
    if not isinstance(node, list):
        return None
    for child in node:
        if isinstance(child, list) and len(child) > 0 and child[0] == tag:
            return child
    return None


def get_property(node, name):
    """Get value of a (property "name" "value" ...) child."""
    for child in node:
        if isinstance(child, list) and len(child) >= 3 and child[0] == 'property' and child[1] == name:
            return child[2]
    return ""


def get_at(node):
    """Extract (at x y [rotation]) as (x, y, rotation) floats."""
    at = find_one(node, 'at')
    if at is None:
        return (0.0, 0.0, 0.0)
    x = _to_float(at[1]) if len(at) > 1 else 0.0
    y = _to_float(at[2]) if len(at) > 2 else 0.0
    rot = _to_float(at[3]) if len(at) > 3 else 0.0
    return (x, y, rot)


def get_start(node):
    """Extract (start x y) as (x, y) floats."""
    s = find_one(node, 'start')
    if s and len(s) >= 3:
        return (_to_float(s[1]), _to_float(s[2]))
    return None


def get_end(node):
    """Extract (end x y) as (x, y) floats."""
    e = find_one(node, 'end')
    if e and len(e) >= 3:
        return (_to_float(e[1]), _to_float(e[2]))
    return None


def _to_float(val):
    """Convert a string or numeric value to float safely."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _to_int(val):
    """Convert a string or numeric value to int safely."""
    try:
        return int(val)
    except (ValueError, TypeError):
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0


def _get_scalar(node, tag):
    """Get first scalar value after tag in a child list: (tag value) -> value."""
    child = find_one(node, tag)
    if child and len(child) >= 2:
        return child[1]
    return None


# ============================================================================
# Signal Classification Helpers (ported from fusion-electronics-export.ulp)
# ============================================================================

def is_power_net(name):
    upper = name.upper()
    for pat in ('VCC', 'VDD', 'VBUS', 'VIN', 'VOUT', 'VBAT', 'VSYS',
                '+3V', '+5V', '+12V', '+24V', '3V3', '5V0', '1V8', '1V2',
                '2V5', 'PWR'):
        if pat in upper:
            return True
    return False


def is_ground_net(name):
    upper = name.upper()
    if upper in ('GND', 'AGND', 'DGND', 'PGND', 'SGND'):
        return True
    if 'VSS' in upper or 'GND' in upper:
        return True
    return False


def is_clock_net(name):
    upper = name.upper()
    for pat in ('CLK', 'XTAL', 'SCK', 'SCLK', 'MCLK', 'BCLK', 'LRCK', 'OSC'):
        if pat in upper:
            return True
    return False


def is_diff_pair_member(name):
    """Returns 1 if positive, -1 if negative, 0 if not differential."""
    upper = name.upper()
    n = len(upper)
    if n >= 2:
        last2 = upper[-2:]
        if last2 == '_P': return 1
        if last2 == '_N': return -1
        if last2 == 'DP': return 1
        if last2 == 'DN': return -1
        if last2 == 'D+': return 1
        if last2 == 'D-': return -1
    if n >= 3:
        last3 = upper[-3:]
        if last3 == '_DP': return 1
        if last3 == '_DN': return -1
    return 0


def find_diff_partner(name):
    n = len(name)
    if n < 2:
        return ""
    last2 = name[-2:]
    ul2 = last2.upper()
    base = name[:-2]
    pairs = {'_P': '_N', '_N': '_P', 'DP': 'DN', 'DN': 'DP', 'D+': 'D-', 'D-': 'D+'}
    if ul2 in pairs:
        # Preserve original case pattern
        return base + pairs[ul2]
    return ""


def guess_voltage(name):
    upper = name.upper()
    if '3V3' in upper or '3.3' in upper or '+3V3' in upper: return "3.3V"
    if '5V0' in upper or '+5V' in upper or '5V' in upper: return "5V"
    if '1V8' in upper or '1.8' in upper: return "1.8V"
    if '1V2' in upper or '1.2' in upper: return "1.2V"
    if '2V5' in upper or '2.5' in upper: return "2.5V"
    if '12V' in upper: return "12V"
    if '24V' in upper: return "24V"
    if 'VBUS' in upper: return "5V"
    if 'VBAT' in upper: return "3.7V"
    return ""


def classify_component(ref, desc=""):
    if not ref:
        return "unknown"
    # Multi-char prefixes first
    if ref[:2] == 'FB': return "ferrite_bead"
    if ref[:2] == 'TP': return "test_point"
    if ref[:2] == 'SW': return "switch"
    if ref[:2] == 'BT': return "battery"
    if ref[:2] == 'MH': return "mounting_hole"
    first = ref[0]
    if first == 'U': return "IC"
    if first == 'C': return "capacitor"
    if first == 'R': return "resistor"
    if first == 'L': return "inductor"
    if first == 'D':
        upper = desc.upper() if desc else ""
        if 'LED' in upper: return "LED"
        if 'TVS' in upper or 'ESD' in upper: return "TVS"
        if 'ZENER' in upper: return "zener"
        return "diode"
    if first == 'Q': return "transistor"
    if first == 'J': return "connector"
    if first in ('X', 'Y'): return "crystal"
    if first == 'F': return "fuse"
    if first == 'T': return "transformer"
    if first == 'K': return "relay"
    return "other"


def guess_diff_interface(name):
    upper = name.upper()
    for pat, iface in (('USB', 'USB'), ('ETH', 'Ethernet'), ('MDIO', 'Ethernet'),
                       ('HDMI', 'HDMI'), ('LVDS', 'LVDS'), ('CAN', 'CAN'),
                       ('RS485', 'RS-485'), ('RS-485', 'RS-485'),
                       ('PCIE', 'PCIe'), ('PCI', 'PCIe'),
                       ('SATA', 'SATA'), ('MIPI', 'MIPI')):
        if pat in upper:
            return iface
    return "unknown"


def needs_trace_detail(name):
    if is_clock_net(name): return True
    if is_diff_pair_member(name) != 0: return True
    upper = name.upper()
    for pat in ('USB', 'ETH', 'HDMI', 'PCIE', 'SATA', 'MIPI', 'LVDS'):
        if pat in upper:
            return True
    return False


# KiCad pin electrical type string mapping
PIN_DIR_MAP = {
    'input': 'IN', 'output': 'OUT', 'bidirectional': 'IO',
    'tri_state': 'HIZ', 'passive': 'PAS', 'free': 'PAS',
    'unspecified': 'UNK', 'power_in': 'PWR', 'power_out': 'SUP',
    'open_collector': 'OC', 'open_emitter': 'OC', 'no_connect': 'NC',
}


# ============================================================================
# Project File Reader
# ============================================================================

def read_kicad_project(pro_path):
    """Read .kicad_pro JSON file. Returns (net_class_map, net_classes, project_meta)."""
    with open(pro_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    net_settings = data.get('net_settings', {})

    # net class definitions
    net_classes = {}
    for cls in net_settings.get('classes', []):
        net_classes[cls['name']] = cls

    # net -> class name mapping
    net_class_map = {}
    for net_name, class_list in (net_settings.get('netclass_assignments') or {}).items():
        if class_list:
            net_class_map[net_name] = class_list[0]

    # project metadata from text_variables
    meta = {}
    for key in ('text_variables',):
        if key in data:
            meta.update(data[key])

    return net_class_map, net_classes, meta


# ============================================================================
# Schematic Parser
# ============================================================================

def parse_schematic(sch_path, project_dir=None, project_name=""):
    """Parse KiCad schematic and all sub-sheets. Returns (components, lib_pin_types, sheet_count)."""
    components = []
    lib_pin_types = {}  # lib_id -> {pin_number: direction_string}
    visited_files = set()
    sheet_uuids = []  # All sheet UUIDs for counting

    def _parse_sheet(path, parent_uuid_path):
        norm = os.path.normcase(os.path.abspath(path))
        is_first_visit = norm not in visited_files
        visited_files.add(norm)

        if not os.path.isfile(path):
            print(f"  Warning: schematic file not found: {path}", file=sys.stderr)
            return

        print(f"  Parsing: {os.path.basename(path)}", file=sys.stderr)
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        sexpr = parse_sexpr(text)
        if not isinstance(sexpr, list) or not sexpr:
            return

        # Extract lib_symbols pin types (only on first visit of this file)
        if is_first_visit:
            lib_syms = find_one(sexpr, 'lib_symbols')
            if lib_syms:
                for sym in find_all(lib_syms, 'symbol'):
                    if len(sym) < 2:
                        continue
                    lib_id = sym[1]
                    if lib_id in lib_pin_types:
                        continue
                    pin_map = {}
                    _collect_pins(sym, pin_map)
                    if pin_map:
                        lib_pin_types[lib_id] = pin_map

        # Extract symbols (components) -- top-level (symbol ...) nodes, not inside lib_symbols
        for node in sexpr:
            if not isinstance(node, list) or not node or node[0] != 'symbol':
                continue
            lib_id_node = find_one(node, 'lib_id')
            if not lib_id_node or len(lib_id_node) < 2:
                continue
            lib_id = lib_id_node[1]

            on_board = _get_scalar(node, 'on_board')
            dnp = _get_scalar(node, 'dnp')

            # Get instances for reference designator resolution
            instances_node = find_one(node, 'instances')
            if instances_node:
                for proj in find_all(instances_node, 'project'):
                    if len(proj) < 2:
                        continue
                    pname = proj[1]
                    if project_name and pname != project_name:
                        continue
                    for path_node in find_all(proj, 'path'):
                        if len(path_node) < 2:
                            continue
                        ref_node = find_one(path_node, 'reference')
                        if not ref_node or len(ref_node) < 2:
                            continue
                        ref = ref_node[1]

                        # Skip power symbols
                        if ref.startswith('#'):
                            continue
                        if on_board == 'no':
                            continue

                        # Avoid duplicate refs
                        unit_node = find_one(path_node, 'unit')
                        unit = _to_int(unit_node[1]) if unit_node and len(unit_node) > 1 else 1
                        if unit > 1:
                            continue  # Only emit unit 1 for multi-unit symbols

                        value = get_property(node, 'Value')
                        footprint = get_property(node, 'Footprint')
                        description = get_property(node, 'Description')
                        populate = True
                        if dnp == 'yes':
                            populate = False

                        # Gather custom attributes
                        attrs = {}
                        standard_props = {'Reference', 'Value', 'Footprint', 'Datasheet',
                                          'Description', 'ki_keywords', 'ki_fp_filters'}
                        for child in node:
                            if isinstance(child, list) and len(child) >= 3 and child[0] == 'property':
                                pname_attr = child[1]
                                if pname_attr not in standard_props and not pname_attr.startswith('ki_'):
                                    pval = child[2]
                                    if pval:
                                        attrs[pname_attr] = pval

                        comp_type = classify_component(ref, description)
                        # Extract package from footprint or Package property
                        package = get_property(node, 'Package') or ""
                        if not package and footprint:
                            # e.g. "w_Passive:C_0603" -> "C_0603"
                            package = footprint.split(':')[-1] if ':' in footprint else footprint

                        components.append({
                            'ref': ref,
                            'value': value,
                            'package': package,
                            'device': lib_id.split(':')[-1] if ':' in lib_id else lib_id,
                            'description': description,
                            'populate': populate,
                            'type': comp_type,
                            'attributes': attrs,
                        })

        # Discover and recurse into sub-sheets
        for sheet_node in find_all(sexpr, 'sheet'):
            sheet_file = get_property(sheet_node, 'Sheetfile')
            sheet_uuid_node = find_one(sheet_node, 'uuid')
            sheet_uuid = sheet_uuid_node[1] if sheet_uuid_node and len(sheet_uuid_node) > 1 else ""
            sheet_uuids.append(sheet_uuid)

            if sheet_file:
                sheet_path = os.path.join(os.path.dirname(path), sheet_file)
                new_path = parent_uuid_path + "/" + sheet_uuid
                _parse_sheet(sheet_path, new_path)

    # Get root UUID
    with open(sch_path, 'r', encoding='utf-8') as f:
        root_text = f.read()
    root_sexpr = parse_sexpr(root_text)
    root_uuid_node = find_one(root_sexpr, 'uuid') if isinstance(root_sexpr, list) else None
    root_uuid = root_uuid_node[1] if root_uuid_node and len(root_uuid_node) > 1 else ""

    _parse_sheet(sch_path, "/" + root_uuid)

    # Deduplicate by ref (multi-unit symbols may generate duplicates)
    seen_refs = set()
    unique_components = []
    for comp in components:
        if comp['ref'] not in seen_refs:
            seen_refs.add(comp['ref'])
            unique_components.append(comp)

    # Count sheets: root + sub-sheets
    sheet_count = 1 + len(sheet_uuids)

    return unique_components, lib_pin_types, sheet_count


def _collect_pins(sym_node, pin_map):
    """Recursively collect pin electrical types from a lib_symbol definition."""
    for child in sym_node:
        if not isinstance(child, list) or not child:
            continue
        if child[0] == 'pin' and len(child) >= 3:
            # (pin passive line (at ...) (length ...) (name "~" ...) (number "1" ...))
            elec_type = child[1]  # e.g. "passive", "input", "output", "power_in"
            num_node = find_one(child, 'number')
            if num_node and len(num_node) >= 2:
                pin_num = num_node[1]
                pin_map[pin_num] = PIN_DIR_MAP.get(elec_type, 'UNK')
        elif child[0] == 'symbol':
            # Sub-symbol (unit)
            _collect_pins(child, pin_map)


# ============================================================================
# Board Parser
# ============================================================================

def parse_board(pcb_path):
    """Parse KiCad PCB file. Returns dict with all board data."""
    print(f"  Parsing: {os.path.basename(pcb_path)}", file=sys.stderr)
    with open(pcb_path, 'r', encoding='utf-8') as f:
        text = f.read()
    sexpr = parse_sexpr(text)
    if not isinstance(sexpr, list) or not sexpr:
        return None

    result = {
        'layers': _extract_layers(sexpr),
        'nets': _extract_nets(sexpr),
        'footprints': _extract_footprints(sexpr),
        'segments': _extract_segments(sexpr),
        'vias': _extract_vias(sexpr),
        'zones': _extract_zones(sexpr),
        'board_outline': _extract_board_outline(sexpr),
        'properties': _extract_board_properties(sexpr),
    }
    return result


def _extract_layers(sexpr):
    """Extract copper layers from (layers ...) block."""
    layers_node = find_one(sexpr, 'layers')
    if not layers_node:
        return []
    copper_layers = []
    for child in layers_node:
        if isinstance(child, list) and len(child) >= 3:
            layer_id = _to_int(child[0])
            layer_name = child[1]
            layer_type = child[2]
            if layer_type in ('signal', 'power', 'mixed'):
                copper_layers.append({'number': layer_id, 'name': layer_name, 'type': layer_type})
    return copper_layers


def _extract_nets(sexpr):
    """Extract net definitions: (net N "name")."""
    nets = {}
    for child in sexpr:
        if isinstance(child, list) and len(child) >= 3 and child[0] == 'net':
            net_id = _to_int(child[1])
            net_name = child[2]
            nets[net_id] = net_name
    return nets


def _extract_footprints(sexpr):
    """Extract footprint data including pad positions."""
    footprints = []
    for node in sexpr:
        if not isinstance(node, list) or not node or node[0] != 'footprint':
            continue
        fp_lib = node[1] if len(node) > 1 else ""
        layer_node = find_one(node, 'layer')
        fp_layer = layer_node[1] if layer_node and len(layer_node) > 1 else "F.Cu"
        x, y, rot = get_at(node)

        ref = get_property(node, 'Reference')
        value = get_property(node, 'Value')
        desc = get_property(node, 'Description')

        # Determine side
        side = "bottom" if "B.Cu" in fp_layer else "top"

        # Extract pads
        pads = []
        for pad_node in find_all(node, 'pad'):
            if len(pad_node) < 4:
                continue
            pad_name = pad_node[1]
            pad_type = pad_node[2]  # smd, thru_hole, np_thru_hole, connect

            pad_x, pad_y, _ = get_at(pad_node)

            # Get net assignment
            pad_net_node = find_one(pad_node, 'net')
            pad_net_id = 0
            pad_net_name = ""
            if pad_net_node and len(pad_net_node) >= 3:
                pad_net_id = _to_int(pad_net_node[1])
                pad_net_name = pad_net_node[2]

            # Get drill size for THT pads
            drill = 0.0
            drill_node = find_one(pad_node, 'drill')
            if drill_node and len(drill_node) >= 2:
                drill = _to_float(drill_node[1])

            # Compute absolute pad position
            abs_x, abs_y = _pad_absolute_position(x, y, rot, fp_layer, pad_x, pad_y)

            pads.append({
                'name': pad_name,
                'type': pad_type,
                'x_mm': round(abs_x, 4),
                'y_mm': round(abs_y, 4),
                'net_id': pad_net_id,
                'net_name': pad_net_name,
                'drill': drill,
            })

        # Package name from lib footprint
        package = fp_lib.split(':')[-1] if ':' in fp_lib else fp_lib

        footprints.append({
            'ref': ref,
            'package': package,
            'value': value,
            'description': desc,
            'x_mm': round(x, 4),
            'y_mm': round(y, 4),
            'rotation': round(rot, 1),
            'side': side,
            'pads': pads,
        })
    return footprints


def _pad_absolute_position(fp_x, fp_y, fp_rot, fp_layer, pad_rx, pad_ry):
    """Compute absolute board position of a pad given footprint transform."""
    rx, ry = pad_rx, pad_ry
    if 'B.Cu' in fp_layer:
        rx = -rx  # mirror X for back-side footprints
    rad = math.radians(fp_rot)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    abs_x = fp_x + rx * cos_r - ry * sin_r
    abs_y = fp_y + rx * sin_r + ry * cos_r
    return abs_x, abs_y


def _extract_segments(sexpr):
    """Extract trace segments."""
    segments = []
    for node in sexpr:
        if not isinstance(node, list) or not node or node[0] != 'segment':
            continue
        start = get_start(node)
        end = get_end(node)
        if not start or not end:
            continue
        width_node = find_one(node, 'width')
        width = _to_float(width_node[1]) if width_node and len(width_node) > 1 else 0.25
        layer_node = find_one(node, 'layer')
        layer = layer_node[1] if layer_node and len(layer_node) > 1 else ""
        net_node = find_one(node, 'net')
        net_id = _to_int(net_node[1]) if net_node and len(net_node) > 1 else 0

        length = math.sqrt((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2)

        segments.append({
            'start': start,
            'end': end,
            'width': width,
            'layer': layer,
            'net_id': net_id,
            'length': length,
        })
    return segments


def _extract_vias(sexpr):
    """Extract vias."""
    vias = []
    for node in sexpr:
        if not isinstance(node, list) or not node or node[0] != 'via':
            continue
        x, y, _ = get_at(node)
        size_node = find_one(node, 'size')
        size = _to_float(size_node[1]) if size_node and len(size_node) > 1 else 0.5
        drill_node = find_one(node, 'drill')
        drill = _to_float(drill_node[1]) if drill_node and len(drill_node) > 1 else 0.25
        net_node = find_one(node, 'net')
        net_id = _to_int(net_node[1]) if net_node and len(net_node) > 1 else 0
        layers_node = find_one(node, 'layers')
        layers = [layers_node[i] for i in range(1, len(layers_node))] if layers_node else []

        vias.append({
            'x_mm': round(x, 4),
            'y_mm': round(y, 4),
            'size': size,
            'drill': drill,
            'net_id': net_id,
            'layers': layers,
        })
    return vias


def _extract_zones(sexpr):
    """Extract copper zones/fills."""
    zones = []
    for node in sexpr:
        if not isinstance(node, list) or not node or node[0] != 'zone':
            continue
        net_node = find_one(node, 'net')
        net_id = _to_int(net_node[1]) if net_node and len(net_node) > 1 else 0
        net_name_node = find_one(node, 'net_name')
        net_name = net_name_node[1] if net_name_node and len(net_name_node) > 1 else ""

        # Layer(s) - can be single (layer "X") or multiple (layers "X" "Y" ...)
        layer_node = find_one(node, 'layer')
        layers_node = find_one(node, 'layers')
        zone_layers = []
        if layers_node:
            zone_layers = [layers_node[i] for i in range(1, len(layers_node))]
        elif layer_node and len(layer_node) > 1:
            zone_layers = [layer_node[1]]

        zones.append({
            'net_id': net_id,
            'net_name': net_name,
            'layers': zone_layers,
        })
    return zones


def _extract_board_outline(sexpr):
    """Extract board outline from Edge.Cuts graphic elements."""
    vertices = []

    for node in sexpr:
        if not isinstance(node, list) or not node:
            continue
        tag = node[0]
        layer_node = find_one(node, 'layer')
        layer = layer_node[1] if layer_node and len(layer_node) > 1 else ""
        if layer != 'Edge.Cuts':
            continue

        if tag == 'gr_rect':
            start = get_start(node)
            end = get_end(node)
            if start and end:
                vertices.extend([start, end])
        elif tag == 'gr_line':
            start = get_start(node)
            end = get_end(node)
            if start:
                vertices.append(start)
            if end:
                vertices.append(end)
        elif tag == 'gr_circle':
            center = find_one(node, 'center')
            end_pt = get_end(node)
            if center and len(center) >= 3 and end_pt:
                cx, cy = _to_float(center[1]), _to_float(center[2])
                ex, ey = end_pt
                r = math.sqrt((ex - cx) ** 2 + (ey - cy) ** 2)
                vertices.extend([(cx - r, cy - r), (cx + r, cy + r)])
        elif tag == 'gr_arc':
            start = get_start(node)
            mid = find_one(node, 'mid')
            end_pt = get_end(node)
            if start:
                vertices.append(start)
            if mid and len(mid) >= 3:
                vertices.append((_to_float(mid[1]), _to_float(mid[2])))
            if end_pt:
                vertices.append(end_pt)

    if not vertices:
        return None

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return {
        'x1': min(xs), 'y1': min(ys),
        'x2': max(xs), 'y2': max(ys),
        'width_mm': round(max(xs) - min(xs), 4),
        'height_mm': round(max(ys) - min(ys), 4),
    }


def _extract_board_properties(sexpr):
    """Extract board-level properties (ProjectTitle, etc.)."""
    props = {}
    for node in sexpr:
        if isinstance(node, list) and len(node) >= 3 and node[0] == 'property':
            props[node[1]] = node[2]
    return props


# ============================================================================
# Analysis Computations
# ============================================================================

def compute_decoupling_proximity(footprints):
    """Compute pad-to-pad distances from IC power pins to nearest decoupling cap."""
    results = []
    # Build net -> pads lookup from footprint data
    net_ic_pads = defaultdict(list)   # net_name -> [(ref, pad_name, x, y)]
    net_cap_pads = defaultdict(list)

    for fp in footprints:
        ref = fp['ref']
        for pad in fp['pads']:
            net_name = pad['net_name']
            if not net_name or not is_power_net(net_name) or is_ground_net(net_name):
                continue
            if ref and ref[0] == 'U':
                net_ic_pads[net_name].append((ref, pad['name'], pad['x_mm'], pad['y_mm']))
            elif ref and ref[0] == 'C':
                net_cap_pads[net_name].append((ref, pad['name'], pad['x_mm'], pad['y_mm']))

    for net_name in net_ic_pads:
        cap_pads = net_cap_pads.get(net_name, [])
        if not cap_pads:
            continue
        for ic_ref, ic_pin, ic_x, ic_y in net_ic_pads[net_name]:
            best_dist = 99999.0
            best_cap = None
            for cap_ref, cap_pin, cap_x, cap_y in cap_pads:
                d = math.sqrt((ic_x - cap_x) ** 2 + (ic_y - cap_y) ** 2)
                if d < best_dist:
                    best_dist = d
                    best_cap = (cap_ref, cap_pin, cap_x, cap_y)
            if best_cap:
                results.append({
                    'ic_ref': ic_ref, 'ic_pin': ic_pin,
                    'ic_pin_x_mm': round(ic_x, 4), 'ic_pin_y_mm': round(ic_y, 4),
                    'cap_ref': best_cap[0], 'cap_pin': best_cap[1],
                    'cap_pin_x_mm': round(best_cap[2], 4), 'cap_pin_y_mm': round(best_cap[3], 4),
                    'distance_mm': round(best_dist, 2),
                    'net': net_name,
                })
    return results


def compute_edge_distances(footprints, outline):
    """Find components within 3mm of board edge."""
    if not outline:
        return []
    results = []
    x1, y1, x2, y2 = outline['x1'], outline['y1'], outline['x2'], outline['y2']
    for fp in footprints:
        ex, ey = fp['x_mm'], fp['y_mm']
        d_left = ex - x1
        d_right = x2 - ex
        d_top = ey - y1
        d_bottom = y2 - ey
        min_dist = min(d_left, d_right, d_top, d_bottom)
        if min_dist < 3.0:
            results.append({'ref': fp['ref'], 'min_distance_mm': round(min_dist, 4)})
    return results


def compute_ground_plane_layers(zones):
    """Identify layers with ground zone fills."""
    layers = []
    seen = set()
    for zone in zones:
        if is_ground_net(zone['net_name']):
            for layer in zone['layers']:
                if layer not in seen:
                    seen.add(layer)
                    layers.append(layer)
    return layers


def compute_signal_stats(segments, vias, nets):
    """Compute per-signal trace statistics."""
    # Group by net
    seg_by_net = defaultdict(list)
    for seg in segments:
        seg_by_net[seg['net_id']].append(seg)

    via_by_net = defaultdict(int)
    for via in vias:
        via_by_net[via['net_id']] += 1

    signals = []
    for net_id, net_name in sorted(nets.items()):
        if net_id == 0 or not net_name:
            continue  # Skip unconnected net

        segs = seg_by_net.get(net_id, [])
        total_length = sum(s['length'] for s in segs)
        widths = [s['width'] for s in segs]
        min_w = min(widths) if widths else 0.0
        max_w = max(widths) if widths else 0.0
        via_count = via_by_net.get(net_id, 0)

        sig = {
            'name': net_name,
            'is_power': is_power_net(net_name),
            'is_ground': is_ground_net(net_name),
            'is_clock': is_clock_net(net_name),
            'trace_length_mm': round(total_length, 4),
            'min_width_mm': round(min_w, 4),
            'max_width_mm': round(max_w, 4),
            'via_count': via_count,
            'segment_count': len(segs),
        }

        if needs_trace_detail(net_name) and segs:
            sig['trace_segments'] = [
                {
                    'layer': s['layer'],
                    'x1_mm': round(s['start'][0], 4), 'y1_mm': round(s['start'][1], 4),
                    'x2_mm': round(s['end'][0], 4), 'y2_mm': round(s['end'][1], 4),
                    'width_mm': round(s['width'], 4),
                }
                for s in segs
            ]

        signals.append(sig)
    return signals


# ============================================================================
# JSON Output Builders
# ============================================================================

def build_schematic_json(project_name, components, lib_pin_types, net_class_map,
                         net_classes, sheet_count, pcb_nets_data=None):
    """Build schematic JSON structure."""
    data = {
        'thomsonlint_version': VERSION,
        'export_date': datetime.now(timezone.utc).isoformat(),
        'mode': 'schematic',
        'project': {
            'name': project_name,
            'variant': '',
            'sheets_count': sheet_count,
        },
        'components': components,
    }

    # Build nets from PCB data if available (authoritative netlist)
    nets_list = []
    analysis = {
        'power_nets': [],
        'ground_nets': [],
        'differential_pairs': [],
        'clock_nets': [],
        'floating_inputs': [],
        'single_pin_nets': [],
    }

    if pcb_nets_data:
        net_names = pcb_nets_data['nets']
        net_pins = pcb_nets_data.get('net_pins', {})

        diff_seen = set()

        for net_id, net_name in sorted(net_names.items()):
            if net_id == 0 or not net_name:
                continue

            is_pwr = is_power_net(net_name)
            is_gnd = is_ground_net(net_name)
            is_clk = is_clock_net(net_name)
            diff_member = is_diff_pair_member(net_name)
            is_diff = diff_member != 0
            diff_partner = find_diff_partner(net_name) if is_diff else None
            volt_guess = guess_voltage(net_name) or None

            # Net class
            cls_name = net_class_map.get(net_name, net_class_map.get('/' + net_name, 'Default'))
            # cls_info available in net_classes[cls_name] if needed

            # Pins on this net
            pins = net_pins.get(net_id, [])
            pin_list = []
            has_driver = False
            has_input = False
            has_power = False

            for ref, pad_name, lib_id in pins:
                direction = 'UNK'
                if lib_id in lib_pin_types and pad_name in lib_pin_types[lib_id]:
                    direction = lib_pin_types[lib_id][pad_name]
                pin_list.append({'part': ref, 'pin': pad_name, 'direction': direction})
                if direction in ('OUT', 'IO'):
                    has_driver = True
                if direction in ('PWR', 'SUP'):
                    has_power = True
                if direction == 'IN':
                    has_input = True

            net_entry = {
                'name': net_name,
                'class': cls_name,
                'is_power': is_pwr,
                'is_ground': is_gnd,
                'is_clock': is_clk,
                'is_differential': is_diff,
                'diff_pair_partner': diff_partner,
                'voltage_guess': volt_guess,
                'pins': pin_list,
            }
            nets_list.append(net_entry)

            # Analysis tracking
            if is_pwr:
                analysis['power_nets'].append(net_name)
            if is_gnd:
                analysis['ground_nets'].append(net_name)
            if is_clk:
                analysis['clock_nets'].append(net_name)
            if diff_member == 1 and net_name not in diff_seen:
                diff_seen.add(net_name)
                analysis['differential_pairs'].append({
                    'positive': net_name,
                    'negative': diff_partner or '',
                    'interface': guess_diff_interface(net_name),
                })
            if len(pin_list) == 1:
                analysis['single_pin_nets'].append(net_name)
            if has_input and not has_driver and not has_power and not is_pwr and not is_gnd:
                for p in pin_list:
                    if p['direction'] == 'IN':
                        analysis['floating_inputs'].append({'part': p['part'], 'pin': p['pin']})

    data['nets'] = nets_list
    data['analysis'] = analysis
    return data


def build_board_json(board_data):
    """Build board JSON structure."""
    footprints = board_data['footprints']
    nets = board_data['nets']
    outline = board_data['board_outline']
    layers = board_data['layers']
    segments = board_data['segments']
    vias = board_data['vias']
    zones = board_data['zones']

    # Components
    components = []
    for fp in footprints:
        pad_list = [{'name': p['name'], 'x_mm': p['x_mm'], 'y_mm': p['y_mm']} for p in fp['pads']]
        components.append({
            'ref': fp['ref'],
            'package': fp['package'],
            'value': fp['value'],
            'x_mm': fp['x_mm'],
            'y_mm': fp['y_mm'],
            'rotation': fp['rotation'],
            'side': fp['side'],
            'pads': pad_list,
        })

    # Board info
    board_info = {
        'area': {
            'width_mm': outline['width_mm'] if outline else 0,
            'height_mm': outline['height_mm'] if outline else 0,
            'x1_mm': round(outline['x1'], 4) if outline else 0,
            'y1_mm': round(outline['y1'], 4) if outline else 0,
            'x2_mm': round(outline['x2'], 4) if outline else 0,
            'y2_mm': round(outline['y2'], 4) if outline else 0,
        },
        'layers_used': [{'number': l['number'], 'name': l['name']} for l in layers],
        'layer_count': len(layers),
        'holes': [],  # TODO: could aggregate via/tht drill holes
        'polygons': [
            {'signal': z['net_name'], 'layers': z['layers']}
            for z in zones
        ],
    }

    # Signals
    signals = compute_signal_stats(segments, vias, nets)

    # Analysis
    analysis = {
        'component_edge_distances': compute_edge_distances(footprints, outline),
        'decoupling_proximity': compute_decoupling_proximity(footprints),
        'ground_plane_layers': compute_ground_plane_layers(zones),
    }

    data = {
        'thomsonlint_version': VERSION,
        'export_date': datetime.now(timezone.utc).isoformat(),
        'mode': 'board',
        'components': components,
        'board': board_info,
        'signals': signals,
        'analysis': analysis,
    }
    return data


# ============================================================================
# Build PCB net-to-pin mapping for schematic enrichment
# ============================================================================

def build_net_pin_mapping(board_data, sch_components):
    """Build net_id -> [(ref, pad_name, lib_id)] from PCB footprint pads."""
    # Map ref -> lib_id from schematic components
    ref_to_lib = {}
    for comp in sch_components:
        ref_to_lib[comp['ref']] = comp['device']

    net_pins = defaultdict(list)
    for fp in board_data['footprints']:
        ref = fp['ref']
        lib_id = ref_to_lib.get(ref, '')
        for pad in fp['pads']:
            if pad['net_id'] and pad['net_name']:
                net_pins[pad['net_id']].append((ref, pad['name'], lib_id))
    return net_pins


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Export KiCad 9 project data for ThomsonLint AI design review.')
    parser.add_argument('project_path', help='Path to .kicad_pro file')
    parser.add_argument('--output', '-o', default=None,
                        help='Output directory (default: exports/ next to project)')
    args = parser.parse_args()

    pro_path = os.path.abspath(args.project_path)
    if not os.path.isfile(pro_path):
        print(f"Error: file not found: {pro_path}", file=sys.stderr)
        sys.exit(1)

    project_dir = os.path.dirname(pro_path)
    base_name = os.path.splitext(os.path.basename(pro_path))[0]

    # Derive paths
    sch_path = os.path.join(project_dir, base_name + '.kicad_sch')
    pcb_path = os.path.join(project_dir, base_name + '.kicad_pcb')
    has_sch = os.path.isfile(sch_path)
    has_pcb = os.path.isfile(pcb_path)

    if not has_sch and not has_pcb:
        print(f"Error: no .kicad_sch or .kicad_pcb found for {base_name}", file=sys.stderr)
        sys.exit(1)

    # Output directory: default to repo-root/exports/ (locate via script path)
    if args.output:
        out_dir = os.path.abspath(args.output)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)  # tools/ -> repo root
        out_dir = os.path.join(repo_root, 'exports')
    os.makedirs(out_dir, exist_ok=True)

    # Read project file
    print(f"Reading project: {base_name}", file=sys.stderr)
    net_class_map, net_classes, project_meta = read_kicad_project(pro_path)
    project_name = project_meta.get('ProjectTitle', base_name)

    # Parse board first (provides authoritative netlist)
    board_data = None
    if has_pcb:
        print("Parsing board...", file=sys.stderr)
        board_data = parse_board(pcb_path)

    # Parse schematic
    sch_components = []
    lib_pin_types = {}
    sheet_count = 0
    if has_sch:
        print("Parsing schematic...", file=sys.stderr)
        sch_components, lib_pin_types, sheet_count = parse_schematic(
            sch_path, project_dir, project_name=base_name)
        print(f"  Found {len(sch_components)} components across {sheet_count} sheets", file=sys.stderr)

    # Generate schematic JSON
    if has_sch:
        print("Building schematic JSON...", file=sys.stderr)
        pcb_nets_data = None
        if board_data:
            net_pins = build_net_pin_mapping(board_data, sch_components)
            pcb_nets_data = {'nets': board_data['nets'], 'net_pins': dict(net_pins)}

        sch_json = build_schematic_json(
            project_name, sch_components, lib_pin_types,
            net_class_map, net_classes, sheet_count, pcb_nets_data)

        sch_out = os.path.join(out_dir, f"{base_name}-thomson-export-sch.json")
        with open(sch_out, 'w', encoding='utf-8') as f:
            json.dump(sch_json, f, indent=2, ensure_ascii=False)
        print(f"  Wrote: {sch_out}", file=sys.stderr)

    # Generate board JSON
    if has_pcb and board_data:
        print("Building board JSON...", file=sys.stderr)
        brd_json = build_board_json(board_data)

        brd_out = os.path.join(out_dir, f"{base_name}-thomson-export-brd.json")
        with open(brd_out, 'w', encoding='utf-8') as f:
            json.dump(brd_json, f, indent=2, ensure_ascii=False)
        print(f"  Wrote: {brd_out}", file=sys.stderr)

    # Summary
    if has_sch and has_pcb and board_data:
        n_nets = len([n for nid, n in board_data['nets'].items() if nid != 0 and n])
        n_segs = len(board_data['segments'])
        n_vias = len(board_data['vias'])
        n_layers = len(board_data['layers'])
        outline = board_data['board_outline']
        print(f"\nSummary:", file=sys.stderr)
        print(f"  Components: {len(sch_components)} (schematic), {len(board_data['footprints'])} (board)", file=sys.stderr)
        print(f"  Nets: {n_nets}", file=sys.stderr)
        print(f"  Copper layers: {n_layers}", file=sys.stderr)
        if outline:
            print(f"  Board size: {outline['width_mm']:.1f} x {outline['height_mm']:.1f} mm", file=sys.stderr)
        print(f"  Segments: {n_segs}, Vias: {n_vias}", file=sys.stderr)

    print("\nDone!", file=sys.stderr)


if __name__ == '__main__':
    main()
