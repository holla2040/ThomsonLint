@echo off
REM Test Saturn physical-math verification with complete stackup data

echo ============================================================
echo Saturn Physical Verification Test Suite
echo ============================================================
echo.

REM First, run the converter to get fresh stackup with TCFX merge
echo Step 1: Running converter to merge TCFX stackup data...
py -3 converter\ipc2581_to_json\thomson_bundle_converter.py "TestProject"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Converter failed
    exit /b 1
)
echo.

REM Test 2: Verify impedance calculations
echo Step 2: Testing impedance verification...
echo ============================================================
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-impedance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --target-ohms 100.0 --json
echo.

REM Test 3: Verify trace temperature calculations
echo Step 3: Testing trace temperature verification...
echo ============================================================
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --verify-trace-temp --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
echo.

REM Test 4: Verify voltage clearance checks
echo Step 4: Testing voltage clearance verification...
echo ============================================================
py -3 scripts\geometry_helpers.py TestProject\post_conversion\TestProject-thomson-export-brd.json --check-voltage-clearance --stackup TestProject\post_conversion\TestProject-thomson-export-stack.json --json
echo.

REM Test 5: Run Saturn engine standalone test
echo Step 5: Testing Saturn engine directly...
echo ============================================================
py -3 scripts\saturn_engine.py
echo.

echo ============================================================
echo All Saturn tests completed!
echo ============================================================
