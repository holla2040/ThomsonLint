@echo off
echo ============================================================
echo Git Commit Preparation - Clean Up Duplicates
echo ============================================================
echo.

REM Remove duplicate/temporary test files
echo Removing duplicates and temp files...

del /Q tests\test_all_geometry_functions_updated.py 2>nul
del /Q tests\test_saturn_verification.bat.txt 2>nul
del /Q update_test_imports.py 2>nul

REM Note: parse_tcfx_stackup.py should only be in converter, not scripts
if exist scripts\parse_tcfx_stackup.py (
    echo   Removing duplicate: scripts\parse_tcfx_stackup.py
    del /Q scripts\parse_tcfx_stackup.py
)

echo.
echo ============================================================
echo Ready to commit!
echo ============================================================
echo.
echo Next steps:
echo   1. Stage all changes: git add -A
echo   2. Review what will be committed: git status
echo   3. Commit with message below
echo.
pause
