# AI Hardware Design Review Framework

## TL;DR

```bash
git clone git@github.com:holla2040/ThomsonLint.git
cd ThomsonLint
```

**Fusion Electronics:**
1. Open your circuit design in Fusion Electronics.
2. From **both** the schematic editor and the board editor, run:
   ```
   RUN fusion-electronics-all.ulp
   ```
   One command per editor produces the JSON connectivity export, layer stackup JSON (board only), and high-resolution image renders. To customise output paths or DPI, run the three underlying ULPs (`fusion-electronics-export.ulp`, `fusion-electronics-stackup.ulp`, `fusion-electronics-images.ulp`) directly — see §7.

**KiCad 9:**
1. Run `python tools/kicad-export.py path/to/MyProject.kicad_pro`

**Then** run Claude Code from the repo root and type `/design-review` at the prompt:

**`/design-review`**

(Fallback if the skill is unavailable: `Read docs/REVIEWER_INSTRUCTIONS.md and follow it to review my design in exports/. Please begin the review.`)

(A pre-generated `review_instructions.txt` bundle is also produced for single-file upload to web AIs like Gemini, but that workflow has not been tested — see §5 "Running a Review".)

---

## Prerequisites

- **Python 3** (3.8+)
- **jsonschema** — required for JSON validation and report generation:
  ```bash
  pip install jsonschema
  ```

### Automated run script

On UNIX and UNIX-like operating systems (Linux, *BSD, MacOS etc), you can run the
`run_review.sh` script from the shell with auto-detection of the project name from the `exports/` directory:
   ```bash
   ./run_review.sh
   ```

If there are more than one project outputs in the directory, then specify it explicitly on the command line:
   ```bash
   ./run_review.sh MySpecialProject
   ```

It require the `jq` and `claude` shell commands. To install these on MacOS using `brew`: `brew install jq claude-code`.

## 1. Project Overview

This repository hosts a knowledge and rule framework designed to empower AI models with the specialized expertise required for comprehensive hardware design reviews. The goal is to provide a structured, machine-readable, and human-readable set of resources that enable an AI to analyze and identify potential issues in hardware designs, including schematics and PCB layouts.

The framework is built upon three core components:

1.  **Ontology (`ontology/ontology.json`):** A machine-readable JSON file that defines a rich set of rules, domains, severity levels, and failure modes for hardware design. This forms the core of the AI's knowledge base.
2.  **Knowledge Base (`docs/AI_Hardware_Design_Review_KnowledgeBase.md`):** A human-readable Markdown file that provides detailed explanations, appendices, and context for the rules defined in the ontology.
3.  **Examples (`examples/examples.json`):** A collection of practical examples, both good and bad, that map to the rules in the ontology. These can be used for training, testing, and validating the AI's understanding of the rules.

## 2. Why "ThomsonLint"?

The name pays homage to **J.J. Thomson**, who discovered the electron in 1897 through his experiments with cathode rays at the Cavendish Laboratory in Cambridge, England. He demonstrated that cathode rays were composed of negatively charged particles much smaller than atoms, which he called "corpuscles" (later renamed electrons). He won the Nobel Prize in Physics in 1906 for this discovery.

Just as Thomson revealed the fundamental building blocks of electrical circuits, this project aims to uncover the fundamental issues in hardware designs—catching the small problems that can have big consequences.

## 3. Project Status

The initial development phase of this project is complete. All tasks outlined in the `TODO.md` file have been implemented, resulting in a comprehensive and well-structured framework for AI-assisted hardware design review.

## 4. Repository Contents

The repository is organized as follows:

-   `README.md`: This file, providing an overview of the project.
-   `LICENSE`: The project's license.
-   `CONTRIBUTING.md`: Guidelines for contributing to the project.
-   `TODO.md`: The completed task list for the initial development phase.
-   `ontology/ontology.json`: The core machine-readable ontology of hardware design rules.
-   `examples/examples.json`: A set of example hardware design scenarios for training and testing.
-   `docs/REVIEWER_INSTRUCTIONS.md`: The single source of truth for how a review is conducted; consumed by both Claude Code and the bundled web-AI workflow.
-   `docs/AI_Hardware_Design_Review_KnowledgeBase.md`: A detailed, human-readable knowledge base.
-   `docs/KiCad_Review_Guide.md`: Usage guide for the KiCad 9 export workflow.
-   `docs/Multi_Agent_Reasoning_Spec.md`: A specification for a conceptual multi-agent reasoning architecture.
-   `tests/ontology_schema.json`: A JSON schema for validating `ontology/ontology.json`.
-   `tests/examples_schema.json`: A JSON schema for validating `examples/examples.json`.
-   `tests/findings_schema.json`: A JSON schema for validating findings JSON files produced by a review.
-   `tests/sample_findings.json`: A worked example demonstrating issues, verified_checks, cross_checks, and image / stackup evidence rows.
-   `tools/fusion-electronics-all.ulp`: Wrapper ULP — recommended entry point. Chains the three exporters below in the right order based on the current editor, so the user runs only one command per editor.
-   `tools/fusion-electronics-export.ulp`: ULP that exports schematic and board connectivity/placement to JSON. Run from each editor.
-   `tools/fusion-electronics-stackup.ulp`: ULP that exports the layer stack (copper ordering, used-vs-unused layers) to JSON. Run from the board editor.
-   `tools/fusion-electronics-images.ulp`: ULP that renders the schematic sheets and per-layer board images as high-resolution PNGs (300 DPI schematic / 1200 DPI board defaults). Run from each editor.
-   `tools/kicad-export.py`: Standalone Python script to export KiCad 9 designs for review.
-   `tools/yt-transcript.py`: Pulls a YouTube video transcript (via yt-dlp) with creator metadata in the header, as raw material for knowledge-base additions. See CLAUDE.md "Ingesting YouTube Content" — KB additions derived from a video must credit the creator (their homepage info feeds the `**Source:**` line).
-   `tools/validate_findings.py`: Coverage validator — schema-checks the findings JSON, lists every input in `exports/` not cited in any `evidence[].source`, and flags missing required fields. Mandatory gate before generating the HTML report.
-   `tools/gen_report.py`: Generates the self-contained HTML review report from findings JSON; embeds image evidence as inline thumbnails.
-   `validate_json.py`: A Python script for validating the JSON files against their schemas.
-   `gen_context.sh`: A bash script to generate the review instructions file.
-   `review_instructions.txt`: Pre-generated file containing the complete knowledge base and AI instructions. Ready to use immediately.

## 5. Running a Review

This section is for the person reviewing a board. It lists the exact inputs the AI needs and the exact outputs a complete review produces. Claude Code is the only driver path that has been tested end-to-end; a single-file-upload bundle is provided for web AIs but that workflow has not been validated.

### Inputs

Reviewer procedure (read by the AI):

-   `docs/REVIEWER_INSTRUCTIONS.md` — the single source of truth for how a review is conducted. Step 1 of this file directs the AI to read the framework knowledge base.

Framework knowledge (loaded by the AI per Step 1 of `REVIEWER_INSTRUCTIONS.md`):

-   `ontology/ontology.json` — rule definitions
-   `examples/examples.json` — worked examples mapped to rules
-   `docs/AI_Hardware_Design_Review_KnowledgeBase.md` — explanations and appendices

Design data (drop into `exports/`):

-   `<project>-thomson-export-sch.json` — schematic export (Fusion Electronics ULP or `tools/kicad-export.py`)
-   `<project>-thomson-export-brd.json` — board export (same source as above)
-   `<project>-thomson-export-stack.json` — layer stack (Fusion `fusion-electronics-stackup.ulp`); copper ordering + used-vs-unused layers
-   `<project>-img-sch-p<N>.png` — one PNG per schematic sheet at 300 DPI (Fusion `fusion-electronics-images.ulp`)
-   `<project>-img-silk-top.png`, `<project>-img-silk-bot.png` — silkscreen renders at 1200 DPI
-   `<project>-img-cu-L<num>-<name>.png` — per-copper-layer renders at 1200 DPI (traces + filled pours + airwires + restrict zones)
-   `*.pdf` / `*.PDF` — datasheets for critical ICs (power converters, MCUs, transceivers), plus any stackup or pinout PDFs

Every input above is hard-gated by `tools/validate_findings.py`: any file present but not cited in some `evidence[].source` causes review failure. The case-insensitive match also catches uppercase `.PDF` / `.PNG`.

### Driver path (tested)

**Claude Code (CLI, in this repo)** — read the reviewer instructions directly. From the repo root run `claude` and type:

> `/design-review`

(Fallback: `Read docs/REVIEWER_INSTRUCTIONS.md and follow it to review my design in exports/. Please begin the review.`)

See §7 "Using with Claude Code" for the full step-by-step.

### Driver path (untested)

**Single-file upload to a web AI (e.g., Gemini, Claude.ai, ChatGPT)** — the repo also produces `review_instructions.txt`, a single concatenation of ontology + examples + KB. Uploading this file along with the design exports to a web AI is *possible* but has not been tested by the maintainers; treat as experimental. See §6.1 for the quick-start. Do **not** point Claude Code at this bundle — it exceeds the per-file `Read` limit, and Claude Code should read the source files directly anyway.

### Outputs

A complete review writes to `exports/`:

-   `<project>-findings.json` — structured findings, schema in `tests/findings_schema.json`
-   `<project>-review.html` — interactive Open / Accept / Ignore checklist generated by:

    ```bash
    python tools/gen_report.py exports/<project>-findings.json --output exports/
    ```

    Triage status is persisted in browser localStorage.

The findings JSON and HTML report sit alongside the schematic/board exports so the review trail stays with the design.

---

## 6. How to Use

This framework serves two types of users:
- **Design Reviewers**: Engineers who want to review their circuit designs using AI
- **Contributors**: Developers who want to extend the knowledge base with new rules

---

### 6.1. For Web-Based AI Reviewers — Untested

> **Status: experimental.** This path has not been validated by the maintainers. The tested workflow is Claude Code (§7). The instructions below are provided as a starting point if you want to try a web AI.

If you want to try reviewing a hardware design with a web AI that takes a single file upload, you don't need to clone or run anything:

1.  **Download `review_instructions.txt`** from this repository (it's pre-generated and always up-to-date).
2.  **Open an AI assistant with file upload support.**
3.  **Upload two things:**
    -   The `review_instructions.txt` file
    -   Your design files (schematic images, PCB layout screenshots, etc.)
4.  **Type:** `Please begin the review.`

The AI should perform a pre-review assessment, ask for any missing information (datasheets, component values, stackup details), and then attempt a review with rule references. Output quality, completeness, and the ability to produce the structured findings JSON / HTML report have not been verified on this path.

---

### 6.2. For Contributors

If you want to extend the knowledge base or customize the rules:

#### Clone the Repository
```bash
git clone <repository-url>
cd ThomsonLint
```

#### Validate JSON Files
```bash
pip install jsonschema  # if not installed
python validate_json.py
```

#### Extend the Framework

1.  **Modify the JSON files:** Add new entries to `ontology/ontology.json` or `examples/examples.json` following the existing structure.
2.  **Update the knowledge base:** If necessary, add new sections to `docs/AI_Hardware_Design_Review_KnowledgeBase.md`.
3.  **Credit your sources:** If the content is derived from external material (a video, article, checklist, or another person's work), add a `**Source:** <author>, <publication or channel>, <URL>` line near the top of the new KB section. Content providers supply valuable knowledge to this project and their efforts are acknowledged in the knowledge base itself — see Appendix J and Appendix I.4 for the expected style, and CONTRIBUTING.md for details.
4.  **Validate your changes:** Run `python validate_json.py`.
5.  **Regenerate the review file:**
    ```bash
    ./gen_context.sh > review_instructions.txt
    ```

---

## 7. Using with Claude Code

Claude Code is the tested driver for this framework. It reads the exported design data and the framework's source files (`ontology/ontology.json`, `examples/examples.json`, `docs/AI_Hardware_Design_Review_KnowledgeBase.md`) directly from the repository — no file uploads, no `review_instructions.txt` (the bundle exists for the experimental web-AI path in §6.1, and exceeds Claude Code's per-file `Read` limit).

### Prerequisites

- Claude Code CLI installed and authenticated
- ThomsonLint repository cloned locally
- Design exported from Fusion Electronics or KiCad 9 (see below)

### Step 1: Export Design Data from Fusion Electronics

The simplest path is the wrapper ULP — one command per editor, no flags:

1.  **Open your design in Fusion Electronics.**
2.  **From the Schematic Editor**, run:
    ```
    RUN fusion-electronics-all.ulp
    ```
    This chains: `fusion-electronics-export.ulp` → `fusion-electronics-images.ulp`. Produces `<design>-thomson-export-sch.json` and one `<design>-img-sch-p<N>.png` per sheet (300 DPI).
3.  **Switch to the Board Editor** (PCB) and run the same command:
    ```
    RUN fusion-electronics-all.ulp
    ```
    This chains: `fusion-electronics-export.ulp` → `fusion-electronics-stackup.ulp` → `fusion-electronics-images.ulp`. Produces `<design>-thomson-export-brd.json`, `<design>-thomson-export-stack.json`, `<design>-img-silk-top.png`, `<design>-img-silk-bot.png`, and one `<design>-img-cu-L<num>-<name>.png` per used copper layer (1200 DPI).

The wrapper detects which editor it's in and runs the right chain. All four ULPs (wrapper plus three children) live under `tools/` and write to `<repo>/exports/` automatically (path derived from `argv[0]`). The wrapper uses each child ULP's default output path and DPI; for granular control, run the children directly — see "Individual ULPs" below.

The schematic JSON export contains components, nets, pin connectivity, and signal analysis. The board JSON contains placement coordinates, trace routing, board geometry, and layout analysis. The stackup JSON contains the physical copper-layer ordering plus the full layer table. The image PNGs are visual evidence — qualitative inputs only; never derive distances or trace widths from them (the reviewer instructions enforce this rule).

#### Individual ULPs (advanced)

If you need to override the output path, use a file-save dialog, or change the image DPI, run the children directly. Each child shares the same flag set:

| Flag | Description |
|------|-------------|
| `-d` | Opens a file-save dialog so you can choose the output location interactively |
| `-o <prefix>` | Writes the output(s) using the specified prefix directly |
| `-r <dpi>` | Image ULP only: override per-mode DPI (50–2400). Default is 300 (schematic) / 1200 (board). Use e.g. `-r 600` if you want smaller board PNGs for a coarse-pitch design. |

Examples:
```
RUN fusion-electronics-export.ulp -d
RUN fusion-electronics-export.ulp -o C:\Users\me\Desktop\my-export.json
RUN fusion-electronics-images.ulp -r 600          # smaller board PNGs
```

To replicate what `fusion-electronics-all.ulp` does manually, run from the schematic editor:

```
RUN fusion-electronics-export.ulp                 # connectivity / placement JSON
RUN fusion-electronics-images.ulp                 # PNG renders
```

…and from the board editor:

```
RUN fusion-electronics-export.ulp                 # connectivity / placement JSON
RUN fusion-electronics-stackup.ulp                # layer stack JSON
RUN fusion-electronics-images.ulp                 # PNG renders (run last — it terminates the chain)
```

### Step 1 (Alternative): Export Design Data from KiCad 9

If your design is in KiCad 9, use the standalone Python exporter instead:

```bash
python tools/kicad-export.py path/to/MyProject.kicad_pro
```

This generates both `-thomson-export-sch.json` and `-thomson-export-brd.json` files in the `exports/` directory. Use `--output <dir>` to specify a different output directory.

The script parses KiCad 9 S-expression files directly — no KiCad installation required, Python 3.6+ standard library only. It handles hierarchical multi-sheet schematics, reads net classes from the project file, and classifies signals (power, ground, clock, differential pairs with interface detection for USB, CAN, Ethernet, HDMI, LVDS, PCIe, SATA, MIPI).

See [`docs/KiCad_Review_Guide.md`](docs/KiCad_Review_Guide.md) for full details on the KiCad export format.

### Step 2: Add Datasheets and Supporting Files

Place any datasheets or other reference documents into the same `exports/` directory alongside the ULP-generated artifacts:

```
exports/
  Pendant_2_I_O_Schematic-thomson-export-sch.json
  Pendant_2_I_O_Board-thomson-export-brd.json
  Pendant_2_I_O_Board-thomson-export-stack.json
  Pendant_2_I_O_Schematic-img-sch-p1.png
  Pendant_2_I_O_Board-img-silk-top.png
  Pendant_2_I_O_Board-img-silk-bot.png
  Pendant_2_I_O_Board-img-cu-L1-Top.png
  Pendant_2_I_O_Board-img-cu-L2-GND.png
  Pendant_2_I_O_Board-img-cu-L303-POWER.png
  Pendant_2_I_O_Board-img-cu-L304-Bottom.png
  TPS54302_datasheet.pdf
  connector_pinout.pdf
```

Claude Code can read PDFs and PNGs directly. Providing datasheets for critical ICs (power converters, MCUs, transceivers) up front saves back-and-forth and produces a more thorough review. The stackup JSON and per-layer PNGs let the reviewer make layer-aware claims (return-path adjacency, plane-split crossing, pour integrity) without having to ask you for stackup specs.

### Step 3: Start a Claude Code Review Session

Open a terminal in the ThomsonLint directory and start Claude Code:

```bash
cd ThomsonLint
claude
```

Then start the review using the project skill:

**`/design-review`**

(Fallback if the skill is unavailable: `Read docs/REVIEWER_INSTRUCTIONS.md and follow it to review my design in exports/. Please begin the review.`)

Claude Code will:
1. Read `docs/REVIEWER_INSTRUCTIONS.md` (the reviewer procedure) and, per its Step 1, the framework knowledge base — `ontology/ontology.json`, `examples/examples.json`, and `docs/AI_Hardware_Design_Review_KnowledgeBase.md`
2. Read the `-sch.json`, `-brd.json`, and `-stack.json` exports, the layer/silk/schematic PNGs, plus any datasheet PDFs from `exports/`
3. Perform a pre-review assessment and ask for any missing information (datasheets, stackup details, etc.)
4. Run through all applicable rules and report issues with specific `rule_id` citations, recording datasheet verifications in `verified_checks[]` and design-wide analyses in `cross_checks[]`
5. Write findings to `exports/<project>-findings.json`, run `tools/validate_findings.py` (mandatory coverage gate), and produce `exports/<project>-review.html` via `tools/gen_report.py` (see §5 "Outputs")

It is also possible to run this whole process automatically on a UNIX or UNIX-Like operating system
by running the `run_review.sh` script:

```bash
cd ThomsonLint
run_review.sh
```

### Step 4: Provide Additional Context (if asked)

Claude may ask for:
- Datasheets for critical ICs (it will try to web-search first)
- Component ratings not captured in the schematic attributes
- PCB stackup and manufacturing specs
- Functional descriptions for non-obvious signals or connectors

Answer these in the chat and Claude will proceed with the full review.

### What the Export Files Contain

**Schematic export** (`*-thomson-export-sch.json`):
- Project info (name, variant, sheet count)
- Components with ref, value, package, type classification, attributes
- Net connectivity with pin directions and net classes
- Signal classification (power, ground, clock, differential pairs)
- Analysis: floating inputs, single-pin nets, voltage guesses

**Board export** (`*-thomson-export-brd.json`):
- Component placement (X/Y coordinates, rotation, top/bottom side)
- Board geometry (dimensions, layer count, holes)
- Signal routing (trace lengths, widths, via counts, segment counts)
- Full trace segments for high-speed/clock/differential nets
- Copper pours and ground plane layers
- Components near board edges

---

## 8. Development Setup

Development (including Claude Code) runs on an **Ubuntu 24.04** host. The repository can be mounted into **Windows 11 WSL** via SSHFS so that Fusion Electronics (running on Windows) can execute the ULP exporter directly:

```bash
sshfs -o allow_other,default_permissions host:/home/user/ThomsonLint ThomsonLint/
```

The ULP auto-detects its own location and writes exports to `<repo>/exports/`, so no path configuration is needed regardless of where the repository is cloned.

## 9. Future Work

While the initial development is complete, the framework is designed for continuous improvement. Future work could include:

-   Expanding the ontology with even more specialized rules.
-   Adding more complex and nuanced examples.
-   Integrating the framework with actual AI models and hardware design tools.
