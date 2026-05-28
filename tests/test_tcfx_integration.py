#!/usr/bin/env python3
"""Test script to verify TCFX integration into thomson_bundle_converter.py"""

import json
import sys
from pathlib import Path

# Add converter directory to path
sys.path.insert(0, str(Path(__file__).parent / "converter" / "ipc2581_to_json"))

from parse_tcfx_stackup import TCFXParser, merge_tcfx_into_stack, merge_tcfx_if_available

def test_tcfx_parsing():
    """Test basic TCFX parsing"""
    print("=" * 60)
    print("Test 1: TCFX Parsing")
    print("=" * 60)
    
    tcfx_path = Path("TestProject/example_tech.tcfx")
    if not tcfx_path.exists():
        print(f"ERROR: TCFX file not found: {tcfx_path}")
        return False
    
    try:
        parser = TCFXParser(tcfx_path)
        print(f"✓ Parsed TCFX file: {tcfx_path}")
        print(f"  Units: {parser.units}")
        print(f"  Total layers parsed: {len(parser.raw_layers)}")
        
        # Count layer types
        type_counts = {}
        for layer in parser.raw_layers:
            layer_type = layer.get("type", "Unknown")
            type_counts[layer_type] = type_counts.get(layer_type, 0) + 1
        
        print(f"\n  Layer types found:")
        for layer_type, count in sorted(type_counts.items()):
            print(f"    {layer_type}: {count}")
        
        # Show dielectric layers specifically
        dielectric_layers = [l for l in parser.raw_layers if l.get("type") == "Dielectric"]
        print(f"\n  Dielectric layers ({len(dielectric_layers)}):")
        for layer in dielectric_layers:
            name = layer.get("name", "UNNAMED")
            material = layer.get("material", "?")
            thickness = layer.get("thickness")
            dk = layer.get("dielectric_constant")
            df = layer.get("loss_tangent")
            print(f"    {name:20s} | {material:10s} | {thickness} mil | Dk={dk} | Df={df}")
        
        return len(dielectric_layers) > 0
    except Exception as e:
        print(f"ERROR: Failed to parse TCFX: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stackup_merge():
    """Test merging TCFX data into stackup JSON"""
    print("\n" + "=" * 60)
    print("Test 2: Stackup JSON Merge (with Dielectric Layers)")
    print("=" * 60)
    
    tcfx_path = Path("TestProject/example_tech.tcfx")
    stack_path = Path("TestProject/post_conversion/TestProject-thomson-export-stack.json")
    
    if not tcfx_path.exists():
        print(f"ERROR: TCFX file not found: {tcfx_path}")
        return False
    
    if not stack_path.exists():
        print(f"ERROR: Stackup JSON not found: {stack_path}")
        return False
    
    try:
        # Parse TCFX
        parser = TCFXParser(tcfx_path)
        
        # Load stackup JSON
        with open(stack_path, "r", encoding="utf-8") as f:
            stack_data = json.load(f)
        
        # Count layers before merge
        layer_count_before = len(stack_data.get("layer_stack", []))
        
        # Merge
        merged_data = merge_tcfx_into_stack(parser, stack_data)
        
        # Count layers after merge
        layer_stack_after = merged_data.get("layer_stack", [])
        layer_count_after = len(layer_stack_after)
        
        # Check for dielectric layers
        dielectric_layers = [l for l in layer_stack_after if l.get("type") == "Dielectric"]
        copper_layers = [l for l in layer_stack_after if l.get("type") in ("Conductor", "Plane")]
        
        # Check physical stackup
        physical_stackup = merged_data.get("physical_stackup", [])
        
        print(f"✓ Merged TCFX data into stackup JSON")
        print(f"  Layers before merge: {layer_count_before}")
        print(f"  Layers after merge: {layer_count_after}")
        print(f"  Physical stackup layers: {len(physical_stackup)}")
        print(f"  Dielectric layers added: {len(dielectric_layers)}")
        print(f"  Copper layers: {len(copper_layers)}")
        
        # Show physical stackup (first 10)
        print("\n  Physical stackup (top → bottom):")
        for i, layer in enumerate(physical_stackup[:15]):
            name = layer.get("name", "UNNAMED")
            layer_type = layer.get("type", "?")
            material = layer.get("material") or "?"
            thickness = layer.get("thickness")
            dk = layer.get("dielectric_constant")
            print(f"    {i+1:2}. {name:20s} | {layer_type:12s} | {material:15s} | {thickness} | Dk={dk}")
        
        if len(physical_stackup) > 15:
            print(f"    ... and {len(physical_stackup) - 15} more layers")
        
        # Check metadata
        quality = merged_data.get("stackup_data_quality", {})
        print(f"\n  Stackup data quality:")
        print(f"    physical_stackup_complete: {quality.get('physical_stackup_complete')}")
        print(f"    dielectric_layer_count: {quality.get('dielectric_layer_count')}")
        print(f"    copper_layer_count: {quality.get('copper_layer_count')}")
        print(f"    source: {quality.get('source')}")
        
        return len(dielectric_layers) > 0
    except Exception as e:
        print(f"ERROR: Failed to merge stackup: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_auto_merge():
    """Test automatic TCFX discovery and merge"""
    print("\n" + "=" * 60)
    print("Test 3: Automatic TCFX Discovery")
    print("=" * 60)
    
    project_root = Path("TestProject")
    stack_path = Path("TestProject/post_conversion/TestProject-thomson-export-stack.json")
    
    if not stack_path.exists():
        print(f"ERROR: Stackup JSON not found: {stack_path}")
        return False
    
    try:
        # Load stackup JSON
        with open(stack_path, "r", encoding="utf-8") as f:
            stack_data = json.load(f)
        
        # Auto-merge
        merged_data = merge_tcfx_if_available(project_root, stack_data)
        
        # Check if merge happened
        tcfx_merge_info = merged_data.get("tcfx_merge", {})
        status = tcfx_merge_info.get("status", "NOT_ATTEMPTED")
        
        print(f"✓ Auto-merge completed")
        print(f"  Status: {status}")
        
        if status == "SUCCESS":
            print(f"  TCFX file: {tcfx_merge_info.get('tcfx_file')}")
            print(f"  Layers parsed: {tcfx_merge_info.get('layers_parsed')}")
            print(f"  Layers updated: {tcfx_merge_info.get('layers_updated')}")
            
            # Verify dielectric layers present
            physical_stackup = merged_data.get("physical_stackup", [])
            dielectric_count = sum(1 for l in physical_stackup if l.get("type") == "Dielectric")
            print(f"  Dielectric layers in physical stackup: {dielectric_count}")
            
            return dielectric_count > 0
        elif status == "ERROR":
            print(f"  Error: {tcfx_merge_info.get('error')}")
            return False
        else:
            print(f"  No TCFX file found (this is OK for testing)")
            return True
        
    except Exception as e:
        print(f"ERROR: Auto-merge failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("TCFX Integration Test Suite (with Dielectric Layers)")
    print("=" * 60)
    
    results = []
    
    # Test 1: Basic parsing
    results.append(("TCFX Parsing", test_tcfx_parsing()))
    
    # Test 2: Merge into stackup JSON
    results.append(("Stackup Merge + Dielectric", test_stackup_merge()))
    
    # Test 3: Auto-discovery
    results.append(("Auto-Discovery", test_auto_merge()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status:8s} | {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
