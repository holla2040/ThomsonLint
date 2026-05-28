#!/usr/bin/env python3
"""Test net-type-aware board edge clearances."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from geometry_helpers import load_board_json, check_board_edge_clearance

board = load_board_json(str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-brd.json"))

print("Testing net-type-aware board edge clearances...")
print("Rules:")
print("  Ground nets (GND): 25 mils (0.635mm)")
print("  Power nets (VCC, 3V3, 5V): 50 mils (1.27mm)")
print("  Signal nets: 50 mils (1.27mm)")

result = check_board_edge_clearance(
    board,
    ground_clearance_mm=0.635,  # 25 mils
    power_clearance_mm=1.27,    # 50 mils
    signal_clearance_mm=1.27    # 50 mils
)

print(f"\n✓ Outline found: {result.outline_found}")
print(f"  Segments: {result.outline_segment_count}")
print(f"  Board units: {result.units}")

print(f"\nViolations: {len(result.violations)}")

# Group violations by net type
ground_violations = [v for v in result.violations if v.feature_net and any(p in v.feature_net.upper() for p in ["GND", "GROUND", "VSS"])]
power_violations = [v for v in result.violations if v.feature_net and any(p in v.feature_net.upper() for p in ["VCC", "VDD", "V5P0", "V24P0", "3V3"])]
signal_violations = [v for v in result.violations if v not in ground_violations and v not in power_violations]

print(f"\n  Ground violations: {len(ground_violations)} (< 25 mils)")
print(f"  Power violations: {len(power_violations)} (< 50 mils)")
print(f"  Signal violations: {len(signal_violations)} (< 50 mils)")

if result.violations:
    print(f"\nSample violations:")
    for v in result.violations[:10]:
        net_type = "GND" if v.feature_net and "GND" in v.feature_net.upper() else \
                   "PWR" if v.feature_net and any(p in v.feature_net.upper() for p in ["VCC", "VDD", "V5P0", "V24P0"]) else \
                   "SIG"
        print(f"  [{net_type}] {v.feature_net or 'unknown'}: {v.distance_to_edge:.4f}\" ({v.distance_to_edge * 25.4:.2f}mm) - {v.severity}")

print(f"\nPass: {result.pass_status}")
