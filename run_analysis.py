#!/usr/bin/env python3
"""Direct analysis of the JSON files"""

import json
import sys
import os

os.chdir('C:\\_Working_VS\\ThomsonLint')

try:
    print("=" * 70)
    print("EXTRACT NETS ANALYSIS")
    print("=" * 70)
    
    # Load board JSON
    print("\n[1/3] Loading board JSON file...")
    with open('TestProject/post_conversion/TestProject-thomson-export-brd.json') as f:
        board = json.load(f)
    print(f"    ✓ Loaded successfully")
    
    # Extract nets from routes
    print("\n[2/3] Extracting nets from routes section...")
    routes = board.get("routes", [])
    print(f"    Total routes: {len(routes)}")
    
    nets = sorted(set(r.get("net") for r in routes if r.get("net")))
    print(f"    ✓ Extracted {len(nets)} unique nets")
    
    # Display results
    output = []
    output.append(f"\nTotal unique nets in board: {len(nets)}")
    output.append("\nFirst 50 nets:")
    for net in nets[:50]:
        output.append(f"  {net}")
    
    # Look for differential pair patterns
    output.append("\n" + "="*60)
    output.append("Differential pair candidates:")
    output.append("="*60)
    
    patterns = {
        "_P/_N": [],
        "+/-": [],
        "_DP/_DN": [],
        "_POS/_NEG": []
    }
    
    for net in nets:
        if net.endswith("_P") and net[:-2] + "_N" in nets:
            patterns["_P/_N"].append((net, net[:-2] + "_N"))
        elif net.endswith("+") and net[:-1] + "-" in nets:
            patterns["+/-"].append((net, net[:-1] + "-"))
        elif net.endswith("_DP") and net[:-3] + "_DN" in nets:
            patterns["_DP/_DN"].append((net, net[:-3] + "_DN"))
        elif net.endswith("_POS") and net[:-4] + "_NEG" in nets:
            patterns["_POS/_NEG"].append((net, net[:-4] + "_NEG"))
    
    for pattern, pairs in patterns.items():
        if pairs:
            output.append(f"\n{pattern} pairs: {len(pairs)}")
            for p, n in pairs[:10]:
                output.append(f"  {p} / {n}")
        else:
            output.append(f"\n{pattern} pairs: 0")
    
    # Check schematic analysis
    output.append("\n" + "="*60)
    output.append("Schematic analysis:")
    output.append("="*60)
    
    print("\n[3/3] Loading schematic JSON file...")
    with open('TestProject/post_conversion/TestProject-thomson-export-sch.json') as f:
        sch = json.load(f)
    print(f"    ✓ Loaded successfully")
    
    clock_nets = sch.get("analysis", {}).get("clock_nets", [])
    output.append(f"\nClock nets (potential differential): {len(clock_nets)}")
    for net in clock_nets:
        output.append(f"  {net}")
    
    # Prepare final output
    result_text = '\n'.join(output)
    
    # Write to file
    print("\n[4/4] Writing results to diagnose_output.txt...")
    with open('diagnose_output.txt', 'w') as out:
        out.write(result_text)
    print(f"    ✓ File written successfully")
    
    # Print to console
    print("\n" + "=" * 70)
    print("CONSOLE OUTPUT:")
    print("=" * 70)
    print(result_text)
    
    print("\n" + "=" * 70)
    print("✓ Analysis complete!")
    print("=" * 70)

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
