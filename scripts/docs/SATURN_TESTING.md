# Saturn Physical Verification Testing Guide

## Quick Start

After running the converter with TCFX merge, you can test the Saturn physical-math verification:

### Option 1: Comprehensive Python Test
```bash
py -3 test_saturn_with_stackup.py
```

**What it tests:**
1. ✓ Stackup has complete physical data (dielectric layers, Dk, Df)
2. ✓ Saturn engine calculations work (impedance, thermal, voltage spacing, via parasitics)
3. ✓ Integration with geometry_helpers.py is functional

### Option 2: Batch Script (Full Workflow)
```bash
test_saturn_verification.bat
```

**What it does:**
1. Runs converter to merge TCFX stackup
2. Tests impedance verification
3. Tests trace temperature verification
4. Tests voltage clearance checks
5. Tests Saturn engine standalone

### Option 3: Individual Tests

#### Test Impedance Verification
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-impedance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
```

**What it checks:**
- Differential pairs against 50Ω, 85Ω, 90Ω, 100Ω targets
- Uses Wheeler approximation with Dk from stackup
- Reports violations with actual Z0 vs target

#### Test Trace Temperature Rise
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-trace-temp --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
```

**What it checks:**
- IPC-2152 temperature rise calculations
- Power net traces against 10°C rise limit
- Uses copper thickness from stackup

#### Test Voltage Clearance
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --check-voltage-clearance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
```

**What it checks:**
- IPC-2221B minimum spacing requirements
- Extracts voltage from net names (VCC_12V, 3V3, 5V, etc.)
- Category B2 (external, uncoated) by default

#### Test Saturn Engine Directly
```bash
py -3 scripts\saturn_engine.py
```

**What it outputs:**
- Sample microstrip impedance (50Ω target)
- Sample IPC-2152 temperature rise
- Sample IPC-2221B voltage spacing (12V)
- Sample via parasitics (R, L, thermal resistance)

## Expected Output Examples

### Successful Impedance Check
```json
{
  "status": "SUCCESS",
  "violations": [
    {
      "net_pair": ["DDR_CK_P", "DDR_CK_N"],
      "target_impedance": 100,
      "calculated_impedance": 95.3,
      "deviation_percent": -4.7,
      "severity": "WARNING"
    }
  ]
}
```

### Successful Temperature Check
```json
{
  "status": "SUCCESS",
  "violations": [
    {
      "net": "VCC_5V",
      "width_mm": 0.254,
      "current_a": 2.0,
      "temp_rise_c": 15.3,
      "limit_c": 10.0,
      "severity": "CRITICAL"
    }
  ]
}
```

### Successful Voltage Spacing Check
```json
{
  "status": "SUCCESS",
  "violations": [
    {
      "net1": "VCC_12V",
      "net2": "GND",
      "voltage_v": 12.0,
      "actual_clearance_mm": 0.08,
      "required_clearance_mm": 0.1,
      "severity": "CRITICAL"
    }
  ]
}
```

## What Data is Required?

### For Impedance Verification
- ✓ Dielectric layers with Dk (dielectric constant)
- ✓ Dielectric thickness (height above reference plane)
- ✓ Copper thickness
- ✓ Trace width from board geometry

### For Temperature Verification
- ✓ Copper thickness (from stackup)
- ✓ Trace width (from board geometry)
- ✓ Current rating (estimated or from power nets)

### For Voltage Spacing
- ✓ Net names with voltage encoding (VCC_12V, 3V3, etc.)
- ✓ Spacing between net segments (from board geometry)

## Troubleshooting

### "STACKUP_DATA_REQUIRED" Error
**Cause:** Stackup JSON missing or incomplete

**Fix:**
1. Run converter to get fresh stackup:
   ```bash
   py -3 converter\ipc2581_to_json\thomson_bundle_converter.py TestProject
   ```
2. Verify TCFX file was found and merged:
   ```bash
   py -3 test_tcfx_integration.py
   ```

### No Dielectric Layers in Stackup
**Cause:** TCFX merge didn't happen or TCFX file missing

**Fix:**
1. Check for TCFX file:
   ```bash
   dir TestProject\*.tcfx /s
   ```
2. Verify parser extracts dielectrics:
   ```bash
   py -3 test_tcfx_integration.py
   ```
   Should show "Dielectric layers: X" in output

### Impedance Calculations Return "valid: false"
**Cause:** Missing Dk or thickness in dielectric layers

**Fix:**
1. Check stackup quality metadata:
   ```bash
   py -3 -c "import json; s=json.load(open('TestProject/post_conversion/TestProject-thomson-export-stack.json')); print(s['stackup_data_quality'])"
   ```
2. Should show `"dielectric_material_available": true`

### No Violations Found (but expected some)
**Cause:** Test board may be well-designed

**Try:**
- Use a real project board with known issues
- Check that traces/nets exist in board JSON
- Verify geometry extraction worked:
  ```bash
  py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --analyze-all --json
  ```

## Integration with Review Workflow

These Saturn checks are integrated into Phase 9 (Geometry Analysis):

```bash
# Full geometry analysis with physical-math verification
py -3 scripts\geometry_helpers.py exports\<project>-thomson-export-brd.json \
  --analyze-all \
  --verify-impedance \
  --verify-trace-temp \
  --check-voltage-clearance \
  --stackup exports\<project>-thomson-export-stack.json \
  --json > exports\<project>-geometry-analysis.json
```

The output JSON is consumed by the LLM reviewer to:
- Flag impedance mismatches (DFM_IMPEDANCE_001)
- Flag thermal violations (PWR_THERMAL_001)
- Flag voltage clearance violations (EMC_CLEARANCE_001)

## Files Created

- `test_saturn_verification.bat` - Windows batch script for full test
- `test_saturn_with_stackup.py` - Python test suite with detailed output
- `SATURN_TESTING.md` - This guide

## Related Documentation

- `TCFX_INTEGRATION.md` - How TCFX stackup merge works
- `scripts/saturn_engine.py` - Mathematical calculation engine
- `scripts/geometry_helpers.py` - Integration layer
- `PLAN.md` Phase 9 - Geometry analysis requirements
- `OPENHANDS_REVIEW.md` Workflow 8 - Physical-math verification steps
