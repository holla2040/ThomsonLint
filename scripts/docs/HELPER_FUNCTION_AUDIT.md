# Helper Function Documentation Audit

## Comparison: Documented vs Available Commands

### ✅ geometry_helpers.py - **FULLY DOCUMENTED**

**Documented in PLAN.md & OPENHANDS_REVIEW.md:**
```bash
--net <NET_NAME> --json
--clearance NET_A NET_B
--diff-pairs --json
--npth --npth-radius 4.0 --json
--ampacity VCC 2.0
--check-annular-ring --json
--detect-acid-traps --json
--board-edge-clearance --json
--copper-balance --json
--verify-impedance --target-ohms 50 --json
--verify-trace-temp --current-a 3.0 --max-temp-rise 10.0 --json
--check-voltage-clearance --json
```

**Actually Available (from code):**
All documented commands are correct! ✅

**Public Functions Available (not CLI):**
- `load_board_json()` - Load board JSON
- `get_net_segments()` - Get segment stats for a net
- `get_all_net_segments()` - Get stats for all nets
- `calculate_min_clearance()` - Calculate clearance between two nets
- `calculate_clearances_for_net()` - Calculate clearances from one net to many
- `analyze_differential_pair()` - Analyze a specific diff pair
- `analyze_all_differential_pairs()` - Auto-detect and analyze all pairs
- `calculate_trace_ampacity()` - IPC-2152 current capacity
- `verify_trace_ampacity()` - Verify net ampacity
- `load_stackup_json()` - Load stackup data
- `verify_impedance()` - Verify impedance (HS_MAT_001)
- `verify_trace_temperature()` - Verify thermal (PWR_TRACE_002)
- `check_voltage_clearance()` - Verify voltage spacing (DFM_TRACE_004)

**Missing from Documentation:**
None! All CLI commands are documented ✅

---

### ❌ schematic_helpers.py - **PARTIALLY DOCUMENTED**

**Documented in PLAN.md & OPENHANDS_REVIEW.md:**
```bash
python scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --analyze-all --json
```

**Actually Available (from code):**
```bash
--analyze-all          # Run all checks (documented) ✅
--single-pins          # Single-pin net detection (SCH_NET_002)
--uart-check           # UART crossover validation (SCH_UART_001)
--fet-check            # FET gate termination check (SCH_FET_001)
--floating-check       # Floating input detection (SCH_FLOAT_001)
--i2c-check            # I2C bus analysis (MS_I2C_001, SCH_I2C_002)
--opamp-check          # Op-amp tie-off check (SCH_PULLUP_001)
--json                 # Output pure JSON (documented) ✅
```

**Missing from Documentation:**
Individual check flags: `--single-pins`, `--uart-check`, `--fet-check`, `--floating-check`, `--i2c-check`, `--opamp-check`

**Impact:** Minor - `--analyze-all` is sufficient for workflow

---

### ❌ bom_helpers.py - **PARTIALLY DOCUMENTED**

**Documented in PLAN.md & OPENHANDS_REVIEW.md:**
```bash
python scripts/bom_helpers.py exports/<project>-bom.json --audit-components --json
```

**Actually Available (from code):**
```bash
--audit-components     # Run all component checks (documented) ✅
--heavy-threshold 3.0  # Heavy component threshold (AERO_VIB_001)
--check-dielectrics    # Audit capacitor dielectrics (COMP_CAP_001)
--audit-mpns           # Audit ordering codes (DFM_BOM_001)
--check-lead-finish    # Assess lead finish (AERO_SLD_001)
--polarized            # Identify polarized capacitors (SCH_POL_001)
--json                 # Output pure JSON (documented) ✅
```

**Missing from Documentation:**
Individual check flags: `--heavy-threshold`, `--check-dielectrics`, `--audit-mpns`, `--check-lead-finish`, `--polarized`

**Impact:** Minor - `--audit-components` is sufficient for workflow

---

### ❌ stackup_helpers.py - **PARTIALLY DOCUMENTED**

**Documented in PLAN.md & OPENHANDS_REVIEW.md:**
```bash
python scripts/stackup_helpers.py input/stackup.csv --validate-stackup --json
python scripts/stackup_helpers.py input/stackup.csv --check-thickness --json
python scripts/stackup_helpers.py input/stackup.csv --check-symmetry --json
python scripts/stackup_helpers.py input/stackup.csv --check-reference-planes --json
```

**Actually Available (from code):**
```bash
--validate-stackup          # Run all checks (documented) ✅
--check-schema              # Schema validation only
--check-thickness           # DFM_STACKUP_001 (documented) ✅
--target-thickness 63.0     # Target thickness in mils
--thickness-tolerance 10.0  # Tolerance percentage
--check-symmetry            # DFM_STACKUP_002 (documented) ✅
--check-reference-planes    # HS_MAT_001 (documented) ✅
--json                      # Output pure JSON (documented) ✅
```

**Missing from Documentation:**
- `--check-schema`
- `--target-thickness`
- `--thickness-tolerance`

**Impact:** Minor - `--validate-stackup` is sufficient

---

### ❌ cross_check_helpers.py - **PARTIALLY DOCUMENTED**

**Documented in PLAN.md & OPENHANDS_REVIEW.md:**
```bash
python scripts/cross_check_helpers.py --bom <bom> --sch <sch> --brd <brd> --json
```

**Actually Available (from code):**
```bash
--bom <path>              # Path to BOM JSON (documented) ✅
--sch <path>              # Path to Schematic JSON (documented) ✅
--brd <path>              # Path to Board JSON (documented) ✅
--run-reconciliation      # RefDes tripartite matching
--check-packages          # Package/footprint validation (DFM_LIB_002)
--verify-netlist          # Netlist topology (SCH_NET_001)
--verify-derating         # Voltage derating (SCH_POL_001, COMP_CAP_002)
--json                    # Output pure JSON (documented) ✅
```

**Missing from Documentation:**
Individual check flags: `--run-reconciliation`, `--check-packages`, `--verify-netlist`, `--verify-derating`

**Current Documentation:** Only shows paths, doesn't show that it defaults to running all checks

**Impact:** Medium - Should clarify that without individual flags, all checks run

---

## Summary

### ✅ **Fully Documented:**
- `geometry_helpers.py` - All CLI flags and usage patterns correct

### ⚠️ **Partially Documented:**
- `schematic_helpers.py` - Missing individual check flags (low priority)
- `bom_helpers.py` - Missing individual check flags (low priority)
- `stackup_helpers.py` - Missing tuning parameters (low priority)
- `cross_check_helpers.py` - Missing individual check flags (medium priority)

### 📝 **Recommended Additions to Documentation:**

#### 1. Add to Phase 8 / Workflow 7 (Schematic):
```markdown
**Optional: Run individual checks:**
- `--single-pins` - SCH_NET_002
- `--uart-check` - SCH_UART_001
- `--fet-check` - SCH_FET_001
- `--floating-check` - SCH_FLOAT_001
- `--i2c-check` - MS_I2C_001, SCH_I2C_002
- `--opamp-check` - SCH_PULLUP_001
```

#### 2. Add to Phase 12 / Workflow 11 (BOM):
```markdown
**Optional: Run individual checks:**
- `--heavy-threshold 3.0` - AERO_VIB_001
- `--check-dielectrics` - COMP_CAP_001
- `--audit-mpns` - DFM_BOM_001
- `--check-lead-finish` - AERO_SLD_001
- `--polarized` - SCH_POL_001
```

#### 3. Add to Phase 16 / Workflow 13 (Cross-Check):
```markdown
**Default behavior:** Runs all checks if no individual flags specified.

**Optional: Run individual checks:**
- `--run-reconciliation` - RefDes tripartite matching
- `--check-packages` - DFM_LIB_002
- `--verify-netlist` - SCH_NET_001
- `--verify-derating` - SCH_POL_001, COMP_CAP_002
```

---

## Verdict: **90% Complete**

The critical commands (`--analyze-all`, `--audit-components`, `--validate-stackup`, all geometry commands) are fully documented. The missing items are optional individual check flags that an AI agent doesn't need to know about since the "all" flags are sufficient.

**Recommendation:** Add the optional flags for completeness, but the current documentation is sufficient for an AI agent to execute the workflow successfully.
