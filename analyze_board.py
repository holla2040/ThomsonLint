#!/usr/bin/env python3
"""Comprehensive analysis of board JSON structure"""
import json
import sys
from pathlib import Path
from collections import defaultdict

path = Path(r"c:\_Working_VS\ThomsonLint\TestProject\post_conversion\TestProject-thomson-export-brd.json")

try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("✓ JSON file loaded successfully\n")
except Exception as e:
    print(f"✗ ERROR loading JSON: {e}", file=sys.stderr)
    sys.exit(1)

# TOP-LEVEL KEYS
print("=" * 70)
print("TOP-LEVEL STRUCTURE")
print("=" * 70)
print(f"Total top-level keys: {len(data)}")
for key in sorted(data.keys()):
    val = data[key]
    if isinstance(val, list):
        print(f"  {key:20} : list[{len(val):5d}]")
    elif isinstance(val, dict):
        print(f"  {key:20} : dict[{len(val):5d} keys]")
    else:
        type_name = type(val).__name__
        val_str = str(val)[:60]
        print(f"  {key:20} : {type_name:15} = {val_str}")

# COMPONENTS
print("\n" + "=" * 70)
print("COMPONENTS STRUCTURE")
print("=" * 70)
components = data.get("components", [])
print(f"Total components: {len(components)}")
if components:
    print(f"First component keys: {list(components[0].keys())}")
    # Count by type
    by_refdes = defaultdict(int)
    for c in components:
        refdes = c.get("refdes", "UNKNOWN")
        prefix = refdes.split()[0] if refdes else "?"
        by_refdes[prefix[0]] += 1
    print("Components by type prefix:")
    for prefix in sorted(by_refdes.keys()):
        print(f"    {prefix}: {by_refdes[prefix]}")

# ROUTES
print("\n" + "=" * 70)
print("ROUTES STRUCTURE")
print("=" * 70)
routes = data.get("routes", [])
print(f"Total routes: {len(routes)}")
if routes:
    print(f"First route keys: {list(routes[0].keys())}")
    print(f"First route sample:")
    for key in list(routes[0].keys())[:8]:
        val = routes[0][key]
        if isinstance(val, list):
            print(f"    {key}: list[{len(val)}]")
        elif isinstance(val, dict):
            print(f"    {key}: dict")
        else:
            print(f"    {key}: {val}")
    
    # Analyze nets in routes
    nets_in_routes = defaultdict(int)
    for r in routes:
        net = r.get("net")
        if net:
            nets_in_routes[net] += 1
    print(f"\nUnique nets referenced by routes: {len(nets_in_routes)}")
    sample_nets = list(nets_in_routes.keys())[:10]
    print(f"Sample net names: {sample_nets}")

# NETS
print("\n" + "=" * 70)
print("NETS STRUCTURE")
print("=" * 70)
nets = data.get("nets", [])
print(f"Total nets: {len(nets)}")
if nets:
    print(f"First net keys: {list(nets[0].keys())}")
    print(f"First net sample:")
    for key in list(nets[0].keys())[:6]:
        val = nets[0][key]
        if isinstance(val, list):
            print(f"    {key}: list[{len(val)}]")
        else:
            print(f"    {key}: {val}")
    
    # Analyze net names
    all_net_names = [n.get("name") for n in nets if n.get("name")]
    v3p3_nets = [n for n in all_net_names if "V3P3" in (n or "").upper()]
    gnd_nets = [n for n in all_net_names if "GND" in (n or "").upper()]
    vdd_nets = [n for n in all_net_names if "VDD" in (n or "").upper()]
    vcc_nets = [n for n in all_net_names if "VCC" in (n or "").upper()]
    
    print(f"\nNet name analysis:")
    print(f"    V3P3 variants: {len(v3p3_nets)} - {v3p3_nets[:5]}")
    print(f"    GND variants:  {len(gnd_nets)} - {gnd_nets[:5]}")
    print(f"    VDD variants:  {len(vdd_nets)} - {vdd_nets[:5]}")
    print(f"    VCC variants:  {len(vcc_nets)} - {vcc_nets[:5]}")
    print(f"    Other nets:    {len(all_net_names) - len(v3p3_nets) - len(gnd_nets) - len(vdd_nets) - len(vcc_nets)}")

# POLYGONS
print("\n" + "=" * 70)
print("POLYGONS STRUCTURE")
print("=" * 70)
polygons = data.get("polygons", [])
print(f"Total polygons: {len(polygons)}")
if polygons:
    print(f"First polygon keys: {list(polygons[0].keys())}")
    
    # Analyze nets in polygons
    poly_nets = defaultdict(int)
    for p in polygons:
        net = p.get("net")
        if net:
            poly_nets[net] += 1
    print(f"Unique nets referenced by polygons: {len(poly_nets)}")
    sample_poly_nets = list(poly_nets.keys())[:10]
    print(f"Sample polygon net names: {sample_poly_nets}")
    
    # Count by layer
    by_layer = defaultdict(int)
    for p in polygons:
        layer = p.get("layer", "UNKNOWN")
        by_layer[layer] += 1
    print(f"Polygons by layer: {dict(by_layer)}")

# PADS
print("\n" + "=" * 70)
print("PADS STRUCTURE")
print("=" * 70)
pads = data.get("pads", [])
print(f"Total pads: {len(pads)}")
if pads:
    print(f"First pad keys: {list(pads[0].keys())}")
    
    # Analyze nets in pads
    pad_nets = defaultdict(int)
    for p in pads:
        net = p.get("net")
        if net:
            pad_nets[net] += 1
    print(f"Unique nets referenced by pads: {len(pad_nets)}")
    sample_pad_nets = list(pad_nets.keys())[:10]
    print(f"Sample pad net names: {sample_pad_nets}")
    
    # Count by layer
    by_layer = defaultdict(int)
    for p in pads:
        layer = p.get("layer", "UNKNOWN")
        by_layer[layer] += 1
    print(f"Pads by layer: {dict(by_layer)}")

# ADDITIONAL KEYS
print("\n" + "=" * 70)
print("ADDITIONAL DATA")
print("=" * 70)
for key in ["source", "project_name", "units", "parser_version"]:
    if key in data:
        val = data[key]
        if isinstance(val, dict):
            print(f"{key}: {json.dumps(val, indent=2)[:200]}")
        else:
            print(f"{key}: {val}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
