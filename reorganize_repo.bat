@echo off
echo ============================================================
echo Repository Reorganization Script
echo ============================================================
echo.
echo Creating new directory structure...
echo.

REM Create new directories
mkdir scripts\docs 2>nul
mkdir tests 2>nul

echo   Created: scripts\docs\
echo   Created: tests\
echo.

REM ============================================================
REM Move Documentation to scripts\docs\
REM ============================================================
echo Moving documentation files to scripts\docs\...

move /Y TESTING_SUMMARY.md scripts\docs\ 2>nul
move /Y CLEARANCE_CLAMPING_FIX.md scripts\docs\ 2>nul
move /Y GEOMETRY_HELPERS_API.md scripts\docs\ 2>nul
move /Y IMPEDANCE_FIX_SUMMARY.md scripts\docs\ 2>nul
move /Y SATURN_STATUS.md scripts\docs\ 2>nul
move /Y SATURN_TESTING.md scripts\docs\ 2>nul
move /Y TCFX_INTEGRATION.md scripts\docs\ 2>nul
move /Y CLEANUP_GUIDE.md scripts\docs\ 2>nul

echo   Moved documentation files
echo.

REM ============================================================
REM Move Test Scripts to tests\
REM ============================================================
echo Moving test scripts to tests\...

REM Python test scripts
move /Y test_all_geometry_functions.py tests\ 2>nul
move /Y test_geometry_helpers.py tests\ 2>nul
move /Y test_clearance_clamping.py tests\ 2>nul
move /Y test_edge_clearance_types.py tests\ 2>nul
move /Y test_saturn_with_stackup.py tests\ 2>nul
move /Y test_voltage_check.py tests\ 2>nul
move /Y test_tcfx_integration.py tests\ 2>nul
move /Y test_python.py tests\ 2>nul

REM Batch test scripts
move /Y test_saturn_verification.bat tests\ 2>nul
move /Y test_tcfx_import.bat tests\ 2>nul

REM Legacy batch files (if we're keeping them)
move /Y analyze.bat tests\ 2>nul

echo   Moved test scripts
echo.

REM ============================================================
REM Keep at Root Level (Core Entry Points & Project Docs)
REM ============================================================
echo.
echo Files kept at root level:
echo   - README.md (project overview)
echo   - TODO.md (task tracking)
echo   - CONTRIBUTING.md (contribution guide)
echo   - LICENSE (license file)
echo   - PLAN.md (planning document)
echo   - analyze_board.py (main entry point)
echo   - run_analysis.py (analysis runner)
echo   - validate_json.py (JSON validation)
echo   - cleanup_temp_files.bat (cleanup utility)
echo   - cleanup_old_tcfx.bat (TCFX cleanup)
echo.

REM ============================================================
REM Summary
REM ============================================================
echo ============================================================
echo Reorganization Complete!
echo ============================================================
echo.
echo New structure:
echo   scripts/              - Helper modules (geometry, saturn, etc.)
echo   scripts/docs/         - Documentation for helper functions
echo   tests/                - Test scripts and validation
echo   Root/                 - Entry points and project documentation
echo.
echo Next steps:
echo   1. Review changes: git status
echo   2. Run tests: cd tests ^&^& python test_all_geometry_functions.py
echo   3. Update imports if needed
echo.
pause
