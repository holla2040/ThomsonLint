# Quick Test Commands

## Fixed Test Script
The test script has been corrected with proper function names from saturn_engine.py:

```bash
py -3 test_saturn_with_stackup.py
```

**What it tests:**
1. ✓ Stackup completeness (dielectric layers with Dk/Df)
2. ✓ Saturn engine calculations (using correct function names)
3. ✓ geometry_helpers.py integration

---

## Expected Output

```
============================================================
Test 1: Stackup Data Completeness
============================================================
✓ Loaded stackup: TestProject-thomson-export-stack.json
  Total layers: 24
  Physical layers: 15
  Dielectric layers: 5
  Copper layers: 6
✓ Stackup is ready for Saturn calculations

============================================================
Test 2: Saturn Engine Standalone
============================================================
✓ Saturn engine imported successfully
  Test: Microstrip impedance calculation
    Result: Z0 = 57.75 Ω (target: 50Ω)
    Valid: True
  Test: IPC-2152 trace temperature rise
    Result: ΔT = 4.32°C
    Valid: True
  Test: IPC-2221B voltage spacing
    Result: Required clearance = 0.100 mm
    Valid: True
  Test: Via parasitics calculation
    Result: R = 1.274 mΩ, L = 0.74 nH
    Valid: True
✓ All Saturn engine calculations passed

============================================================
Test 3: geometry_helpers.py Integration
============================================================
✓ geometry_helpers imports successful
✓ Stackup loaded successfully
  Layers parsed: 24
✓ All integration functions available and ready

✓ All Saturn verification tests passed!
```

---

## Saturn Engine Function Signatures (Correct)

### Impedance
```python
calculate_microstrip_impedance(w, t, h, dk, unit="mm")
# w: trace width
# t: trace thickness (copper)
# h: dielectric height (to reference plane)
# dk: dielectric constant
# unit: "mm" or "mil"

calculate_stripline_impedance(w, t, h, dk, unit="mm")
calculate_differential_impedance(w, s, h, t, dk, unit="mm")
# s: spacing between traces
```

### Thermal
```python
calculate_temp_rise(current_a, width_mm, thickness_um, is_internal)
# Returns: ThermalResult with temp_rise_c

calculate_max_current(width_mm, thickness_um, temp_rise_c, is_internal)
# Returns: ThermalResult with max_current_a
```

### Voltage Spacing
```python
get_required_clearance(voltage_v, category)
# category: "B1" (internal), "B2" (external uncoated), "B4" (coated)
# Returns: VoltageSpacingResult with required_clearance_mm
```

### Via
```python
calculate_via_parasitics(drill_dia_mm, length_mm, plating_thickness_um)
# Returns: ViaResult with via_resistance_ohms, via_inductance_nh, thermal_resistance_c_per_w
```

---

## Individual Command Tests

### Standalone Saturn Engine
```bash
py -3 scripts\saturn_engine.py
```

### Full Geometry Analysis with Saturn
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --analyze-all --verify-impedance --verify-trace-temp --check-voltage-clearance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
```

### Impedance Only
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-impedance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json
```

### Temperature Only
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-trace-temp --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json
```

### Voltage Clearance Only
```bash
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --check-voltage-clearance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json
```

---

##  ✅ Saturn Engine Works!

Step 5 shows the Saturn engine is working perfectly:
- ✓ Microstrip impedance: 57.75Ω
- ✓ IPC-2152 trace temperature: 4.32°C rise
- ✓ IPC-2221B voltage spacing: 0.1mm required @ 12V
- ✓ Via parasitics: R=1.274mΩ, L=0.74nH

## ⚠️ Integration Issues

The geometry_helpers.py integration (steps 2-4) has errors because the board JSON structure doesn't match what the functions expect:

**Problem:** The functions expect `board["nets"]` to be a **dict** (net_name → net_data), but the TestProject board JSON has `nets` as a **list**.

**Impact:** The `--verify-impedance`, `--verify-trace-temp`, and `--check-voltage-clearance` flags don't work with the current TestProject board JSON structure.

**Solution:** These functions need to be updated to handle the actual board JSON structure from the IPC-2581 converter, OR the converter needs to output nets as a dict instead of a list.

## What Works Right Now

1. **✅ TCFX Integration** - Dielectric layers extracted correctly
2. **✅ Saturn Engine** - All calculations working
3. **✅ Stackup Loading** - Complete physical data available
4. **⚠️ Integration Layer** - Needs board JSON structure fixes

## Recommended Next Steps

1. **For immediate use:** Call Saturn engine functions directly in Python:
   ```python
   from scripts.saturn_engine import calculate_microstrip_impedance
   result = calculate_microstrip_impedance(w=0.254, h=0.2, t=0.035, dk=4.5, unit="mm")
   print(f"Z0 = {result.z0_ohms:.2f} Ω")
   ```

2. **For full integration:** Update geometry_helpers.py functions to handle list-based nets structure

3. **For testing with real projects:** The integration may work with projects that have a different board JSON structure

---

## Next Steps After Successful Test

1. **Run on real project:**
   ```bash
   py -3 converter\ipc2581_to_json\thomson_bundle_converter.py <your_project_path>
   py -3 scripts\geometry_helpers.py exports\<project>-brd.json --verify-impedance --verify-trace-temp --stackup exports\<project>-stack.json
   ```

2. **Review violations:**
   - Impedance mismatches → DFM_IMPEDANCE_001
   - Temperature violations → PWR_THERMAL_001
   - Clearance violations → EMC_CLEARANCE_001

3. **Integrate into findings JSON:**
   - Use output for LLM review workflow
   - Add to `exports/<project>-findings.json`
