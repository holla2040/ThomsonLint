# Repository Reorganization Guide

## New Directory Structure

```
ThomsonLint/
├── scripts/                     # Helper modules and utilities
│   ├── docs/                    # Documentation for helper functions
│   │   ├── TESTING_SUMMARY.md
│   │   ├── CLEARANCE_CLAMPING_FIX.md
│   │   ├── GEOMETRY_HELPERS_API.md
│   │   ├── IMPEDANCE_FIX_SUMMARY.md
│   │   ├── SATURN_STATUS.md
│   │   ├── SATURN_TESTING.md
│   │   ├── TCFX_INTEGRATION.md
│   │   └── CLEANUP_GUIDE.md
│   ├── geometry_helpers.py      # Geometry analysis functions
│   ├── saturn_engine.py         # Impedance calculations
│   ├── stackup_helpers.py       # Stackup utilities
│   ├── schematic_helpers.py     # Schematic analysis
│   └── ... (other helpers)
├── tests/                       # Test scripts and validation
│   ├── test_all_geometry_functions.py
│   ├── test_geometry_helpers.py
│   ├── test_clearance_clamping.py
│   ├── test_edge_clearance_types.py
│   ├── test_saturn_with_stackup.py
│   ├── test_voltage_check.py
│   ├── test_tcfx_integration.py
│   ├── test_saturn_verification.bat
│   └── test_tcfx_import.bat
├── README.md                    # Project overview
├── TODO.md                      # Task tracking
├── CONTRIBUTING.md              # Contribution guidelines
├── LICENSE                      # License file
├── bootstrap.py                 # Project bootstrap
├── analyze_board.py             # Main entry point
├── run_analysis.py              # Analysis runner
└── validate_json.py             # JSON validation

```

## Migration Steps

### Step 1: Run Cleanup (Remove Temporary Files)
```bash
cleanup_temp_files.bat
```

### Step 2: Run Reorganization (Move Files)
```bash
reorganize_repo.bat
```

This will:
- Create `scripts/docs/` directory
- Create `tests/` directory
- Move documentation to `scripts/docs/`
- Move test scripts to `tests/`
- Keep core entry points at root

### Step 3: Update Test Imports
```bash
python update_test_imports.py
```

This will automatically update all test files to use correct paths:
- `sys.path.insert(0, "scripts")` → `sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))`
- `"TestProject/..."` → `str(Path(__file__).parent.parent / "TestProject/...")`

### Step 4: Verify Tests Work
```bash
# From project root
python tests/test_all_geometry_functions.py

# Or from tests directory
cd tests
python test_all_geometry_functions.py
```

## Files Moved

### Documentation → scripts/docs/
- TESTING_SUMMARY.md
- CLEARANCE_CLAMPING_FIX.md
- GEOMETRY_HELPERS_API.md
- IMPEDANCE_FIX_SUMMARY.md
- SATURN_STATUS.md
- SATURN_TESTING.md
- TCFX_INTEGRATION.md
- CLEANUP_GUIDE.md

### Test Scripts → tests/
- test_all_geometry_functions.py
- test_geometry_helpers.py
- test_clearance_clamping.py
- test_edge_clearance_types.py
- test_saturn_with_stackup.py
- test_voltage_check.py
- test_tcfx_integration.py
- test_python.py
- test_saturn_verification.bat
- test_tcfx_import.bat
- analyze.bat (if keeping)

### Kept at Root
- README.md, TODO.md, CONTRIBUTING.md, LICENSE, PLAN.md
- bootstrap.py, analyze_board.py, run_analysis.py, validate_json.py
- Cleanup utilities: cleanup_temp_files.bat, cleanup_old_tcfx.bat

## Import Pattern Updates

### Before (from root)
```python
import sys
sys.path.insert(0, "scripts")
from geometry_helpers import load_board_json

board = load_board_json("TestProject/post_conversion/TestProject-thomson-export-brd.json")
```

### After (from tests/)
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from geometry_helpers import load_board_json

BOARD_PATH = str(Path(__file__).parent.parent / "TestProject/post_conversion/TestProject-thomson-export-brd.json")
board = load_board_json(BOARD_PATH)
```

## Running Tests After Reorganization

### From Project Root
```bash
# Run all tests
python tests/test_all_geometry_functions.py
python tests/test_geometry_helpers.py
python tests/test_clearance_clamping.py

# Run batch tests
tests\test_saturn_verification.bat
```

### From Tests Directory
```bash
cd tests

# Run all tests
python test_all_geometry_functions.py
python test_geometry_helpers.py
python test_clearance_clamping.py

# Run batch tests
test_saturn_verification.bat
```

## Git Commit After Reorganization

```bash
# Stage changes
git add scripts/docs/
git add tests/
git add reorganize_repo.bat update_test_imports.py REORGANIZATION_GUIDE.md

# Stage moves (git will detect renames)
git add -A

# Commit
git commit -m "Reorganize repository structure

- Move documentation to scripts/docs/
- Move test scripts to tests/
- Update test imports for new structure
- Keep core entry points at root level

Structure:
  scripts/       - Helper modules
  scripts/docs/  - Helper documentation
  tests/         - Test scripts
  Root/          - Entry points and project docs
"
```

## Benefits of New Structure

1. ✅ **Clear Separation**: Helper code, tests, and docs in separate directories
2. ✅ **Easy Navigation**: Developers can find files quickly
3. ✅ **Scalable**: Easy to add new tests or documentation
4. ✅ **Standard Layout**: Follows Python project conventions
5. ✅ **IDE Friendly**: Most IDEs recognize tests/ as test directory
6. ✅ **Clean Root**: Only essential entry points at top level

## Troubleshooting

### "Module not found" errors
- Check: Are you running from project root or tests/ directory?
- Fix: Use Path-based imports (see update_test_imports.py)

### "File not found" errors
- Check: Are TestProject paths relative to project root?
- Fix: Use `Path(__file__).parent.parent / "TestProject/..."`

### Tests fail after moving
- Check: Did you run update_test_imports.py?
- Fix: Run `python update_test_imports.py` to fix imports

## Verification Checklist

- [ ] Run cleanup_temp_files.bat
- [ ] Run reorganize_repo.bat
- [ ] Run update_test_imports.py
- [ ] Test: `python tests/test_all_geometry_functions.py`
- [ ] Verify: All 18 functions pass
- [ ] Review: `git status` shows moves correctly
- [ ] Commit changes with descriptive message
