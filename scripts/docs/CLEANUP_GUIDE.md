# Repository Cleanup - Files to Keep

## Essential Test Suites (KEEP)

### Comprehensive Testing
- **`test_all_geometry_functions.py`** - Complete 18-function test suite with detailed debugging
- **`test_geometry_helpers.py`** - Quick validation of all geometry functions
- **`test_clearance_clamping.py`** - Validates negative clearance fix
- **`test_edge_clearance_types.py`** - Validates net-type-aware edge clearances

### Physical-Math Verification
- **`test_saturn_verification.bat`** - Impedance calculation testing (100Ω differential)
- **`test_saturn_with_stackup.py`** - Saturn engine integration tests
- **`test_voltage_check.py`** - Voltage clearance validation
- **`test_tcfx_integration.py`** - Converter integration tests

### Core Functionality
- **`bootstrap.py`** - Project bootstrap
- **`analyze_board.py`** - Board analysis entry point
- **`run_analysis.py`** - Analysis runner
- **`validate_json.py`** - JSON schema validation

### Utilities
- **`analyze.bat`** - Windows wrapper for analysis
- **`cleanup_old_tcfx.bat`** - TCFX cleanup utility
- **`test_tcfx_import.bat`** - TCFX import testing

---

## Temporary Files Removed

### Debug Scripts (removed)
- debug_geometry_helpers.py
- debug_via_structure.py
- debug_outline.py
- debug_via.bat

### Quick Tests (removed)
- quick_*.py (all quick test scripts)
- _quick_*.py (all underscore-prefixed quick scripts)

### Diagnose Scripts (removed)
- _diagnose.py, diagnose_*.py, *_diagnose.py
- diagnose_nets.bat, run_diagnose.bat, etc.

### Extract Scripts (removed)
- extract_nets.py, final_extract.py, simple_extract.py
- manual_extract_nets.py, execute_extract.py
- run_extract.py, run_extract.bat

### Inspect Scripts (removed)
- _inspect_*.py, inspect_board.py
- check_*.py (outline, nets, routes)

### Other Temporary (removed)
- _plan_writer.py, get_keys.py, parse_json.py
- find_voltage_nets.py, show_net_structure.py
- run_it.bat, run_comprehensive_test.bat

---

## Documentation Files (KEEP)

### Testing Documentation
- **`TESTING_SUMMARY.md`** - Complete test results for all 18 functions
- **`CLEARANCE_CLAMPING_FIX.md`** - Negative clearance fix documentation
- **`GEOMETRY_HELPERS_API.md`** - Complete API reference

### Fix Documentation
- **`IMPEDANCE_FIX_SUMMARY.md`** - Impedance calculation fixes
- **`SATURN_STATUS.md`** - Saturn engine status
- **`SATURN_TESTING.md`** - Saturn testing procedures

### General Documentation
- **`README.md`** - Project overview
- **`TODO.md`** - Task tracking
- **`CONTRIBUTING.md`** - Contribution guidelines
- **`LICENSE`** - License file

---

## How to Clean Up

**Run this batch file:**
```bash
cleanup_temp_files.bat
```

This will:
1. Remove all temporary debug/test scripts
2. Keep essential test suites
3. Preserve documentation
4. Show summary of what was kept

---

## Before Check-In Checklist

1. ✅ Run cleanup: `cleanup_temp_files.bat`
2. ✅ Run comprehensive tests: `python test_all_geometry_functions.py`
3. ✅ Verify all tests pass (18/18)
4. ✅ Review changes in git: `git status`, `git diff`
5. ✅ Commit with meaningful message
6. ✅ Push to remote

---

## Git Commit Message Suggestion

```
Fix geometry helper functions - 9 critical issues resolved

- Fixed differential impedance calculation (48Ω → 100Ω)
- Added length-weighted coupling average
- Fixed NPTH unit conversion (6147 → 42 violations)
- Added via annular ring cross-reference (0 → 176 analyzed)
- Fixed board outline extraction
- Added net-type-aware edge clearances (25/50 mils)
- Integrated schematic analysis for power/ground nets
- Fixed negative clearance clamping (overlap → 0.0)
- All 18 geometry functions verified and tested

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```
