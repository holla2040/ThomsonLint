#!/usr/bin/env python3
"""Test negative clearance clamping fix."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from geometry_helpers import load_board_json, calculate_min_clearance, get_all_net_segments

board = load_board_json(str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-brd.json"))

print("="*70)
print("Testing Clearance Clamping (Negative → 0.0 on Overlap)")
print("="*70)

# Get all nets
all_nets = get_all_net_segments(board)
net_names = list(all_nets.keys())

print(f"\nTotal nets: {len(net_names)}")
print(f"\nTesting clearances between various net pairs...")

# Test a few net pairs
test_pairs = [
    ("V5P0", "GND"),
    ("V24P0", "GND"),
    ("V24P0", "V5P0"),
    ("XY2_CLK-1_P", "XY2_CLK-1_N"),  # Differential pair (should be close)
]

negative_clearances_found = 0
zero_clearances_found = 0
positive_clearances_found = 0

for net_a, net_b in test_pairs:
    if net_a not in net_names or net_b not in net_names:
        print(f"\n  ⚠️  {net_a} ↔ {net_b}: One or both nets not found")
        continue
    
    result = calculate_min_clearance(board, net_a, net_b)
    clearance = result.min_clearance
    
    if clearance < 0:
        negative_clearances_found += 1
        print(f"\n  ❌ {net_a} ↔ {net_b}: {clearance:.6f} (NEGATIVE - BUG!)")
    elif clearance == 0.0:
        zero_clearances_found += 1
        print(f"\n  ⚠️  {net_a} ↔ {net_b}: {clearance:.6f} (OVERLAP/SHORT)")
    else:
        positive_clearances_found += 1
        print(f"\n  ✓ {net_a} ↔ {net_b}: {clearance:.6f} (OK)")
    
    if result.clearance_location:
        print(f"     Location: ({result.clearance_location[0]:.4f}, {result.clearance_location[1]:.4f})")
        print(f"     Layer: {result.clearance_layer}")

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
print(f"Negative clearances: {negative_clearances_found}")
print(f"Zero clearances (overlap/short): {zero_clearances_found}")
print(f"Positive clearances: {positive_clearances_found}")

if negative_clearances_found > 0:
    print("\n❌ FAIL: Negative clearances found - clamping not working!")
    sys.exit(1)
else:
    print("\n✅ PASS: All clearances >= 0.0 (clamping working correctly)")
    print("\nPhysical interpretation:")
    print("  0.0 = traces overlap or touch (short circuit)")
    print("  >0.0 = traces separated by clearance distance")
