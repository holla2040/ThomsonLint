# Clearance Calculation Fix - Negative Value Clamping

## Issue: Negative Edge-to-Edge Clearances

### Problem Description

When two traces on different nets physically overlap or intersect (a short circuit), the clearance calculation in `calculate_min_clearance()` would produce **negative clearance values**.

**Mathematical Flow:**
1. `_segment_to_segment_distance()` correctly calculates centerline distance = 0.0 for overlapping segments
2. Edge-to-edge clearance = `dist - (width_a / 2.0) - (width_b / 2.0)`
3. For overlapping traces: `0.0 - 0.005 - 0.005 = -0.010` (negative!)

### Physical Interpretation

**Edge-to-edge clearance** represents the physical distance between conductor boundaries:
- **Positive value:** Traces are separated
- **Zero:** Traces touch or overlap (short circuit)
- **Negative:** Mathematically inconsistent - physically impossible

### Fix Applied

**File:** `scripts/geometry_helpers.py`  
**Line:** 536  

**Before:**
```python
# Adjust for trace widths (edge-to-edge clearance)
edge_clearance = dist - (sa.width / 2.0) - (sb.width / 2.0)
```

**After:**
```python
# Adjust for trace widths (edge-to-edge clearance clamped to 0.0 on overlap)
edge_clearance = max(0.0, dist - (sa.width / 2.0) - (sb.width / 2.0))
```

### Rationale

1. **Physical Consistency:** Clearance cannot be negative in physical reality
2. **Consistent with NPTH Check:** Uses same pattern: `max(0.0, dist_center - pad_radius)`
3. **Clear Semantic:** 0.0 = overlap/short, >0.0 = separated
4. **Downstream Safety:** Prevents math errors in modules expecting non-negative clearances

### Parallel/Collinear Safety (Already Present)

The code already handles parallel and collinear segments safely:

**Division-by-Zero Protection (Line 180):**
```python
if abs(denom) > 1e-12:
    t = ((p3x - p1x) * dy2 - (p3y - p1y) * dx2) / denom
```

**Collinear Fallback (Lines 187-191):**
When segments are collinear, the CCW test returns False, and the function falls back to endpoint-to-segment distance calculations, correctly resolving distance = 0.0.

### Testing

**Test Script:** `test_clearance_clamping.py`

**Validates:**
- No negative clearances returned
- Overlapping traces return 0.0 (not negative)
- Positive clearances still work correctly

**Run:**
```bash
python test_clearance_clamping.py
```

**Expected Output:**
```
✅ PASS: All clearances >= 0.0 (clamping working correctly)

Physical interpretation:
  0.0 = traces overlap or touch (short circuit)
  >0.0 = traces separated by clearance distance
```

### Impact

**Functions Affected:**
- `calculate_min_clearance()` - Direct fix
- `calculate_clearances_for_net()` - Uses calculate_min_clearance
- Any downstream analysis relying on clearance values

**Behavior Change:**
- **Before:** Overlapping traces → negative clearance
- **After:** Overlapping traces → 0.0 clearance
- **Non-overlapping traces:** No change (positive values preserved)

### Related Fixes

This is consistent with other physical clamping in the codebase:
- NPTH clearance: `max(0.0, dist_center - pad_radius)` (line 854)
- Via annular rings: Ring width calculation (line 1189)

All physical distance measurements now follow the same pattern: clamp to 0.0 minimum.
