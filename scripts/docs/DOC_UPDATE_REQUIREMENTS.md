# Documentation Update Requirements

## Files to Update
- `PLAN.md`
- `OPENHANDS_REVIEW.md`

## Required Updates

### 1. Add Reference to New Test Suite ✅ Already Mentioned

Both documents reference `scripts/geometry_helpers.py` ✅

### 2. Update Geometry Helpers Capabilities

Add note about recent fixes in Phase 9 / Workflow 8:

**Current mentions:**
- geometry_helpers.py for quantitative analysis
- DFM checks (annular rings, acid traps, edge clearance, copper balance)
- Physical-math verification (impedance, temperature, voltage clearance)

**Add this note after geometry_helpers.py introduction:**

```markdown
**Recent Fixes (2024):**
- Differential impedance calculation corrected (48Ω → 100Ω differential target)
- Length-weighted coupling average for accurate impedance
- Topology-specific formulas (microstrip vs stripline)
- NPTH clearance unit conversion fixed (mm → board units)
- Via annular ring cross-reference (coordinate-based pad lookup)
- Board outline extraction (flat point list handling)
- Net-type-aware edge clearances (GND=25mil, PWR/SIG=50mil)
- Schematic-driven power/ground net classification
- Negative clearance clamping (overlap → 0.0)
```

### 3. Verify Helper Script Paths

All paths are correct:
- ✅ `scripts/geometry_helpers.py`
- ✅ `scripts/saturn_engine.py` (integrated into geometry_helpers)
- ✅ `scripts/schematic_helpers.py`
- ✅ `scripts/stackup_helpers.py`
- ✅ `scripts/bom_helpers.py`
- ✅ `scripts/cross_check_helpers.py`

### 4. Add Testing Reference

Add after Phase 9 / Workflow 8 geometry helpers section:

```markdown
**Testing:**
- Comprehensive test suite: `tests/test_all_geometry_functions.py`
- Quick validation: `tests/test_geometry_helpers.py`
- All 18 geometry functions verified with mathematical proofs
- See `scripts/docs/TESTING_SUMMARY.md` for detailed test results
```

### 5. Update Converter Reference

Both documents mention `thomson_bundle_converter.py` ✅

Add note about recent converter improvements:
- TCFX stackup integration (automatic merge during conversion)
- Board outline extraction improvements
- Schematic analysis integration (power_nets, ground_nets, clock_nets in board JSON)

### 6. Ontology Rules - Verify Completeness

#### Phase 8 / Workflow 7 - Schematic Rules (Cluster 1)

**Currently Listed:**
- SCH_NET_001, SCH_NET_002, SCH_NET_003, SCH_NET_004 ✅
- SCH_UART_001, SCH_FLOAT_001, SCH_FET_001, SCH_PULLUP_001 ✅
- AN_OPAMP_002, AN_OPAMP_003, AN_ADC_001, AN_ADC_003 ✅
- PWR_COMP_001, PWR_RELAY_001, PWR_FUSE_001 ✅
- SCH_POL_001, SCH_DNP_001 ✅
- SCH_OPT_001, SCH_IC_001 (marked UNVERIFIABLE) ✅
- AERO_TVS_001, AERO_RPP_001 ✅
- SCH_I2C_001, SCH_I2C_002, MS_I2C_001 ✅
- MS_RST_001, MX_PWR_001 ✅
- DFT_JTAG_001, DFT_SWD_001 ✅

**Missing from list (should add):**
- PWR_DEC_001 (decoupling capacitor placement)
- PWR_DEC_002 (bulk capacitor sizing)
- PWR_REG_001 (regulator thermal pad)

#### Phase 9 / Workflow 8 - Board/Layout Rules (Cluster 2)

**Currently Implicit via Geometry Helpers:**
- Via annular rings (DFM_VIA_001, DFM_VIA_003, DFM_VIA_004) ✅
- Acid traps (DFM_ACID_001) ✅
- Board edge clearance (DFM_EDGE_001, DFM_PANEL_001) ✅
- Copper balance (DFM_COPPER_001) ✅
- NPTH keepout (Appendix K.6) ✅
- Impedance (HS_MAT_001) ✅
- Trace temperature (PWR_TRACE_002) ✅
- Voltage clearance (DFM_TRACE_004) ✅

**Should explicitly list:**
- PWR_BUCK_001, PWR_BUCK_002, PWR_BUCK_003, PWR_BUCK_004 (SMPS layout)
- HS_DIFF_001, HS_DIFF_002, HS_DIFF_003, HS_DIFF_004, HS_DIFF_005, HS_DIFF_006 (differential pairs)
- HS_DDR_001, HS_DDR_002, HS_DDR_003, HS_DDR_004 (DDR routing)
- EMC_GND_001, EMC_GND_002, EMC_GND_003 (ground stitching)
- AN_TRACE_001, AN_TRACE_002 (analog routing)

#### Phase 10 / Workflow 9 - Stackup Rules

**Currently Listed:**
- DFM_STACKUP_001 (thickness) ✅
- DFM_STACKUP_002 (symmetry) ✅
- HS_MAT_001 (reference planes) ✅

**Complete** ✅

#### Phase 11 / Workflow 10 - DFM Rules

**Currently Listed:**
- Annular rings, acid traps, edge clearance, copper balance ✅

**Should add:**
- DFM_TRACE_001, DFM_TRACE_002, DFM_TRACE_003 (trace width/spacing)
- DFM_LIB_002 (footprint validation)
- DFM_SLIVER_001 (copper/mask slivers)
- DFM_COMP_001 (component edge clearance)
- DFM_FID_001 (fiducial placement)

#### Phase 12 / Workflow 11 - BOM Rules

**Currently Implicit via bom_helpers.py:**
- AERO_VIB_001 (heavy components) ✅
- COMP_CAP_001 (capacitor dielectrics) ✅
- DFM_BOM_001 (incomplete MPNs) ✅
- AERO_SLD_001 (lead finish) ✅
- SCH_POL_001 (polarized caps) ✅

**Should add:**
- COMP_CAP_002 (capacitor derating)
- AERO_TERM_001 (connector locking/retention)

#### Phase 16 / Workflow 13 - Cross-Check Rules

**Currently Listed via cross_check_helpers.py:**
- RefDes reconciliation ✅
- Package/footprint matching (DFM_LIB_002) ✅
- Netlist topology (SCH_NET_001) ✅
- Voltage derating (SCH_POL_001, COMP_CAP_002) ✅

**Complete** ✅

---

## Summary

**Overall Status:** Both documents are 90% current!

**Minor updates needed:**
1. Add note about recent geometry_helpers.py fixes
2. Add testing reference
3. Expand explicit rule lists for Phases 9, 11, 12 (currently implicit via helper tools)
4. Add converter improvements note

**Critical:** All helper script paths and workflows are correct ✅
