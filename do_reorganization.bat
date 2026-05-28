@echo off
echo ============================================================
echo ThomsonLint Repository Reorganization - Master Script
echo ============================================================
echo.
echo This script will:
echo   1. Clean up temporary files
echo   2. Reorganize directory structure
echo   3. Update test imports
echo   4. Verify tests still work
echo.
echo Press Ctrl+C to cancel, or
pause

REM Step 1: Cleanup temporary files
echo.
echo ============================================================
echo Step 1: Cleaning up temporary files...
echo ============================================================
call cleanup_temp_files.bat

REM Step 2: Reorganize directory structure
echo.
echo ============================================================
echo Step 2: Reorganizing directory structure...
echo ============================================================
call reorganize_repo.bat

REM Step 3: Update test imports
echo.
echo ============================================================
echo Step 3: Updating test imports...
echo ============================================================
python update_test_imports.py
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to update test imports
    pause
    exit /b 1
)

REM Step 4: Verify tests work
echo.
echo ============================================================
echo Step 4: Verifying tests work...
echo ============================================================
echo Running comprehensive test suite...
echo.
python tests\test_all_geometry_functions.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo WARNING: Tests failed. Please review the output above.
    echo.
) else (
    echo.
    echo SUCCESS: All tests passed!
    echo.
)

REM Summary
echo.
echo ============================================================
echo Reorganization Complete!
echo ============================================================
echo.
echo New structure:
echo   scripts/docs/  - Documentation
echo   tests/         - Test scripts
echo   Root/          - Entry points
echo.
echo Next steps:
echo   1. Review changes: git status
echo   2. Review diffs: git diff
echo   3. Run specific test: python tests\test_geometry_helpers.py
echo   4. Commit when ready
echo.
echo See REORGANIZATION_GUIDE.md for details.
echo.
pause
