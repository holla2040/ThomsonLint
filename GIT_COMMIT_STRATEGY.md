# Git Commit Strategy

## Step 1: Clean Up Duplicates

Run this to remove temporary/duplicate files:
```bash
prepare_commit.bat
```

This removes:
- `tests/test_all_geometry_functions_updated.py` (duplicate)
- `tests/test_saturn_verification.bat.txt` (backup file)
- `update_test_imports.py` (one-time migration script)
- `scripts/parse_tcfx_stackup.py` (duplicate - should only be in converter/)

## Step 2: Stage Changes

```bash
git add -A
```

## Step 3: Review What Will Be Committed

```bash
git status
```

Expected changes:
- ✅ Modified: `scripts/geometry_helpers.py` (9 critical fixes)
- ✅ Modified: `converter/ipc2581_to_json/thomson_bundle_converter.py` (outline extraction)
- ✅ Deleted: Temporary debug scripts (~15 files)
- ✅ New: `scripts/docs/` (8 documentation files)
- ✅ New: `tests/` (11 test files)
- ✅ New: Helper scripts (`scripts/saturn_engine.py`, `scripts/bom_helpers.py`, etc.)
- ✅ New: Reorganization scripts (`do_reorganization.bat`, etc.)

## Step 4: Commit with This Message

```bash
git commit -m "Major refactor: Fix geometry helpers and reorganize repo

Geometry Helper Fixes (9 critical issues):
- Fixed differential impedance (48Ω → 100Ω differential)
  * Length-weighted coupling average
  * Topology-specific formulas (microstrip/stripline)
  * Adjacent dielectric layer lookup
  * Correct height for each topology
- Fixed NPTH clearance unit conversion (6147 → 42 violations)
- Added via annular ring cross-reference (0 → 176 vias analyzed)
- Fixed board outline extraction (flat point list → segments)
- Added net-type-aware edge clearances (GND=25mil, PWR/SIG=50mil)
- Integrated schematic analysis for power/ground net classification
- Fixed negative clearance clamping (overlap → 0.0)

Repository Reorganization:
- Created scripts/docs/ for helper documentation
- Created tests/ for all test scripts
- Removed ~40 temporary debug/diagnostic files
- Clean root with only entry points

New Helper Modules:
- scripts/saturn_engine.py - Impedance calculations (Wheeler/Wadell)
- scripts/bom_helpers.py - BOM analysis utilities
- scripts/schematic_helpers.py - Schematic analysis utilities
- scripts/stackup_helpers.py - Stackup validation
- scripts/cross_check_helpers.py - Cross-source verification

Testing:
- All 18 geometry functions verified and tested
- Comprehensive test suite in tests/
- Documentation in scripts/docs/

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
"
```

## Step 5: Push

```bash
git push
```

---

## If You Want to Split Into Multiple Commits

### Commit 1: Geometry Fixes
```bash
git add scripts/geometry_helpers.py
git add scripts/saturn_engine.py
git add scripts/docs/IMPEDANCE_FIX_SUMMARY.md
git add scripts/docs/CLEARANCE_CLAMPING_FIX.md
git add scripts/docs/GEOMETRY_HELPERS_API.md
git commit -m "Fix geometry helper functions - 9 critical issues

- Differential impedance: 48Ω → 100Ω (8 fixes)
- NPTH clearance: 6147 → 42 violations (unit conversion)
- Via annular rings: 0 → 176 analyzed (coordinate cross-ref)
- Edge clearances: Net-type-aware (25/50 mil)
- Negative clearance clamping: overlap → 0.0
"
```

### Commit 2: New Helpers
```bash
git add scripts/bom_helpers.py
git add scripts/schematic_helpers.py
git add scripts/stackup_helpers.py
git add scripts/cross_check_helpers.py
git commit -m "Add new helper modules for comprehensive analysis

- bom_helpers.py - BOM component analysis
- schematic_helpers.py - Schematic graph analysis
- stackup_helpers.py - Stackup validation
- cross_check_helpers.py - Cross-source verification
"
```

### Commit 3: Reorganization
```bash
git add tests/
git add scripts/docs/
git add do_reorganization.bat
git add reorganize_repo.bat
git add cleanup_temp_files.bat
git add REORGANIZATION_*.md
git commit -m "Reorganize repository structure

- Created tests/ directory for all test scripts
- Created scripts/docs/ for helper documentation
- Removed ~40 temporary debug files
- Clean root with only entry points
"
```

### Commit 4: Cleanup
```bash
git add -u  # Stage all deletions
git commit -m "Remove temporary debug and diagnostic files

Removed ~40 temporary files:
- debug_*.py, quick_*.py (one-off debugging)
- diagnose_*.py, extract_*.py (temporary analysis)
- Old reports and workarounds
"
```

---

## Quick Option (Single Commit)

```bash
prepare_commit.bat
git add -A
git commit -F- <<EOF
Major refactor: Fix geometry helpers and reorganize repo

Geometry Helper Fixes (9 critical issues):
- Differential impedance: 48Ω → 100Ω
- NPTH clearance: 6147 → 42 violations
- Via annular rings: 0 → 176 analyzed
- Edge clearances: Net-type-aware (25/50 mil)
- Negative clearance clamping

Repository Reorganization:
- scripts/docs/ for documentation
- tests/ for test scripts
- Removed ~40 temp files

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
EOF
git push
```
