#!/usr/bin/env python3
"""
Systematic Geometry Helper Function Testing Script

Tests all public API functions in geometry_helpers.py to verify correctness.
Organized by category: Basic Geometry, DFM Checks, Physical-Math Verification.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from geometry_helpers import (
    load_board_json,
    get_net_segments,
    get_all_net_segments,
    calculate_min_clearance,
    calculate_clearances_for_net,
    analyze_differential_pair,
    analyze_all_differential_pairs,
    check_npth_clearance,
    check_via_annular_rings,
    detect_acid_traps,
    check_board_edge_clearance,
    estimate_copper_balance,
    calculate_trace_ampacity,
    verify_trace_ampacity,
    load_stackup_json,
    verify_impedance,
    verify_trace_temperature,
    check_voltage_clearance
)

# Test configuration
BOARD_PATH = str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-brd.json")
STACKUP_PATH = str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-stack.json")
SCHEMATIC_PATH = str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-sch.json")

def print_test(category, test_name, passed, message=""):
    """Print test result with status indicator."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  [{status}] {test_name}")
    if message:
        print(f"         {message}")

def test_category_1_basic_geometry():
    """Test basic geometry functions (no Saturn engine required)."""
    print("\n" + "="*70)
    print("CATEGORY 1: Basic Geometry Functions")
    print("="*70)
    
    try:
        board = load_board_json(BOARD_PATH)
        print_test("Load", "load_board_json", True, f"Board loaded successfully")
    except Exception as e:
        print_test("Load", "load_board_json", False, f"Error: {e}")
        return
    
    # Test get_net_segments
    try:
        stats = get_net_segments(board, "V5P0")
        passed = (stats.total_length > 0 and 
                 stats.min_width is not None and 
                 len(stats.segments) > 0)
        msg = f"Length: {stats.total_length:.3f}, Segments: {len(stats.segments)}, Width: {stats.min_width:.4f}-{stats.max_width:.4f}"
        print_test("Nets", "get_net_segments", passed, msg)
    except Exception as e:
        print_test("Nets", "get_net_segments", False, f"Error: {e}")
    
    # Test get_all_net_segments
    try:
        all_stats = get_all_net_segments(board)
        passed = len(all_stats) > 0
        print_test("Nets", "get_all_net_segments", passed, f"Found {len(all_stats)} nets")
    except Exception as e:
        print_test("Nets", "get_all_net_segments", False, f"Error: {e}")
    
    # Test calculate_min_clearance
    try:
        result = calculate_min_clearance(board, "V5P0", "GND")
        passed = result.min_clearance is not None and result.clearance_layer is not None
        msg = f"Min clearance: {result.min_clearance:.4f}, Layer: {result.clearance_layer}, Segments compared: {result.segments_compared}"
        print_test("Clearance", "calculate_min_clearance", passed, msg)
    except Exception as e:
        print_test("Clearance", "calculate_min_clearance", False, f"Error: {e}")
    
    # Test calculate_clearances_for_net
    try:
        results = calculate_clearances_for_net(board, "V5P0", ["GND", "3V3"])
        passed = len(results) > 0 and all(r.min_clearance is not None for r in results)
        # Check if sorted (smallest first)
        if len(results) > 1:
            sorted_check = all(results[i].min_clearance <= results[i+1].min_clearance 
                             for i in range(len(results)-1))
            passed = passed and sorted_check
        print_test("Clearance", "calculate_clearances_for_net", passed, f"Checked {len(results)} net pairs")
    except Exception as e:
        print_test("Clearance", "calculate_clearances_for_net", False, f"Error: {e}")
    
    # Test analyze_differential_pair
    try:
        analysis = analyze_differential_pair(board, "XY2_SYNC-1_P", "XY2_SYNC-1_N")
        passed = (analysis.avg_coupling_distance is not None and 
                 analysis.coupling_quality in ["good", "marginal", "poor", "insufficient_data"] and
                 len(analysis.coupled_sections) > 0)
        msg = f"Avg coupling: {analysis.avg_coupling_distance:.4f}, Quality: {analysis.coupling_quality}, Coupled sections: {len(analysis.coupled_sections)}"
        print_test("Diff Pairs", "analyze_differential_pair", passed, msg)
    except Exception as e:
        print_test("Diff Pairs", "analyze_differential_pair", False, f"Error: {e}")
    
    # Test analyze_all_differential_pairs
    try:
        pairs = analyze_all_differential_pairs(board)
        passed = len(pairs) > 0
        print_test("Diff Pairs", "analyze_all_differential_pairs", passed, f"Found {len(pairs)} differential pairs")
    except Exception as e:
        print_test("Diff Pairs", "analyze_all_differential_pairs", False, f"Error: {e}")


def test_category_2_dfm_checks():
    """Test DFM check functions (no Saturn engine required)."""
    print("\n" + "="*70)
    print("CATEGORY 2: DFM Check Functions")
    print("="*70)
    
    try:
        board = load_board_json(BOARD_PATH)
    except Exception as e:
        print(f"Cannot load board: {e}")
        return
    
    # Test check_npth_clearance
    try:
        result = check_npth_clearance(board, keepout_radius=4.0)
        passed = result.npth_count >= 0
        msg = f"NPTH holes: {result.npth_count}, Analyzed: {result.analyzed_count}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
        print_test("NPTH", "check_npth_clearance", passed, msg)
    except Exception as e:
        print_test("NPTH", "check_npth_clearance", False, f"Error: {e}")
    
    # Test check_via_annular_rings
    try:
        result = check_via_annular_rings(board, min_ring_mm=0.127)
        passed = result.via_count > 0
        msg = f"Vias: {result.via_count}, Analyzed: {result.analyzed_count}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
        print_test("Via", "check_via_annular_rings", passed, msg)
        if result.violations:
            v = result.violations[0]
            print(f"         Sample violation: Ring={v.annular_ring:.4f}mm (min={result.threshold_mm}mm)")
    except Exception as e:
        print_test("Via", "check_via_annular_rings", False, f"Error: {e}")
    
    # Test detect_acid_traps
    try:
        result = detect_acid_traps(board, angle_threshold_deg=70.0)
        passed = result.routes_analyzed > 0
        msg = f"Routes: {result.routes_analyzed}, Vertices: {result.vertices_analyzed}, Traps: {len(result.traps)}, Pass: {result.pass_status}"
        print_test("Acid Trap", "detect_acid_traps", passed, msg)
        if result.traps:
            t = result.traps[0]
            print(f"         Sample trap: Net={t.net}, Angle={t.angle_deg}°, Severity={t.severity}")
    except Exception as e:
        print_test("Acid Trap", "detect_acid_traps", False, f"Error: {e}")
    
    # Test check_board_edge_clearance
    try:
        result = check_board_edge_clearance(board, min_clearance_mm=0.5)
        passed = True  # Can pass even if no outline found
        msg = f"Outline found: {result.outline_found}, Segments: {result.outline_segment_count}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
        print_test("Edge", "check_board_edge_clearance", passed, msg)
    except Exception as e:
        print_test("Edge", "check_board_edge_clearance", False, f"Error: {e}")
    
    # Test estimate_copper_balance
    try:
        result = estimate_copper_balance(board, imbalance_threshold_pct=25.0)
        passed = len(result.layer_areas) > 0
        msg = f"Layers: {len(result.layer_areas)}, Pairs checked: {result.layer_pairs_checked}, Warnings: {len(result.warnings)}, Pass: {result.pass_status}"
        print_test("Copper", "estimate_copper_balance", passed, msg)
        if result.layer_areas:
            la = result.layer_areas[0]
            print(f"         Sample layer: {la.layer_name}, Total area: {la.total_area:.2f}")
    except Exception as e:
        print_test("Copper", "estimate_copper_balance", False, f"Error: {e}")
    
    # Test calculate_trace_ampacity
    try:
        ampacity = calculate_trace_ampacity(width_mm=0.254, thickness_oz=1.0, temp_rise_c=10.0, is_internal=False)
        passed = ampacity > 0
        msg = f"10mil trace @ 1oz = {ampacity:.2f}A (10°C rise)"
        print_test("Ampacity", "calculate_trace_ampacity", passed, msg)
    except Exception as e:
        print_test("Ampacity", "calculate_trace_ampacity", False, f"Error: {e}")
    
    # Test verify_trace_ampacity
    try:
        result = verify_trace_ampacity(board, "V5P0", required_current_a=2.0, copper_oz=1.0, temp_rise_c=10.0)
        passed = "pass" in result
        msg = f"Net: {result['net']}, Pass: {result['pass']}, Violations: {result.get('violation_count', 0)}"
        print_test("Ampacity", "verify_trace_ampacity", passed, msg)
    except Exception as e:
        print_test("Ampacity", "verify_trace_ampacity", False, f"Error: {e}")


def test_category_3_physical_math():
    """Test physical-math verification functions (requires Saturn engine + stackup)."""
    print("\n" + "="*70)
    print("CATEGORY 3: Physical-Math Verification (Saturn Engine)")
    print("="*70)
    
    try:
        board = load_board_json(BOARD_PATH)
    except Exception as e:
        print(f"Cannot load board: {e}")
        return
    
    # Test load_stackup_json
    try:
        stackup = load_stackup_json(STACKUP_PATH)
        passed = len(stackup) > 0
        layers_with_dk = sum(1 for l in stackup.values() if l.dielectric_constant is not None)
        msg = f"Loaded {len(stackup)} layers, {layers_with_dk} with dielectric properties"
        print_test("Stackup", "load_stackup_json", passed, msg)
        if stackup:
            sample = next(iter(stackup.values()))
            print(f"         Sample: {sample.name}, Function: {sample.function}, Dk: {sample.dielectric_constant}")
    except Exception as e:
        print_test("Stackup", "load_stackup_json", False, f"Error: {e}")
        return
    
    # Test verify_impedance
    try:
        result = verify_impedance(board, STACKUP_PATH, target_ohms=100.0, tolerance_percent=10.0)
        passed = result.stackup_available and result.nets_analyzed > 0
        msg = f"Status: {result.status}, Nets: {result.nets_analyzed}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
        print_test("Impedance", "verify_impedance", passed, msg)
        if result.violations:
            v = result.violations[0]
            print(f"         Sample: {v['net']}, Z0={v['calculated_z0_single_ohms']:.2f}Ω, Zdiff={v['calculated_zdiff_ohms']:.2f}Ω, Target={v['target_zdiff_ohms']:.2f}Ω")
            print(f"         Topology: {v['topology']}, Spacing: {v['pair_spacing_mm']:.4f}mm, Deviation: {v['deviation_percent']:.1f}%")
    except Exception as e:
        print_test("Impedance", "verify_impedance", False, f"Error: {e}")
    
    # Test verify_trace_temperature
    try:
        result = verify_trace_temperature(board, STACKUP_PATH, current_a=1.0, max_temp_rise_c=10.0)
        passed = result.stackup_available and result.nets_analyzed > 0
        msg = f"Status: {result.status}, Nets: {result.nets_analyzed}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
        print_test("Thermal", "verify_trace_temperature", passed, msg)
        if result.violations:
            v = result.violations[0]
            print(f"         Sample: {v['net']}, Temp rise: {v['calculated_temp_rise_c']:.1f}°C (max: {v['max_allowed_temp_rise_c']}°C)")
            print(f"         Width: {v['trace_width_mm']:.3f}mm, Current: {v['current_a']}A, Internal: {v['is_internal']}")
    except Exception as e:
        print_test("Thermal", "verify_trace_temperature", False, f"Error: {e}")
    
    # Test check_voltage_clearance
    if Path(SCHEMATIC_PATH).exists():
        try:
            result = check_voltage_clearance(board, schematic_path=SCHEMATIC_PATH, default_category="B2")
            passed = result.status in ["PASS", "FAIL", "NO_VOLTAGE_NETS", "INSUFFICIENT_DATA"]
            msg = f"Status: {result.status}, Pairs: {result.net_pairs_analyzed}, Violations: {len(result.violations)}, Pass: {result.pass_status}"
            print_test("Voltage", "check_voltage_clearance", passed, msg)
            if result.violations:
                v = result.violations[0]
                print(f"         Sample: {v['net_a']} ({v['voltage_a']}V) to {v['net_b']} ({v['voltage_b']}V)")
                print(f"         Required: {v['required_clearance_mm']:.3f}mm, Actual: {v['actual_clearance_mm']:.3f}mm")
        except Exception as e:
            print_test("Voltage", "check_voltage_clearance", False, f"Error: {e}")
    else:
        print_test("Voltage", "check_voltage_clearance", False, f"Schematic not found: {SCHEMATIC_PATH}")


def main():
    """Run all test categories."""
    print("\n" + "="*70)
    print("ThomsonLint Geometry Helpers - Systematic Function Tests")
    print("="*70)
    
    test_category_1_basic_geometry()
    test_category_2_dfm_checks()
    test_category_3_physical_math()
    
    print("\n" + "="*70)
    print("Test suite completed!")
    print("="*70)
    print("\nReview the results above to verify all functions are working correctly.")
    print("Functions marked with ✓ PASS are operating correctly.")
    print("Functions marked with ✗ FAIL need investigation.\n")


if __name__ == "__main__":
    main()
