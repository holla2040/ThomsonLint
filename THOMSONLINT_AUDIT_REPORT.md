# THOMSONLINT AUDIT REPORT

**Document:** ThomsonLint Workflow Cross-Validation Audit  
**Scope:** `PLAN.md` and `OPENHANDS_REVIEW.md` vs. `ontology/ontology.json` and `docs/AI_Hardware_Design_Review_KnowledgeBase.md`  
**Audit Date:** 2026-05-26  
**Auditor Role:** Expert Workflow Auditor and Systems Engineer  

---

## Table of Contents

1. [Audit Scope and Methodology](#1-audit-scope-and-methodology)
2. [Workflow Parity Table](#2-workflow-parity-table)
3. [Gate Enforcement Gaps](#3-gate-enforcement-gaps)
4. [Ontology Coverage Gaps](#4-ontology-coverage-gaps)
5. [Knowledge Base Blind Spots](#5-knowledge-base-blind-spots)
6. [Actionable Recommendations](#6-actionable-recommendations)
7. [Summary Risk Matrix](#7-summary-risk-matrix)

---

## 1. Audit Scope and Methodology

### 1.1 Documents Reviewed

| Document | Lines | Purpose |
|---|---|---|
| `PLAN.md` | 330 | Linear execution plan (20 phases) |
| `OPENHANDS_REVIEW.md` | 626 | Normative workflow definitions (18 numbered workflows + response format) |
| `ontology/ontology.json` | 4280 | Machine-readable rule set (domains, severity, evidence requirements) |
| `docs/AI_Hardware_Design_Review_KnowledgeBase.md` | 929 | Human-readable engineering context (Appendices A–L) |

### 1.2 Audit Phases Executed

- **Phase 1:** Structural workflow alignment and gate compliance
- **Phase 2:** Ontology-to-evidence mapping verification
- **Phase 3:** Knowledge base depth verification
- **Phase 4:** Datasheet sourcing rules audit
- **Phase 5:** Report generation (this document)

---

## 2. Workflow Parity Table

Mapping of `OPENHANDS_REVIEW.md` Workflows to `PLAN.md` Phases with structural alignment assessment.

| OPENHANDS_REVIEW.md Workflow | PLAN.md Phase | Status | Notes |
|---|---|---|---|
| *(No corresponding numbered workflow — preamble content)* | **Phase 1** — Ingest ThomsonLint Workflow | ⚠️ PARTIAL | Phase 1 has no direct counterpart in OPENHANDS_REVIEW.md. It is a PLAN.md-only meta-phase. The mapping table it is supposed to produce (workflow → phase correspondence) is never formally defined, creating a loose coupling between the two documents. |
| **Workflow 1:** Prepare Review Inputs | **Phase 2** — Inspect Inputs and Datasheets | ✅ PASS | Content and intent aligned. Phase 2 correctly extends Workflow 1 by listing all stackup input sources explicitly. |
| **Workflow 2:** Setup and Tool Preflight | **Phase 3** — Setup and Tool Preflight | ✅ PASS | Artifact fields, fallback logic, and pass criteria are verbatim-aligned. |
| **Workflow 3:** Run Integrated Converter | **Phase 4** — Run Integrated Converter | ✅ PASS | Aligned on command, output verification, and evidence-quality note requirement for warnings. |
| **Workflow 4:** Inspect ThomsonLint Framework | **Phase 5** — Inspect Findings Framework | ✅ PASS | Aligned. Both enumerate the same framework files. |
| **Workflow 5:** Full BOM Datasheet Retrieval | **Phase 6** — Full BOM Datasheet Retrieval | ✅ PASS | Hard definitions (`discovered_url` / `downloaded_datasheet`), status values, bounding limits (3–5 URLs), coverage rule, and manifest validation artifact are well-aligned between documents. |
| **Workflow 6:** Enforce Image Review Gate | **Phase 7** — Enforce Image Review Gate | ✅ PASS | Fallback distinction, approval rules, artifact fields, and phase-local loop are aligned. **Minor gap (G-1):** Phase 7 does not explicitly reference `exports/tool-preflight-status.json` as the file where `json_only_review_approved` was set in Phase 3; OPENHANDS_REVIEW.md Workflow 6 implies this cross-file dependency. |
| **Workflow 7:** Review Schematic Evidence FULL | **Phase 8** — Review Schematic Evidence FULL | ⚠️ PARTIAL | Functionally aligned, but Phase 8 lacks a **dedicated evidence artifact** (e.g., no `exports/<project>-schematic-evidence-inventory.json`). Only the universal checkpoint row is required. This is a weak gate compared to Phase 9's two-artifact validation model. **Gap (G-2).** |
| **Workflow 8:** Full Board/Layout JSON Evaluation | **Phase 9** — Full Board/Layout JSON Evaluation | ✅ PASS | Strong alignment. Phase 9 correctly mirrors Workflow 8's two-artifact model (board evidence inventory + validation JSON). Both documents forbid summary-only extraction with identical language. |
| **Workflow 9:** Review Stackup and Manufacturing Evidence | **Phase 10** — Review Stackup and Manufacturing Evidence FULL | ⚠️ PARTIAL | Aligned on stackup data extraction. However, Phase 10 does **not** address DFM manufacturing evidence from KB Appendix G (acid traps, solder mask, panelization, edge clearances, copper slivers) — content wholly absent from both Phase 10 and Workflow 9. **Gap (G-3).** |
| **Workflow 10:** Review BOM and Component Evidence FULL | **Phase 11** — Review BOM and Component Evidence FULL | ⚠️ PARTIAL | Functionally aligned, but Phase 11 lacks a **dedicated evidence artifact**. No `exports/<project>-bom-evidence-inventory.json` is required. Evidence is only checkpoint-row backed. **Gap (G-4).** |
| **Workflow 11:** Review Image Evidence FULL | **Phase 12** — Review Image Evidence FULL | ⚠️ PARTIAL | Phase 12 and Phase 7 **share the same required artifact** (`exports/<project>-image-evidence-inventory.json`). An agent that created this artifact in Phase 7 can claim Phase 12 is complete without performing any actual image inspection. No distinct Phase-12-only artifact exists to prove inspection occurred. **Gap (G-5).** |
| **Workflow 12:** Review Datasheet Evidence FULL | **Phase 13** — Review Datasheet Evidence FULL | ⚠️ PARTIAL | Functionally aligned, but Phase 13 lacks a **dedicated evidence artifact**. No `exports/<project>-datasheet-evidence-inventory.json` is required. Evidence is only checkpoint-row backed. **Gap (G-6).** |
| **Workflow 13:** Cross-Source Consistency Review | **Phase 14** — Cross-Source Consistency Review | ✅ PASS | Cross-check coverage list is aligned between documents. |
| **Workflow 14:** Pre-Findings Gate Check | **Phase 15** — Pre-Findings Gate Check | ✅ PASS | Gate fields, blocker rule, and artifact definition are aligned. **Minor gap (G-7):** Phase 15 uses field name `datasheet_manifest_validation_pass` in the pre-findings gate JSON, but the source artifact `datasheet_manifest_validation.json` uses `overall_pass`. The mapping between these two field names is never documented. |
| **Workflow 15:** Create Candidate Findings | **Phase 16** — Candidate Finding Development | ✅ PASS | Aligned on evidence-backing requirements and vague-finding rejection. |
| **Workflow 16:** Create Findings JSON | **Phase 17** — Write Findings JSON | ❌ FAIL | **DIRECT CONTRADICTION (G-8).** OPENHANDS_REVIEW.md Workflow 16 states: *"Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise."* PLAN.md Phase 17 states: *"Do not apply arbitrary count caps."* An agent following PLAN.md would reject the 15-issue cap; an agent following OPENHANDS_REVIEW.md would enforce it. This is an unresolvable contradiction unless one document is authoritative. |
| **Workflow 17:** Validate Findings | **Phase 18** — Validate and Repair Findings | ✅ PASS | Aligned on validator invocation, repair-only constraint, and no-bypass rule. |
| **Workflow 18:** Generate Report | **Phase 19** — Generate Report | ✅ PASS | HTML-required assertion, markdown-only rejection, validation-before-report ordering, and artifact fields are aligned. |
| Final Agent Response Format | **Phase 20** — Final Summary | ✅ PASS | Required final response fields are mirrored from OPENHANDS_REVIEW.md into PLAN.md Phase 20. |

**Parity Summary:** 11 PASS / 7 PARTIAL / 1 FAIL (20 phases total)

---

## 3. Gate Enforcement Gaps

This section identifies missing or weak artifact validation requirements in `PLAN.md`.

### G-1 · Phase 7 — json_only_review_approved Cross-File Dependency Undocumented

**Location:** `PLAN.md` Phase 7, `OPENHANDS_REVIEW.md` Workflow 6  
**Severity:** Minor  
**Issue:** `json_only_review_approved` is set in `exports/tool-preflight-status.json` (created in Phase 3). Phase 7 requires this field to be `true` for JSON-only fallback approval, but neither Phase 7 in PLAN.md nor Workflow 6 in OPENHANDS_REVIEW.md explicitly states "read `json_only_review_approved` from `exports/tool-preflight-status.json`." An agent that re-evaluates from scratch could look for this flag in a new context and not find it, or create a duplicate field elsewhere.

---

### G-2 · Phase 8 — Schematic Review Has No Dedicated Evidence Artifact

**Location:** `PLAN.md` Phase 8, `OPENHANDS_REVIEW.md` Workflow 7  
**Severity:** Major  
**Issue:** Phase 9 mandates `exports/<project>-board-evidence-inventory.json` + validation artifact as proof of complete board review. Phase 8 has **no equivalent artifact**. The only gate for Phase 8 is the universal checkpoint row, which is insufficient because checkpoint rows can be written with `phase_passed=true` without any verifiable output. A schematic review that produces only narrative text — explicitly forbidden by the Artifact-Based Phase Completion Rule — could still pass Phase 8's gate.

**Contrast:** Phase 9 (Board), Phase 6 (BOM), Phase 7 (Images), Phase 15 (Pre-Findings Gate) all require dedicated named JSON artifacts. Phases 8, 11, 13, and 14 do not, making them systematically weaker gates.

---

### G-3 · Phase 10 — Stackup Review Omits All DFM Manufacturing Evidence

**Location:** `PLAN.md` Phase 10, `OPENHANDS_REVIEW.md` Workflow 9  
**Severity:** Major  
**Issue:** Phase 10 exclusively covers stackup material data (layer order, copper weight, dielectric, impedance). KB Appendix G (Design for Manufacturing) covers trace width/spacing minimums, via annular rings, acid traps, solder mask design, silkscreen clearances, panelization, fiducials, board edge clearances, copper slivers, and component-to-edge placement. None of these DFM checks are mandated in Phase 10 or any other phase. The board JSON (Phase 9) lists "non-copper geometry" and "silkscreen/mechanical features" as inspection categories but does not command DFM-specific evidence extraction against manufacturing minimums.

This means the following ontology rules have no dedicated evidence extraction phase:
`DFM_TRACE_001`, `DFM_VIA_001`, `DFM_ACID_001`, `DFM_MASK_001`, `DFM_SILK_001`, `DFM_PANEL_001`, `DFM_FID_001`, `DFM_FID_002`, `DFM_EDGE_001`, `DFM_SLIVER_001`, `DFM_COMP_EDGE_001`

---

### G-4 · Phase 11 — BOM Review Has No Dedicated Evidence Artifact

**Location:** `PLAN.md` Phase 11  
**Severity:** Moderate  
**Issue:** Same structural weakness as G-2. Phase 11 produces no named artifact beyond the checkpoint row. A superficial BOM scan that misses missing MPN fields, AERO_SLD_001-relevant lead-finish data, or component-mass records for AERO_VIB_001 could not be distinguished from a thorough review at the gate level.

---

### G-5 · Phase 12 — Image Review Gate Is Ineffective (Shared Artifact With Phase 7)

**Location:** `PLAN.md` Phase 12, `OPENHANDS_REVIEW.md` Workflow 11  
**Severity:** Major  
**Issue:** Phase 7 (Image Review Gate) creates `exports/<project>-image-evidence-inventory.json`. Phase 12 (Review Image Evidence FULL) declares the **same file** as its required artifact. Because the artifact already exists from Phase 7, the Phase 12 gate check — "if `image-evidence-inventory.json` is missing, do not proceed" — is satisfied vacuously without the agent ever opening a PNG in Phase 12. Nothing in the checkpoint mechanism distinguishes Phase 7 artifact creation from Phase 12 actual inspection.

A distinct Phase-12-only artifact (e.g., `exports/<project>-image-evidence-review.json` with fields such as `pages_actually_opened`, `visual_observations`, `phase_12_completed`) would close this gap.

---

### G-6 · Phase 13 — Datasheet Evidence Review Has No Dedicated Evidence Artifact

**Location:** `PLAN.md` Phase 13  
**Severity:** Moderate  
**Issue:** Same structural weakness as G-2 and G-4. Phase 13 produces no named artifact. There is no `exports/<project>-datasheet-evidence-review.json` that would prove component-specific parameters were extracted. An agent can write a checkpoint row and claim the phase is complete with only narrative text.

---

### G-7 · Phase 15 — Pre-Findings Gate Field Name Mismatch

**Location:** `PLAN.md` Phase 15  
**Severity:** Minor  
**Issue:** The pre-findings gate JSON (`exports/<project>-pre-findings-gate.json`) uses the field name `datasheet_manifest_validation_pass`, but the source artifact (`exports/datasheets/datasheet_manifest_validation.json`) uses `overall_pass`. Neither document specifies how the pre-findings gate derives this field from the source artifact. An agent implementing the gate could introduce a silent mapping error where `overall_pass=false` is not correctly reflected in `datasheet_manifest_validation_pass`.

---

### G-8 · Phase 17 vs. Workflow 16 — Direct Contradiction on Issues Count Cap

**Location:** `PLAN.md` Phase 17 vs. `OPENHANDS_REVIEW.md` Workflow 16  
**Severity:** Critical  
**Issue:** This is the only outright contradiction between the two documents.

- `OPENHANDS_REVIEW.md` Workflow 16: *"Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise."*
- `PLAN.md` Phase 17: *"Do not apply arbitrary count caps."*

An agent that treats OPENHANDS_REVIEW.md as the normative source will cap issues at 15. An agent that treats PLAN.md as authoritative will produce an uncapped issues list. The two behaviors are incompatible and produce materially different review outputs for designs with more than 15 issues.

---

### G-9 · No Phase Consolidation Warning is Absent From Individual Phase Descriptions

**Location:** `PLAN.md` Phases 8–14, 16–17  
**Severity:** Moderate  
**Issue:** The "No Phase Consolidation" rule is stated globally in Section 3 of PLAN.md but is **not repeated** in the individual phase descriptions for Phases 8–14 or 16–17. A stateless agent that does not retain the preamble could interpret the relatively brief phase descriptions of Phases 8, 11, 12, 13 as candidates for consolidation. Specifically, Phases 11 (BOM) and 12 (Images), and Phases 13 (Datasheets) and 14 (Cross-Source), are thematically adjacent and their brief descriptions provide no internal prohibition against consolidation.

---

## 4. Ontology Coverage Gaps

This section lists ontology rules in `ontology.json` that cannot be accurately assessed because `PLAN.md` fails to mandate the correct evidence extraction.

### 4.1 Aerospace Domain — No Dedicated Evidence Extraction Phase

All six AERO_* rules require metadata that does not appear in schematic, board, stackup, or BOM JSON exports. PLAN.md provides no mechanism to collect this data.

| Rule ID | Evidence Required | Evidence Phase in PLAN.md | Gap |
|---|---|---|---|
| **AERO_VIB_001** | Component mass (from datasheet or user metadata) to determine if mass > 3 g threshold is exceeded; vibration profile type; retention method inspection | Phase 13 covers datasheets but does not command mass data extraction. No phase covers user-supplied environmental metadata. | **MISSING** — no mass-extraction step |
| **AERO_SLD_001** | Solder alloy specification from fab order; IPC class (1/2/3) from fab notes; component lead-finish qualification (JESD201 class 1A, Vishay -E3/-M3) from BOM + datasheets | Phase 11 covers MPN/manufacturer fields but not IPC class, not solder alloy, not JESD201 lead-finish designators. No phase covers fab work-order inspection. | **MISSING** — no fab-notes inspection phase |
| **AERO_RPP_001** | Schematic check for ideal-diode controller + N-FET topology on aircraft DC bus input | Phase 8 schematic review covers "power nets" and "external interfaces" but doesn't enumerate the reverse-polarity protection topology check explicitly | **WEAK** — implicit but not commanded |
| **AERO_TVS_001** | Schematic + board: active rectifier IC presence, TVS placement within 50 mm of ANODE pin, TVS ground stitching via count | Phase 9 board review covers connectors and vias but doesn't enumerate "TVS placement within 50 mm of active rectifier IC" as an evidence target | **MISSING** — not commanded |
| **AERO_TERM_001** | Conformal coating specification in fab work order; masking documentation identifying each serviceable terminal | No PLAN.md phase covers process/fabrication documentation. Phase 2 (Inspect Inputs) does not list conformal coating specs as an accepted input type. | **MISSING** — no process-docs phase |
| **AERO_GND_001** | Board JSON: copper keepout presence around NPTH mounting holes on every layer; identification of single vs. multiple bonding points to chassis | Phase 9 inspection categories include "holes" and "plated vs non-plated" but do **not** include "copper keepout zones around NPTH holes" or "chassis-bond point identification." The board evidence inventory template has no field for this. | **MISSING** — not in board inventory schema |

---

### 4.2 Thermal Domain — Thermal Pad and Via Array Analysis Absent From Board Inventory

| Rule ID | Evidence Required | Gap |
|---|---|---|
| **THM_VIA_001** | Board JSON: thermal pad presence on component footprints; via array under thermal pads; via-to-pad ratio | Phase 9 inspection categories include "pads and pad primitives" and "vias/holes" but do not explicitly require thermal-pad identification or thermal-via-array assessment. The board evidence inventory schema (`exports/<project>-board-evidence-inventory.json`) has no field for `thermal_pad_analysis` or `thermal_via_array_coverage`. |
| **THM_PWR_001** | Board JSON: copper area adjacent to high-power components; identification of components with high power dissipation | Phase 9 board inventory includes `object_counts` and `component_count_if_available` but not power-dissipation candidates or adjacent-copper-area assessment. |

---

### 4.3 High-Speed / EMC Domain — Specific Layout Evidence Not Commanded

| Rule ID | Evidence Required | Gap |
|---|---|---|
| **HS_DDR_001** | Route length by net for DQ/DQS groups and address/command groups; specific tolerance verification | Phase 9 includes "route length by net/layer" generically, but doesn't mandate DQ/DQS group extraction or tolerance evaluation. Phase 14 mentions "paired/differential candidates vs route length/width evidence" partially. |
| **HS_DIFF_004** | Material data (fiber weave specification — spread glass, low-Dk) from stackup for high-speed differential pairs | Phase 10 covers material/Dk data where available, but doesn't explicitly feed this into a cross-check with Phase 9 differential-pair routing evidence. Phase 14 doesn't enumerate this cross-check. |
| **HS_MAT_001** | Stackup material system (FR-4 vs. Rogers/Isola) for multi-gigabit designs | Phase 10 covers materials but Phase 14 doesn't explicitly cross-check material against high-speed signal presence. |
| **PWR_BUCK_004** | Board JSON: keepout zones under power inductors for all layers; signal routing under inductor footprint | Phase 9 inspection categories do not include keepout zone analysis or "routing under component footprint" verification. |
| **PWR_BUCK_005** | Board JSON: switching node (SW) copper area measurement | Phase 9 mentions "polygons/copper areas" and "pour indicators" but does not command switching-node copper area assessment. |
| **EMC_PLANE_002** | Board JSON: continuous slots or walls of vias in ground planes | Phase 9 includes "polygons/copper areas" but does not command slot/via-wall analysis in ground planes. |

---

### 4.4 Schematic Domain — Key Check Families Not Enumerated

Phase 8 covers "components, nets, power nets, external interfaces, connector nets, single-pin/unusual connections" but does not enumerate the following schematic rule families, leaving them at risk of being skipped:

| Rule(s) | Check Type | Gap in Phase 8 |
|---|---|---|
| **SCH_I2C_001, SCH_I2C_002** | I2C address annotation and conflict detection | Not mentioned in Phase 8 evidence/output |
| **SCH_NET_001–004** | Cross-sheet label matching, single-pin nets, duplicate net names | "Single-pin/unusual connections" partially covers SCH_NET_002 but SCH_NET_001 (cross-sheet labels) and SCH_NET_004 (duplicate names = shorted rails) are not explicitly enumerated |
| **SCH_UART_001** | UART TX/RX crossover verification | Not mentioned |
| **SCH_FET_001** | MOSFET gate pull-down for defined startup state | Not mentioned |
| **PWR_RELAY_001** | Relay coil flyback diode | Not mentioned |
| **PWR_FUSE_001** | Overcurrent protection sizing | Not mentioned |
| **SCH_PULLUP_001** | Unused op-amp/comparator input tie-off | Not mentioned |
| **MS_RST_001** | Output lines defined state during reset | Not mentioned |
| **SCH_POL_001** | Polar capacitor polarity and voltage | Not mentioned |

---

### 4.5 Component Selection Domain — Datasheet Evidence Targets Not Enumerated

Phase 13 (Datasheet Evidence) provides guidance on citation format but does not list the component-parameter evidence targets that must be extracted from datasheets. Without explicit targets, the following rules lack a commanded evidence step:

| Rule Family | Evidence Required | Gap |
|---|---|---|
| **COMP_CAP_001–006** | Dielectric type (Y5V/X5R/X7R/C0G), DC bias derating curves, voltage rating, ESR/ESL specs, ripple current rating | Not enumerated as extraction targets in Phase 13 |
| **COMP_RES_001–003** | Noise index, temperature coefficient, power derating | Not enumerated |
| **COMP_IND_001–004** | Saturation current (Isat ≥ 1.3× peak), self-resonant frequency, Q factor, tolerance | Not enumerated (partially covered by PWR_RATING_001 which is mentioned in Phase 8 but saturation current requires a datasheet check in Phase 13) |
| **PWR_RATING_001** | Inductor Isat from datasheet vs. calculated peak inductor current | Phase 8 mentions "power nets" but inductor saturation verification requires datasheet data (Phase 13) cross-referenced against design calculations. Phase 14 doesn't enumerate this cross-check. |

---

## 5. Knowledge Base Blind Spots

Areas where the engineering depth required by `AI_Hardware_Design_Review_KnowledgeBase.md` exceeds the evidence extraction mandated by PLAN.md.

### 5.1 Appendix K (Aerospace) — Entirely Unaddressed

KB Appendix K defines six specific areas (K.1–K.6) with standards citations (AS-50881, IPC J-STD-001 Class 3, IEC 60068-2-6, DO-160, IPC-CC-830B, FAA AC 43.13-1B) and corresponding AERO_* rules. PLAN.md:
- Does not list aerospace certification documentation as an accepted input in Phase 2
- Does not extract component mass in Phase 13
- Does not inspect fab notes or assembly work instructions in any phase
- Does not check for conformal coating masking documentation in any phase
- Does not check chassis-ground keepout geometry in Phase 9's board inventory schema

For aerospace designs, this means **all six AERO_* rules** are effectively unenforceable as written in the current PLAN.md.

---

### 5.2 Appendix G (DFM) — Covered by Ontology but Absent From Evidence Plan

KB Appendix G contains 11 DFM subsections (G.1 Trace Width/Spacing → G.11 DFM Checklist) directly backed by 11 ontology rules (`DFM_TRACE_001`, `DFM_VIA_001`, `DFM_ACID_001`, `DFM_MASK_001`, `DFM_SILK_001`, `DFM_PANEL_001`, `DFM_FID_001`, `DFM_EDGE_001`, `DFM_SLIVER_001`, `DFM_COMP_EDGE_001`, `DFM_COURT_001`). None of these receive a dedicated evidence extraction command in PLAN.md:

- Phase 9 lists "non-copper geometry" and "silkscreen/mechanical features" as inspection categories, but these are described in terms of routing evidence, not DFM compliance checking. No field in the board evidence inventory schema captures "minimum trace width violations," "annular ring adequacy," or "component-to-edge clearance violations."
- Phase 10 covers only stackup material data. The DFM checklist in KB Appendix G (trace width, via size, solder mask, fiducials, panelization, edge clearances) is within Phase 10's subject matter (manufacturing readiness) but is completely absent.

---

### 5.3 Appendix A/D (High-Speed SI) — Deep Traversal Commanded but Specific Targets Missing

KB Appendix A covers crosstalk (3W rule, A.3), eye diagrams (A.4), and transmission-line basics. KB Appendix D covers differential pair routing (D.1), return-path vias (D.2), serpentine geometry (D.3), and material selection (D.4).

Phase 9 correctly forbids summary-only extraction and commands "deep traversal." However, it does not explicitly command:
- **Trace-spacing assessment** for the 3W rule (center-to-center ≥ 3× trace width)
- **Via stub length measurement** for `HS_DIFF_003` (stub length < λ/10 above 3 Gbps)
- **Serpentine geometry quality** for `HS_ROUTE_001` (45° bends, spacing ≥ 4× trace width)
- **Return-path via adjacency** for D.2 (ground via within one via-diameter of each signal via on layer change)

These require extracting routing geometry beyond what "route width by net" and "route length by net" capture.

---

### 5.4 Appendix C (SMPS Layout) — Layout-Level Checks Not Commanded

KB Appendix C covers the "hot loop" (C.2), compensation ringing (C.3), and related SMPS layout rules. Three ontology rules (`PWR_BUCK_004`, `PWR_BUCK_005`, `PWR_BUCK_006`) require board-level evidence:
- `PWR_BUCK_004`: No ground plane or signals under inductor — requires keepout zone inspection
- `PWR_BUCK_005`: SW node copper area minimization — requires polygon area analysis
- `PWR_BUCK_006`: Output cap/input cap separation — requires component position delta measurement

Phase 9 lists "polygons/copper areas" in its inspection categories, but does not command the SMPS-specific analyses needed to evaluate these rules.

---

### 5.5 Appendix B (Op-Amp Stability) — Schematic Evidence Targets Not Enumerated

KB Appendix B covers op-amp stability (large capacitive loads, feedback network topology, phase/gain margin). This maps to `AN_OPAMP_001`, `AN_OPAMP_002`, `AN_OPAMP_003`, and `SCH_PULLUP_001`. Phase 8 covers "components, nets, power nets" but does not enumerate op-amp-specific review items:
- Capacitive load at output (isolation resistor check for `AN_OPAMP_002`)
- Feedback topology classification for `AN_OPAMP_003`
- Unused op-amp section tie-off for `SCH_PULLUP_001`

---

### 5.6 Appendix I (Component Selection) — No Extraction Target List in Phase 13

KB Appendix I provides detailed component selection criteria for capacitors (I.1), resistors (I.2), and inductors (I.3), backed by 13 ontology rules (`COMP_CAP_001`–`COMP_IND_004`). Phase 13 instructs the agent to review "available local datasheet evidence" but provides no list of parameters to extract. Without explicit targets, systematic coverage of Appendix I rules is not guaranteed.

---

### 5.7 Appendix H (Schematic Review Checks) — Not Referenced in Phase 8

KB Appendix H is a systematic schematic review guide covering net integrity (H.1), component application (H.2), value/rating verification (H.3), protection and safety (H.4), experimental options (H.5), and I2C documentation (H.6). Phase 8 does not reference Appendix H or enumerate these check families. The current Phase 8 description is effectively a generic schematic scan rather than a structured multi-pass review.

---

## 6. Actionable Recommendations

### R-1 · Resolve the Issues-Count Contradiction (Critical)

**Target:** `OPENHANDS_REVIEW.md` Workflow 16 or `PLAN.md` Phase 17  
**Action:** Pick one authoritative position and apply it to both documents. The recommended resolution is to **retain PLAN.md's uncapped approach** (since the cap is arbitrary and inconsistent with full evidence-backed coverage) and **remove the "at most 15" limit from OPENHANDS_REVIEW.md Workflow 16**, replacing it with: *"Report all concrete, non-duplicative, evidence-supported issues. Do not apply an arbitrary numeric cap."*

---

### R-2 · Add a Dedicated Schematic Evidence Artifact (Phase 8)

**Target:** `PLAN.md` Phase 8, `OPENHANDS_REVIEW.md` Workflow 7  
**Action:** Require a `exports/<project>-schematic-evidence-inventory.json` artifact with fields analogous to the board evidence inventory:  
```
schematic_json_loaded, inspected_components, power_nets_identified, connector_nets_identified,
interface_nets_identified, single_pin_nets_found, i2c_buses_identified, uart_interfaces_identified,
relay_coil_count, protection_components_identified, schematic_check_families_covered,
conversion_limitations, evidence_paths_used
```
Add a corresponding validation artifact `exports/<project>-schematic-evidence-inventory-validation.json`.

---

### R-3 · Add Dedicated Evidence Artifacts for Phases 11, 13, and 14

**Target:** `PLAN.md` Phases 11, 13, 14  
**Action:** Following the Phase 9 model, require named artifacts:
- **Phase 11:** `exports/<project>-bom-evidence-inventory.json` — fields: `bom_row_count`, `mpn_coverage`, `lcsc_coverage`, `missing_mpn_rows`, `package_metadata_coverage`, `aero_lead_finish_reviewed`, `component_mass_candidates`, `dnp_components_flagged`
- **Phase 13:** `exports/<project>-datasheet-evidence-review.json` — fields: `datasheets_reviewed`, `components_with_voltage_rating_verified`, `components_with_saturation_current_verified`, `components_with_thermal_data_extracted`, `aero_lead_finish_designators_found`, `evidence_gaps`
- **Phase 14:** `exports/<project>-cross-source-review.json` — fields for each cross-check category listed in the phase

---

### R-4 · Decouple Phase 12 From Phase 7 Artifact

**Target:** `PLAN.md` Phase 12, `OPENHANDS_REVIEW.md` Workflow 11  
**Action:** Create a distinct Phase-12-only artifact `exports/<project>-image-evidence-review.json` separate from the Phase-7 image-evidence-inventory. This artifact should contain fields that can only be populated by actual image inspection:
```
pages_actually_opened, schematic_page_observations[], layout_page_observations[],
visual_concerns[], schematic_labels_identified[], power_interface_labels_identified[],
connector_labels_identified[], limitations[], phase_12_completed
```
Phase 12 gate should require `exports/<project>-image-evidence-review.json` to exist and `phase_12_completed=true`.

---

### R-5 · Add Aerospace Evidence Collection to Phase 2 and Phase 11

**Target:** `PLAN.md` Phase 2 (Inspect Inputs), Phase 11 (BOM Review), Phase 13 (Datasheet Review)  
**Action:**

**Phase 2:** Extend accepted input types to include:
- Fab work order or board-build specification (for `AERO_SLD_001` solder alloy, IPC class)
- Conformal coating specification document (for `AERO_TERM_001` masking requirements)
- Environmental profile document (for `AERO_VIB_001` vibration profile)
- Chassis-mounting drawing (for `AERO_GND_001` bonding point identification)

**Phase 11:** Add to BOM review targets:
- Solder alloy stated in fab notes or BOM notes field
- IPC class from BOM or fab specification
- Component lead-finish designators (JESD201 class 1A, -E3/-M3, etc.)
- Component mass for components > 1 g (from datasheet or mass field in BOM)

**Phase 13:** Add explicit extraction targets:
- Component mass (from datasheet mechanical section) for relays, large electrolytics, inductors, crystals, modules
- Lead-finish suffix qualification from datasheet ordering information

---

### R-6 · Add NPTH Keepout Check and Thermal Pad Analysis to Phase 9 Board Inventory

**Target:** `PLAN.md` Phase 9, `OPENHANDS_REVIEW.md` Workflow 8  
**Action:** Add two fields to the required board evidence inventory:
- `npth_holes_with_copper_keepout`: list of NPTH holes and whether copper keepout is present on all layers
- `thermal_pad_components`: list of components identified as having thermal pads, with via array presence status

Add corresponding required inspection category: *"NPTH mounting holes and copper keepout zones"* and *"thermal pad footprints and via array sufficiency."*

---

### R-7 · Add DFM Evidence Phase or Extend Phase 10

**Target:** `PLAN.md` Phase 10 or as new phase, `OPENHANDS_REVIEW.md` Workflow 9  
**Action:** Either extend Phase 10 to cover DFM manufacturing evidence or add a "Phase 10b — DFM Checklist Review" with inspection targets mapped directly to KB Appendix G:
- Trace width minimum compliance (G.1) — from Phase 9 route width summary
- Via annular ring analysis (G.2) — from Phase 9 via/hole data
- Silkscreen clearance and legibility (G.5)
- Fiducial count and placement (G.7)
- Board edge clearance (G.8) — from Phase 9 board outline + component positions
- Copper slivers (G.9) — from Phase 9 polygon data
- Component-to-edge clearance (G.10)

This requires adding these categories to the required Phase 9 board inventory inspection list so the data is available for DFM evaluation.

---

### R-8 · Add Appendix H Schematic Check Families to Phase 8

**Target:** `PLAN.md` Phase 8  
**Action:** Extend Phase 8's "Expected evidence/output" to explicitly enumerate the KB Appendix H schematic check families:
- Net integrity (single-pin nets, cross-sheet label matching, duplicate power net names)
- Component application (floating inputs, UART TX/RX crossover, MOSFET gate pull-down)
- Value and rating verification (polar capacitor polarity, voltage ratings)
- Protection and safety (relay flyback diodes, fuse sizing, overcurrent protection)
- I2C address annotation and conflict detection
- Reset state for all output lines

---

### R-9 · Add Explicit Phase 17 Cross-Check to OPENHANDS_REVIEW.md Workflow 16

**Target:** `OPENHANDS_REVIEW.md` Workflow 16 item 7  
**Action:** Verify the resolution chosen in R-1 is applied. If adopting an uncapped approach, add text to Workflow 16: *"Do not apply an arbitrary count cap on issues. Include every concrete, non-duplicative, evidence-supported issue that satisfies schema and validation requirements."*

---

### R-10 · Document json_only_review_approved Cross-File Dependency

**Target:** `PLAN.md` Phase 7, `OPENHANDS_REVIEW.md` Workflow 6  
**Action:** Add to Phase 7 validation instructions: *"Read `json_only_review_approved` from `exports/tool-preflight-status.json` (written in Phase 3). Do not re-request user approval if already recorded there."*

---

### R-11 · Repeat No-Consolidation Warning in Each Phase 8–14 Description

**Target:** `PLAN.md` Phases 8–14  
**Action:** Add a standardized one-line reminder at the top of each Phase 8–14 description:  
*"⚠️ No Phase Consolidation: This phase must produce its checkpoint row and complete independently before the next phase begins."*

---

### R-12 · Reconcile Pre-Findings Gate Field Naming

**Target:** `PLAN.md` Phase 15  
**Action:** Either (a) rename `datasheet_manifest_validation_pass` in the pre-findings gate to `datasheet_manifest_overall_pass` to match the source artifact field `overall_pass`, or (b) add an explicit note: *"`datasheet_manifest_validation_pass` must be set by reading `exports/datasheets/datasheet_manifest_validation.json overall_pass`."*

---

## 7. Summary Risk Matrix

| Gap ID | Description | Documents Affected | Severity | Type |
|---|---|---|---|---|
| **G-1** | `json_only_review_approved` cross-file dependency undocumented | PLAN Phase 7, OPENHANDS Workflow 6 | Minor | Gate |
| **G-2** | Phase 8 (Schematic) has no dedicated evidence artifact | PLAN Phase 8, OPENHANDS Workflow 7 | Major | Gate |
| **G-3** | Phase 10 omits all DFM manufacturing evidence | PLAN Phase 10, OPENHANDS Workflow 9 | Major | Coverage |
| **G-4** | Phase 11 (BOM) has no dedicated evidence artifact | PLAN Phase 11 | Moderate | Gate |
| **G-5** | Phase 12 (Image Review) gate is vacuously satisfied by Phase 7 artifact | PLAN Phase 12, OPENHANDS Workflow 11 | Major | Gate |
| **G-6** | Phase 13 (Datasheet) has no dedicated evidence artifact | PLAN Phase 13 | Moderate | Gate |
| **G-7** | Pre-findings gate field name mismatch vs. source artifact field | PLAN Phase 15 | Minor | Gate |
| **G-8** | **DIRECT CONTRADICTION: issues count cap** | PLAN Phase 17 vs. OPENHANDS Workflow 16 | **Critical** | Contradiction |
| **G-9** | No-consolidation warning absent from individual phase descriptions | PLAN Phases 8–14, 16–17 | Moderate | Gate |
| **AERO-ALL** | All 6 AERO_* rules lack commanded evidence extraction steps | PLAN Phases 2, 9, 11, 13 | Major | Coverage |
| **THM-VIA** | `THM_VIA_001` thermal pad analysis absent from board inventory schema | PLAN Phase 9 | Moderate | Coverage |
| **DFM-ALL** | 11 DFM_* rules have no dedicated evidence extraction step | PLAN Phases 9, 10 | Major | Coverage |
| **SCH-ENUM** | 9 schematic rule families not enumerated in Phase 8 | PLAN Phase 8 | Moderate | Coverage |
| **DS-ENUM** | Component selection evidence targets not enumerated in Phase 13 | PLAN Phase 13 | Moderate | Coverage |
| **HS-DEPTH** | Via stub, serpentine geometry, return-path via targets missing from Phase 9 | PLAN Phase 9 | Moderate | Coverage |
| **SMPS-DEPTH** | Inductor keepout, SW-node copper, hot-loop geometry not commanded in Phase 9 | PLAN Phase 9 | Moderate | Coverage |

**Totals by Severity:**
- 🔴 Critical: 1 (G-8 — issues count contradiction)
- 🟠 Major: 6 (G-2, G-3, G-5, AERO-ALL, DFM-ALL, and total aerospace coverage)
- 🟡 Moderate: 8
- 🔵 Minor: 2

---

*End of ThomsonLint Audit Report.*
