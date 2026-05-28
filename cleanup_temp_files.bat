@echo off
echo Cleaning up temporary debug and test scripts...
echo.

REM Debug scripts
del /Q debug_geometry_helpers.py 2>nul
del /Q debug_via_structure.py 2>nul
del /Q debug_outline.py 2>nul
del /Q debug_via.bat 2>nul

REM Quick test scripts
del /Q quick_edge_test.py 2>nul
del /Q quick_diagnose.py 2>nul
del /Q quick_via_test.py 2>nul
del /Q quick_via_test.bat 2>nul
del /Q quick_json_check.py 2>nul
del /Q quick_inspect.py 2>nul
del /Q quick_extract.py 2>nul
del /Q _quick_saturn_test.py 2>nul
del /Q _quick_check.py 2>nul

REM Check/inspect scripts
del /Q check_outline.py 2>nul
del /Q check_nets_simple.py 2>nul
del /Q check_route_widths.py 2>nul
del /Q _check_board_structure.py 2>nul

REM Diagnose scripts
del /Q _diagnose.py 2>nul
del /Q diagnose_simple.py 2>nul
del /Q diagnose_nets.py 2>nul
del /Q diagnose_and_save.py 2>nul
del /Q diagnose_nets.bat 2>nul
del /Q run_diagnose.py 2>nul
del /Q run_diagnostic.bat 2>nul
del /Q run_diagnose.bat 2>nul
del /Q _run_diagnose.bat 2>nul
del /Q temp_diagnose.py 2>nul
del /Q write_diagnose_results.py 2>nul
del /Q execute_diagnose.py 2>nul

REM Extract scripts
del /Q extract_nets.py 2>nul
del /Q final_extract.py 2>nul
del /Q simple_extract.py 2>nul
del /Q manual_extract_nets.py 2>nul
del /Q execute_extract.py 2>nul
del /Q run_extract.py 2>nul
del /Q run_extract.bat 2>nul

REM Inspect scripts
del /Q _inspect_schema.py 2>nul
del /Q _inspect_nets.py 2>nul
del /Q inspect_board.py 2>nul

REM Other temporary
del /Q _plan_writer.py 2>nul
del /Q get_keys.py 2>nul
del /Q parse_json.py 2>nul
del /Q find_voltage_nets.py 2>nul
del /Q show_net_structure.py 2>nul
del /Q run_it.bat 2>nul
del /Q run_comprehensive_test.bat 2>nul
del /Q _test_schematic.bat 2>nul
del /Q bootstrap.py 2>nul

REM Old diagnostic/extraction tools
del /Q diagnose_output.txt 2>nul
del /Q DIAGNOSTIC_REPORT.md 2>nul
del /Q extract_nets.js 2>nul
del /Q net_extractor.html 2>nul

echo.
echo Cleanup complete!
echo.
echo Kept essential files:
echo   - test_all_geometry_functions.py (comprehensive test suite)
echo   - test_geometry_helpers.py (quick test suite)
echo   - test_clearance_clamping.py (clearance fix validation)
echo   - test_edge_clearance_types.py (net-type-aware clearances)
echo   - test_saturn_verification.bat (impedance testing)
echo   - test_saturn_with_stackup.py (Saturn engine tests)
echo   - test_voltage_check.py (voltage clearance tests)
echo   - test_tcfx_integration.py (converter integration)
pause
