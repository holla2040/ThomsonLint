from pathlib import Path
#!/usr/bin/env python3
"""Quick test of voltage clearance with schematic data"""

import subprocess
import json

print("Testing voltage clearance with schematic analysis...")
print("=" * 60)

result = subprocess.run([
    "python", "scripts/geometry_helpers.py",
    "TestProject/post_conversion/TestProject-thomson-export-brd.json",
    "--check-voltage-clearance",
    "--json"
], capture_output=True, text=True)

if result.returncode == 0:
    data = json.loads(result.stdout)
    voltage_data = data.get("voltage_spacing", {})
    
    print(f"Status: {voltage_data.get('status')}")
    print(f"Net pairs analyzed: {voltage_data.get('net_pairs_analyzed')}")
    print(f"Violations: {voltage_data.get('violation_count')}")
    print(f"Pass: {voltage_data.get('pass')}")
    if voltage_data.get('error_message'):
        print(f"Message: {voltage_data.get('error_message')}")
    
    if voltage_data.get('violations'):
        print("\nViolations found:")
        for v in voltage_data['violations'][:5]:
            print(f"  {v}")
else:
    print("ERROR:", result.stderr)
    print(result.stdout)
