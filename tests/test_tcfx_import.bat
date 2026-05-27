@echo off
REM Quick test to verify TCFX parser can be imported

echo Testing TCFX parser import...
echo.

cd converter\ipc2581_to_json
py -3 -c "from parse_tcfx_stackup import merge_tcfx_if_available; print('✓ Import successful')"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Success! TCFX parser is ready to use.
) else (
    echo.
    echo Error: Import failed. Check syntax errors.
    exit /b 1
)

cd ..\..
