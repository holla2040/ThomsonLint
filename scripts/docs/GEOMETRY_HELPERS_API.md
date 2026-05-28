# ThomsonLint Geometry Helper Functions - Complete API Reference

This document catalogs all public API functions available in `geometry_helpers.py` for AI-assisted hardware design review.

---

## 1. Board Data Loading

### `load_board_json(path: Path | str) -> dict[str, Any]`
**Purpose:** Load and parse board JSON file  
**Input:** Path to board JSON file  
**Output:** Board data dictionary  
**Test:** Verify it loads TestProject board without errors

---

## 2. Trace Width & Net Analysis

### `get_net_segments(board: dict, net_name: str) -> NetSegmentStats`
**Purpose:** Extract all trace segments for a specific net with width statistics  
**Returns:** 
- `segments`: List of Segment objects
- `total_length`: Total trace length
- `min_width`, `max_width`, `avg_width`, `nominal_width`: Width statistics
- `layers`: Set of layers the net traverses
- `width_histogram`: Width distribution

**Test Case:**
```python
stats = get_net_segments(board, "3V3")
assert stats.total_length > 0
assert stats.min_width is not None
assert len(stats.segments) > 0
```

### `get_all_net_segments(board: dict) -> dict[str, NetSegmentStats]`
**Purpose:** Extract segment statistics for all nets in the board  
**Returns:** Dictionary mapping net name → NetSegmentStats  
**Test:** Verify all nets in the board are found

---

## 3. Net-to-Net Clearance Analysis

### `calculate_min_clearance(board: dict, net_a: str, net_b: str) -> ClearanceResult`
**Purpose:** Calculate minimum edge-to-edge clearance between two nets  
**Returns:**
- `min_clearance`: Minimum distance (mm or inches)
- `clearance_location`: (x, y) coordinates of closest point
- `clearance_layer`: Layer where minimum occurs
- `segments_compared`: Number of segment pairs evaluated

**Test Case:**
```python
result = calculate_min_clearance(board, "3V3", "GND")
assert result.min_clearance is not None
assert result.clearance_layer is not None
```

### `calculate_clearances_for_net(board: dict, target_net: str, critical_nets: list[str] | None) -> list[ClearanceResult]`
**Purpose:** Calculate clearances between target net and multiple other nets  
**Returns:** Sorted list of ClearanceResult (ascending by clearance)  
**Test:** Verify results are sorted smallest clearance first

---

## 4. Differential Pair Analysis

### `analyze_differential_pair(board: dict, net_positive: str, net_negative: str, coupling_threshold: float | None = None) -> DifferentialPairAnalysis`
**Purpose:** Analyze coupling characteristics of a differential pair  
**Key Features:**
- **Length-weighted average** coupling distance (prevents breakout skew)
- Unit-aware coupling threshold (auto-detects INCH vs MM)

**Returns:**
- `avg_coupling_distance`: **Length-weighted** average gap (physically correct)
- `min_coupling_distance`, `max_coupling_distance`: Gap range
- `length_mismatch`: Absolute length difference
- `length_mismatch_percent`: Percentage mismatch
- `coupled_sections`: List of tightly coupled segments
- `uncoupled_sections`: List of breakout/flared sections
- `coupling_quality`: "good", "marginal", "poor", "insufficient_data"

**Test Case:**
```python
analysis = analyze_differential_pair(board, "CLK_P", "CLK_N")
assert analysis.avg_coupling_distance is not None
assert analysis.coupling_quality in ["good", "marginal", "poor"]
# Verify length-weighted average is being used
assert len(analysis.coupled_sections) > 0
```

### `analyze_all_differential_pairs(board: dict, coupling_threshold: float | None = None) -> list[DifferentialPairAnalysis]`
**Purpose:** Auto-detect and analyze all differential pairs  
**Detection Patterns:** `_P/_N`, `+/-`, `_DP/_DN`, `D+/D-`  
**Test:** Verify all expected diff pairs are detected

---

## 5. NPTH (Non-Plated Through Hole) Clearance

### `check_npth_clearance(board: dict, keepout_radius: float = 4.0) -> NPTHClearanceResult`
**Purpose:** Check copper features maintain clearance from NPTH mounting holes  
**Per:** Appendix K.6 (4mm copper keepout prevents uncontrolled chassis ground)  
**Returns:**
- `npth_count`: Total NPTH holes found
- `analyzed_count`: Holes successfully analyzed
- `violations`: List of NPTHClearanceViolation objects
- `clean_holes`: List of compliant hole IDs
- `pass_status`: Boolean

**Test Case:**
```python
result = check_npth_clearance(board, keepout_radius=4.0)
assert result.npth_count >= 0
assert result.pass_status is not None
```

---

## 6. Ampacity & Current Capacity

### `calculate_trace_ampacity(width_mm: float, thickness_oz: float = 1.0, temp_rise_c: float = 10.0, is_internal: bool = False) -> float`
**Purpose:** Calculate trace current capacity using IPC-2221 formula  
**Returns:** Maximum current (Amperes)  
**Test:** Verify 10 mil trace @ 1oz = ~0.5A for 10°C rise

### `verify_trace_ampacity(board: dict, net_name: str, required_current_a: float, copper_oz: float = 1.0, temp_rise_c: float = 10.0) -> dict`
**Purpose:** Verify net can carry required current  
**Returns:** Dictionary with violations if capacity insufficient  
**Test:** Check power nets have adequate width

---

## 7. Via Annular Ring (DFM)

### `check_via_annular_rings(board: dict, min_ring_mm: float = 0.127) -> AnnularRingResult`
**Purpose:** Check vias have sufficient annular ring (pad - drill) / 2  
**Rule:** DFM_VIA_001, DFM_VIA_003, DFM_VIA_004  
**Default:** 0.127mm (5 mils) minimum  
**Returns:**
- `via_count`: Total vias analyzed
- `violations`: List of AnnularRingViolation objects
- `pass_status`: Boolean

**Test Case:**
```python
result = check_via_annular_rings(board, min_ring_mm=0.127)
assert result.via_count > 0
for v in result.violations:
    assert v.annular_ring < 0.127
```

---

## 8. Acid Trap Detection (DFM)

### `detect_acid_traps(board: dict, angle_threshold_deg: float = 70.0) -> AcidTrapResult`
**Purpose:** Detect acute angle trace bends that trap etchant  
**Rule:** DFM_ACID_001  
**Default:** 70° threshold (angles ≤ 70° flagged)  
**Returns:**
- `routes_analyzed`: Total routes checked
- `vertices_analyzed`: Total bend vertices checked
- `traps`: List of AcidTrap objects with angle, location, severity

**Test Case:**
```python
result = detect_acid_traps(board, angle_threshold_deg=70.0)
assert result.routes_analyzed > 0
for trap in result.traps:
    assert trap.angle_deg <= 70.0
```

---

## 9. Board Edge Clearance (DFM)

### `check_board_edge_clearance(board: dict, min_clearance_mm: float = 0.5) -> EdgeClearanceResult`
**Purpose:** Check copper features maintain clearance from board edge  
**Rule:** DFM_EDGE_001, DFM_PANEL_001  
**Default:** 0.5mm (20 mils) minimum  
**Returns:**
- `outline_found`: Boolean (can only check if outline exists)
- `outline_segment_count`: Number of board edge segments
- `violations`: List of EdgeClearanceViolation objects

**Test Case:**
```python
result = check_board_edge_clearance(board, min_clearance_mm=0.5)
if result.outline_found:
    assert result.outline_segment_count > 0
```

---

## 10. Copper Balance Estimation (DFM)

### `estimate_copper_balance(board: dict, imbalance_threshold_pct: float = 25.0) -> CopperBalanceResult`
**Purpose:** Estimate copper area per layer and check for imbalance  
**Rule:** DFM_COPPER_001  
**Default:** 25% imbalance threshold  
**Returns:**
- `layer_areas`: List of LayerCopperArea objects (route, pad, polygon areas per layer)
- `warnings`: List of CopperBalanceWarning for symmetric layer pairs
- `layer_pairs_checked`: Number of symmetric pairs evaluated

**Test Case:**
```python
result = estimate_copper_balance(board, imbalance_threshold_pct=25.0)
assert len(result.layer_areas) > 0
for warning in result.warnings:
    assert warning.imbalance_percent > 25.0
```

---

## 11. Physical-Math Verification (Saturn Engine Integration)

### `load_stackup_json(stackup_path: str) -> dict[str, StackupLayer]`
**Purpose:** Load and parse stackup JSON with material properties  
**Returns:** Dictionary mapping layer name → StackupLayer  
**Units:** Auto-converts INCH/MIL/MM to mm  
**Test:** Verify stackup layers have dielectric properties

---

### `verify_impedance(board: dict, stackup_path: str | None, target_ohms: float = 100.0, tolerance_percent: float = 10.0) -> ImpedanceVerificationResult`
**Purpose:** Verify controlled impedance for differential pairs  
**Rule:** HS_MAT_001  
**Method:** 
- Uses Wheeler/Wadell transmission line equations
- **Topology-specific coupling:** Microstrip vs Stripline formulas
- **Length-weighted spacing:** Uses physically correct average from `analyze_differential_pair`
- Adjacent dielectric layer lookup (not copper layer properties)

**Returns:**
- `status`: "PASS", "FAIL", "ERROR", "STACKUP_DATA_REQUIRED"
- `nets_analyzed`: Number of differential pairs checked
- `violations`: List with calculated Z0_single, Z_diff, deviation

**Test Case:**
```python
result = verify_impedance(board, stackup_path, target_ohms=100.0, tolerance_percent=10.0)
assert result.stackup_available == True
assert result.nets_analyzed > 0
for v in result.violations:
    assert v["calculated_zdiff_ohms"] is not None
    assert v["topology"] in ["differential_microstrip", "differential_stripline"]
```

**Critical Implementation Details:**
- ✅ Uses `se_result.dielectric_height_mm` (correct for both microstrip and stripline)
- ✅ Uses `board_units` for spacing conversion (not route width units)
- ✅ Passes `topology` to coupling formula
- ✅ Looks up adjacent DIELECTRIC layer (not copper layer)

---

### `verify_trace_temperature(board: dict, stackup_path: str | None, current_a: float = 1.0, max_temp_rise_c: float = 10.0) -> ThermalVerificationResult`
**Purpose:** Verify trace current capacity and temperature rise  
**Rule:** PWR_TRACE_002  
**Method:** IPC-2152 thermal model  
**Power Net Detection:** 
- **Comprehensive regex:** Matches VCC, VDD, VBUS, VSYS, VBAT, VPP, VREF, AVDD, DVDD
- **Numeric rails:** 3V3, 5V, 12V, +12V, 1V8, 3.3V, etc.

**Returns:**
- `nets_analyzed`: Number of power nets checked
- `violations`: List with calculated temp rise vs. limit

**Test Case:**
```python
result = verify_trace_temperature(board, stackup_path, current_a=1.0, max_temp_rise_c=10.0)
assert result.nets_analyzed > 0  # Should find many power nets
for v in result.violations:
    assert v["calculated_temp_rise_c"] > 10.0
```

---

### `check_voltage_clearance(board: dict, schematic_path: str | None = None, default_category: str = "B2") -> VoltageSpacingResult`
**Purpose:** Verify electrical clearances per IPC-2221B Table 6-1  
**Rule:** DFM_TRACE_004  
**Method:** 
- Parse voltage from net names (V12P0, 3V3, 3.3V, etc.)
- Calculate required spacing based on voltage difference
- Compare to actual clearance

**Returns:**
- `net_pairs_analyzed`: Number of voltage pairs checked
- `violations`: List with voltage_diff, required vs. actual clearance

**Test Case:**
```python
result = check_voltage_clearance(board, schematic_path, default_category="B2")
if result.status == "PASS" or result.status == "FAIL":
    assert result.net_pairs_analyzed > 0
```

---

## Testing Checklist

Use this systematic checklist to verify each function:

### Category 1: Basic Geometry (No Saturn Engine)
- [ ] `load_board_json` - Loads without errors
- [ ] `get_net_segments` - Returns valid segment stats
- [ ] `get_all_net_segments` - Finds all nets
- [ ] `calculate_min_clearance` - Returns reasonable clearance values
- [ ] `calculate_clearances_for_net` - Results are sorted
- [ ] `analyze_differential_pair` - Length-weighted average works correctly
- [ ] `analyze_all_differential_pairs` - Auto-detects all pairs

### Category 2: DFM Checks (No Saturn Engine)
- [ ] `check_npth_clearance` - Finds NPTH holes, checks clearances
- [ ] `check_via_annular_rings` - Finds vias, validates ring width
- [ ] `detect_acid_traps` - Detects acute angle bends
- [ ] `check_board_edge_clearance` - Validates edge spacing
- [ ] `estimate_copper_balance` - Calculates layer areas
- [ ] `calculate_trace_ampacity` - Returns reasonable current values
- [ ] `verify_trace_ampacity` - Checks net capacity

### Category 3: Physical-Math Verification (Requires Saturn Engine + Stackup)
- [ ] `load_stackup_json` - Parses stackup, converts units correctly
- [ ] `verify_impedance` - Calculates Z0_single ~50Ω, Z_diff ~100Ω
  - [ ] Uses topology-specific formulas (microstrip vs stripline)
  - [ ] Uses length-weighted coupling distance
  - [ ] Looks up adjacent dielectric layer
  - [ ] Uses correct height for each topology
- [ ] `verify_trace_temperature` - Finds power nets (3V3, 5V, etc.)
  - [ ] Comprehensive regex catches all power rail patterns
  - [ ] Calculates reasonable temp rise values
- [ ] `check_voltage_clearance` - Parses voltages, checks spacing
  - [ ] Handles dot-decimal formats (3.3V, 1.8V)

---

## Known Issues & Fixes Applied

1. ✅ **Length-weighted coupling average** - Prevents breakout skew (lines 737-747)
2. ✅ **Comprehensive power net regex** - Catches 3V3, 5V, etc. (lines 2101-2107)
3. ✅ **Topology-specific coupling** - Microstrip vs stripline formulas
4. ✅ **Adjacent dielectric lookup** - Not copper layer properties
5. ✅ **Correct height for coupling** - Uses `se_result.dielectric_height_mm`
6. ✅ **Unit-aware coupling threshold** - Auto-detects INCH vs MM
7. ✅ **Board units for spacing** - Not route width units

---

## Test Script Examples

### Basic Test:
```python
from geometry_helpers import *

board = load_board_json("TestProject/post_conversion/TestProject-thomson-export-brd.json")
stackup = "TestProject/post_conversion/TestProject-thomson-export-stack.json"

# Test differential pairs
pairs = analyze_all_differential_pairs(board)
print(f"Found {len(pairs)} differential pairs")

# Test impedance
result = verify_impedance(board, stackup, target_ohms=100.0)
print(f"Impedance: {result.status}, {result.nets_analyzed} nets analyzed")

# Test thermal
result = verify_trace_temperature(board, stackup)
print(f"Thermal: {result.status}, {result.nets_analyzed} nets analyzed")
```

### Systematic Function Test:
```python
# Test each category systematically
def test_category_1():
    board = load_board_json("...")
    stats = get_net_segments(board, "3V3")
    assert stats.total_length > 0
    # ... continue for all Category 1 functions

def test_category_2():
    board = load_board_json("...")
    result = check_npth_clearance(board)
    assert result.npth_count >= 0
    # ... continue for all Category 2 functions

def test_category_3():
    board = load_board_json("...")
    stackup = "..."
    result = verify_impedance(board, stackup, target_ohms=100.0)
    assert result.nets_analyzed > 0
    # ... continue for all Category 3 functions
```
