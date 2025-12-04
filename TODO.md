# TODO — AI Hardware Design Review Framework

This file is written for **future AI agents / CLI tools** (e.g., Codex / GPT via CLI) that are asked to “read TODO.md and continue work on this project.”

If you are an AI model reading this file:

- Treat this as your **project spec + backlog**.
- Understand the current repository state.
- Then pick tasks from the backlog when the user asks you to “continue work.”

---

## Project Status

The initial development phase, as outlined in the "Backlog Checklist" (Section 4 below), is now complete. All planned tasks have been implemented and integrated into the framework. This `TODO.md` file is preserved for historical context and can be re-purposed for future development sprints.

---

## 1. Project Summary (for the AI)

This repository is building a **knowledge and rule framework for AI-assisted hardware design review**. The primary goal is to create a comprehensive set of files (`ontology.json`, `AI_Hardware_Design_Review_KnowledgeBase.md`, `examples.json`) that can be uploaded to a general-purpose AI (like Gemini) to provide it with the specialized context and expertise needed to review hardware designs (schematics / PCBs). This framework covers:

-   Schematic review (digital, analog, mixed-signal)
-   PCB layout (placement, routing, SI/PI, EMC/ESD, thermal, mechanical)
-   Ontology of rules (machine-readable JSON) - **Significantly expanded**
-   Examples of issues (JSON) for training / testing - **Significantly expanded**
-   Human + AI-readable knowledge base (Markdown) - **Significantly expanded**
-   JSON schemas for validating ontology and examples - **Created**
-   Multi-agent reasoning specification - **Created**

You (the AI) will be asked to extend and refine this system over time, with the ultimate aim of enabling Gemini to emit structured JSON issues and comprehensive reviews based on provided design files (CAD, images, etc.).

---

## 2. Current Repository Contents (what exists now)

Assumed files already present:

-   `README.md`  
    -   Overview of the project.
    -   Executive summary.
    -   How humans and tools should use the repo.

-   `LICENSE`  
    -   MIT license (or similar).

-   `CONTRIBUTING.md`  
    -   High-level contribution guidelines.

-   `docs/AI_Hardware_Design_Review_KnowledgeBase.md`  
    -   “Detailed but concise” knowledge base.
    -   **Now includes Appendix A on High-Speed Signal Integrity.**
    -   Covers multi-pass AI review framework, schematic/PCB rules, failure modes, JSON output schema, and guidance for extending.

-   `docs/Multi_Agent_Reasoning_Spec.md`
    -   **Newly created specification** outlining conceptual multi-agent architecture for specialized review.

-   `ontology/ontology.json`  
    -   A **significantly expanded ontology** containing:
        -   `schema_version`, `project`, `domains`, `severity_levels`.
        -   **Expanded with High-Speed Digital (SI) rules.**

-   `examples/examples.json`  
    -   A **significantly expanded examples** file with:
        -   More example scenarios.
        -   **Now includes high-speed digital examples.**
        -   Each maps to one or more rules from the ontology.
        -   Each includes expected issue output (rule_id, severity, summary, recommended_actions).

-   `tests/` directory
    -   **Newly created directory** containing:
        -   `tests/ontology_schema.json` - JSON schema for validating `ontology.json`.
        -   `tests/examples_schema.json` - JSON schema for validating `examples.json`.

If any of these are missing or inconsistent, your first task should be to **align them with this description**.

---

## 3. Formatting & Behavior Constraints (very important)

When you (AI) modify files in this repo:

1.  **Never include Markdown headings, commentary, or code fences inside JSON files.**
    -   JSON files must contain **pure JSON only**.
    -   No leading `---`, no ```json fences, no prose.

2.  **When updating a file, output the full new file contents**, not a diff.
    -   The user will typically overwrite the file manually.
    -   Do NOT output “only the changed part”; always output the whole file.

3.  **Do not create ZIP archives or binary content.**
    -   Just produce plain text content for files.

4.  **Preserve valid syntax.**
    -   `ontology/ontology.json` must remain valid JSON.
    -   `examples/examples.json` must remain valid JSON.
    -   Markdown files must remain valid Markdown.

5.  **Be explicit about which file you are updating.**
    -   e.g., “Updated `ontology/ontology.json`:” followed by the complete JSON.

6.  **If you add new files**, mention:
    -   The path (e.g., `docs/Appendix_HighSpeed_SI.md`).
    -   The intended purpose.

---

## 4. Backlog Checklist (What Needs to Be Done Next)

These are the **major work areas** for this project. When the user asks you to “continue work,” you should choose one area (or the one they specify) and work on it.

### 4.1 Expand Ontology (`ontology/ontology.json`)

Goal: grow from a few rules → a richer rule set covering the main hardware domains.

-   `[x]` **4.1.1 High-Speed Digital (SI)**
    -   `[x]` Add DDR3/DDR4/LPDDR rules: length matching, topology, VREF/VTT/VDDQ, termination.
    -   `[x]` Add high-speed serial rules: differential impedance, length matching, max vias, no plane splits, reference-plane continuity.
    -   `[x]` Add Clock nets rules: single-source driving, series termination, fanout buffer usage.
    -   *Each rule includes: `id`, `name`, `domain`, `description`, `applies_to`, `conditions`, `default_severity`, `failure_modes`, `recommended_actions`, `kb_references`.*

-   `[x]` **4.1.2 Power & SMPS**
    -   `[x]` Add rules for Buck converter layout: hot loop minimization, placement of input/output caps.
    -   `[x]` Add rules for Inductor / FET / diode ratings: saturation current margin, voltage rating margin.
    -   `[x]` Add rules for Compensation network: presence when required, typical RC network structures.

-   `[x]` **4.1.3 Analog & Mixed-Signal**
    -   `[x]` Add rules for Op-amp stability: large capacitive loads, feedback network topology.
    -   `[x]` Add rules for ADC driver requirements: bandwidth vs sampling rate, RC anti-alias filters.
    -   `[x]` Add rules for Sensor front-end: high-impedance nodes, guard rings and shielding.

-   `[x]` **4.1.4 EMC / ESD**
    -   `[x]` Add rules for ESD protection on all external connectors.
    -   `[x]` Add rules for EMI filter placement (connector boundary).
    -   `[x]` Add rules for Return paths for high di/dt currents.
    -   `[x]` Add rules for Ground stitching near board edges and layer changes.

-   `[x]` **4.1.5 Thermal & Mechanical**
    -   `[x]` Add rules for Power density and copper area.
    -   `[x]` Add rules for Thermal via arrays.
    -   `[x]` Add rules for Connector mechanical reinforcement.

    > *When expanding the ontology: **preserve the current structure**, add rules to the `rules` array, and validate JSON.*

### 4.2 Expand Knowledge Base (`docs/AI_Hardware_Design_Review_KnowledgeBase.md`)

Goal: keep this file **readable but more complete**.

-   `[x]` Add Appendix A — High-Speed Signal Integrity (Transmission line basics, Z0, crosstalk, eye diagram, jitter concepts).
-   `[x]` Add Appendix B — Analog Design & Op-Amp Stability (Common-mode range, phase/gain margin, instability patterns).
-   `[x]` Add Appendix C — SMPS & Power Electronics (Buck/boost operation, layout dos and don’ts, compensation, ringing).

    > *Integrate references that connect knowledge base sections to ontology rules (e.g., “See rule `HS_DIFF_001` in ontology for automation”).*

### 4.3 Expand Examples (`examples/examples.json`)

Goal: provide more training/evaluation cases.

-   `[x]` Add multiple examples for High-speed domain (good/bad diff-pair routing, DDR termination mistakes).
-   `[x]` Add multiple examples for Power domain (correct vs incorrect decoupling, undersized inductors).
-   `[x]` Add multiple examples for Analog domain (Op-amp CM violation, noisy ADC input vs properly filtered).
-   `[x]` Add multiple examples for EMC/ESD domain (missing ESD on connectors, long trace between connector and ESD diode).

    > *Each example object includes: `id`, `title`, `description`, `triggered_rules`, `expected_issue`.*
    > *Preserve JSON validity and overall structure.*

### 4.4 Add Tests

-   `[x]` Create `tests/` directory.
-   `[x]` Add JSON schema for ontology (`tests/ontology_schema.json`).
-   `[x]` Add JSON schema for examples (`tests/examples_schema.json`).
    > *These schemas are for validating the structure of `ontology.json` and `examples.json`.*

### 4.5 Multi-Agent Reasoning Specification

-   `[x]` Create `docs/Multi_Agent_Reasoning_Spec.md`.
-   `[x]` Define agent roles (e.g., High-Speed SI Agent, Analog Agent).
-   `[x]` Describe what each agent reads.
-   `[x]` Specify which ontology rules each agent focuses on.
-   `[x]` Outline how agents combine results.

    > *This is mostly documentation / design; no code is required unless asked.*

---

## 5. How You (the AI) Should Proceed When Called via CLI

If a user says something like:

> “Read TODO.md and continue work on this project.”

Follow this procedure:

1.  **Read this file conceptually** to understand:
    -   Project context.
    -   Current files.
    -   Backlog.

2.  **Ask (or infer) which area to work on**:
    -   If the user specifies (“expand ontology for DDR”), do that.
    -   If not specified, choose a backlog item that adds obvious value (e.g., expand ontology in one domain).

3.  **When modifying a file**:
    -   State clearly which file you are updating.
    -   Output the **full new content** of that file only.
    -   Do not mix multiple file contents in one block unless the user explicitly wants that.

4.  **Maintain consistency**:
    -   Keep ontology rules aligned with KB sections.
    -   Keep examples aligned with ontology rules.

5.  **Stay conservative about deleting things**:
    -   Prefer appending/expanding over removing, unless explicitly told to refactor.

---

## 6. Notes to Future Me (the Human)

-   This project is intended to grow incrementally.
-   Don’t worry if the AI doesn’t “finish everything” in one go.
-   Use `git diff` to review changes suggested by the AI.
-   When something looks good, commit it and iterate.

---