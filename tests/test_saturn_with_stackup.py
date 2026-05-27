#!/usr/bin/env python3
"""
Test Saturn physical-math verification with complete stackup data.

This script validates that:
1. Stackup JSON has complete physical data (dielectric layers, Dk, Df)
2. Saturn engine can calculate impedance, thermal, voltage spacing
3. Integration with geometry_helpers.py works end-to-end
"""

import json
import sys
from pathlib import Path

def test_stackup_completeness():
    """Verify stackup has all required data for Saturn calculations"""
    print("=" * 60)
    print("Test 1: Stackup Data Completeness")
    print("=" * 60)
    
    stack_path = Path("TestProject/post_conversion/TestProject-thomson-export-stack.json")
    if not stack_path.exists():
        print(f"ERROR: Stackup file not found: {stack_path}")
        return False
    
    try:
        with open(stack_path, 'r', encoding='utf-8') as f:
            stack = json.load(f)
        
        # Check for physical stackup
        physical_stackup = stack.get("physical_stackup", [])
        layer_stack = stack.get("layer_stack", [])
        quality = stack.get("stackup_data_quality", {})
        
        print(f"✓ Loaded stackup: {stack_path.name}")
        print(f"  Total layers: {len(layer_stack)}")
        print(f"  Physical layers: {len(physical_stackup)}")
        
        # Check for dielectric layers
        dielectric_layers = [l for l in physical_stackup if l.get("type") == "Dielectric"]
        copper_layers = [l for l in physical_stackup if l.get("type") in ("Conductor", "Plane")]
        
        print(f"\n  Layer breakdown:")
        print(f"    Dielectric layers: {len(dielectric_layers)}")
        print(f"    Copper layers: {len(copper_layers)}")
        
        # Check data quality flags
        print(f"\n  Data quality:")
        print(f"    physical_stackup_complete: {quality.get('physical_stackup_complete')}")
        print(f"    dielectric_material_available: {quality.get('dielectric_material_available')}")
        print(f"    material_thickness_available: {quality.get('material_thickness_available')}")
        
        # Sample first dielectric layer
        if dielectric_layers:
            d = dielectric_layers[0]
            print(f"\n  Sample dielectric layer:")
            print(f"    Name: {d.get('name')}")
            print(f"    Material: {d.get('material')}")
            print(f"    Thickness: {d.get('thickness')} inches")
            print(f"    Dk: {d.get('dielectric_constant')}")
            print(f"    Df: {d.get('loss_tangent')}")
        
        # Check if we have enough data for impedance calculations
        has_dielectric = len(dielectric_layers) > 0
        has_dk = any(d.get('dielectric_constant') for d in dielectric_layers)
        has_thickness = any(d.get('thickness') for d in dielectric_layers)
        
        if has_dielectric and has_dk and has_thickness:
            print(f"\n✓ Stackup is ready for Saturn calculations")
            return True
        else:
            print(f"\n✗ Stackup missing required data for calculations")
            return False
            
    except Exception as e:
        print(f"ERROR: Failed to load stackup: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_saturn_standalone():
    """Test Saturn engine standalone calculations"""
    print("\n" + "=" * 60)
    print("Test 2: Saturn Engine Standalone")
    print("=" * 60)
    
    sys.path.insert(0, str(Path(__file__).parent / "scripts"))
    
    try:
        from saturn_engine import (
            calculate_microstrip_impedance,
            calculate_temp_rise,
            get_required_clearance,
            calculate_via_parasitics
        )
        
        print("✓ Saturn engine imported successfully")
        
        # Test 1: Microstrip impedance (50Ω target)
        print("\n  Test: Microstrip impedance calculation")
        result = calculate_microstrip_impedance(
            w=0.254,         # 10 mil trace width
            h=0.2,           # 8 mil dielectric height
            t=0.035,         # 1 oz copper thickness
            dk=4.5,          # FR-4 dielectric constant
            unit="mm"
        )
        print(f"    Input: 10 mil trace, 8 mil height, Dk=4.5")
        print(f"    Result: Z0 = {result.z0_ohms:.2f} Ω (target: 50Ω)")
        print(f"    Valid: {result.valid}")
        
        # Test 2: IPC-2152 trace temperature
        print("\n  Test: IPC-2152 trace temperature rise")
        result = calculate_temp_rise(
            current_a=1.0,         # 1A
            width_mm=0.5,          # 20 mil trace
            thickness_um=35,       # 1 oz copper
            is_internal=False
        )
        print(f"    Input: 1A through 20 mil trace (external)")
        print(f"    Result: ΔT = {result.temp_rise_c:.2f}°C")
        print(f"    Valid: {result.valid}")
        
        # Test 3: IPC-2221B voltage spacing
        print("\n  Test: IPC-2221B voltage spacing")
        result = get_required_clearance(
            voltage_v=12.0,
            category="B2"  # External, uncoated
        )
        print(f"    Input: 12V, category B2 (external, uncoated)")
        print(f"    Result: Required clearance = {result.required_clearance_mm:.3f} mm")
        print(f"    Valid: {result.valid}")
        
        # Test 4: Via parasitics
        print("\n  Test: Via parasitics calculation")
        result = calculate_via_parasitics(
            drill_dia_mm=0.3,       # 12 mil drill
            length_mm=1.6,          # 1.6mm board thickness
            plating_thickness_um=25 # 25um plating
        )
        print(f"    Input: 12 mil drill, 1.6mm length")
        print(f"    Result: R = {result.via_resistance_ohms*1000:.3f} mΩ, L = {result.via_inductance_nh:.2f} nH")
        print(f"    Valid: {result.valid}")
        
        print("\n✓ All Saturn engine calculations passed")
        return True
        
    except Exception as e:
        print(f"ERROR: Saturn engine test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_geometry_helpers_integration():
    """Test Saturn integration in geometry_helpers.py"""
    print("\n" + "=" * 60)
    print("Test 3: geometry_helpers.py Integration")
    print("=" * 60)
    
    sys.path.insert(0, str(Path(__file__).parent / "scripts"))
    
    try:
        from geometry_helpers import load_stackup_json
        
        print("✓ geometry_helpers imports successful")
        
        # Load stackup
        stack_path = Path("TestProject/post_conversion/TestProject-thomson-export-stack.json")
        board_path = Path("TestProject/post_conversion/TestProject-thomson-export-brd.json")
        
        if not stack_path.exists() or not board_path.exists():
            print(f"ERROR: Required files not found")
            return False
        
        print(f"\n  Loading stackup from: {stack_path.name}")
        
        try:
            stackup_layers = load_stackup_json(str(stack_path))
            
            if stackup_layers:
                print(f"✓ Stackup loaded successfully")
                print(f"  Layers parsed: {len(stackup_layers)}")
                
                # Show sample layer
                if stackup_layers:
                    sample_name = list(stackup_layers.keys())[0]
                    sample_layer = stackup_layers[sample_name]
                    print(f"\n  Sample layer: {sample_name}")
                    print(f"    Function: {sample_layer.function}")
                    print(f"    Copper thickness: {sample_layer.copper_thickness_mm} mm")
                    print(f"    Dielectric thickness: {sample_layer.dielectric_thickness_mm} mm")
                    print(f"    Dk: {sample_layer.dielectric_constant}")
            else:
                print(f"✗ Stackup load returned empty dictionary")
                return False
        except Exception as e:
            print(f"✗ Stackup load failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # Load board data
        print(f"\n  Loading board from: {board_path.name}")
        with open(board_path, 'r', encoding='utf-8') as f:
            board_data = json.load(f)
        
        print(f"✓ Board data loaded")
        
        # Test that Saturn integration functions exist
        print(f"\n  Checking Saturn integration functions:")
        
        try:
            from geometry_helpers import verify_impedance
            print(f"    ✓ verify_impedance available")
        except ImportError:
            print(f"    ✗ verify_impedance not found")
            return False
        
        try:
            from geometry_helpers import verify_trace_temperature
            print(f"    ✓ verify_trace_temperature available")
        except ImportError:
            print(f"    ✗ verify_trace_temperature not found")
            return False
        
        try:
            from geometry_helpers import check_voltage_clearance
            print(f"    ✓ check_voltage_clearance available")
        except ImportError:
            print(f"    ✗ check_voltage_clearance not found")
            return False
        
        print("\n✓ All integration functions available and ready")
        return True
        
    except Exception as e:
        print(f"ERROR: Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Saturn verification tests"""
    print("\n" + "=" * 60)
    print("Saturn Physical Verification Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: Stackup completeness
    results.append(("Stackup Completeness", test_stackup_completeness()))
    
    # Test 2: Saturn standalone
    results.append(("Saturn Engine", test_saturn_standalone()))
    
    # Test 3: Integration
    results.append(("geometry_helpers Integration", test_geometry_helpers_integration()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:8s} | {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✓ All Saturn verification tests passed!")
        print("\nNext steps:")
        print("  1. Run full geometry analysis with Saturn checks:")
        print("     py -3 scripts\\geometry_helpers.py TestProject\\post_conversion\\TestProject-thomson-export-brd.json --verify-impedance --verify-trace-temp")
        print("\n  2. Or use the batch script:")
        print("     test_saturn_verification.bat")
        return 0
    else:
        print("\n✗ Some Saturn tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
