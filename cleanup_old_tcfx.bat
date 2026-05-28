@echo off
REM Cleanup script - removes old parse_tcfx_stackup.py from scripts directory
REM The file has been moved to converter\ipc2581_to_json\parse_tcfx_stackup.py

echo Removing old parse_tcfx_stackup.py from scripts directory...

if exist "scripts\parse_tcfx_stackup.py" (
    del /Q "scripts\parse_tcfx_stackup.py"
    echo Done: Removed scripts\parse_tcfx_stackup.py
) else (
    echo File already removed or not found.
)

echo.
echo The TCFX parser is now located at:
echo   converter\ipc2581_to_json\parse_tcfx_stackup.py
echo.
echo It is automatically integrated into thomson_bundle_converter.py
