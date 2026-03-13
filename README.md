# AI Hardware Design Review Framework

## TL;DR

```bash
git clone git@github.com:holla2040/ThomsonLint.git
cd ThomsonLint
```

1. Open your circuit design in Fusion Electronics
2. Run `tools/fusion-electronics-export.ulp` in both the schematic and board layout workspace
3. Run Claude Code and enter this prompt:

**`Read the review instructions in review_instructions.txt, then review my design using the exported JSON files and datasheets in exports/. Please begin the review.`**

---

## Prerequisites

- **Python 3** (3.8+)
- **jsonschema** — required for JSON validation and report generation:
  ```bash
  pip install jsonschema
  ```

## 1. Project Overview

This repository hosts a knowledge and rule framework designed to empower AI models (like Gemini) with the specialized expertise required for comprehensive hardware design reviews. The goal is to provide a structured, machine-readable, and human-readable set of resources that enable an AI to analyze and identify potential issues in hardware designs, including schematics and PCB layouts.

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
-   `docs/AI_Hardware_Design_Review_KnowledgeBase.md`: A detailed, human-readable knowledge base.
-   `docs/Multi_Agent_Reasoning_Spec.md`: A specification for a conceptual multi-agent reasoning architecture.
-   `tests/ontology_schema.json`: A JSON schema for validating `ontology/ontology.json`.
-   `tests/examples_schema.json`: A JSON schema for validating `examples/examples.json`.
-   `validate_json.py`: A Python script for validating the JSON files against their schemas.
-   `gen_context.sh`: A bash script to generate the review instructions file.
-   `review_instructions.txt`: Pre-generated file containing the complete knowledge base and AI instructions. Ready to use immediately.

## 5. How to Use

This framework serves two types of users:
- **Design Reviewers**: Engineers who want to review their circuit designs using AI
- **Contributors**: Developers who want to extend the knowledge base with new rules

---

### 5.1. For Design Reviewers (Quick Start)

If you just want to review your hardware design, you don't need to clone or run anything.

1.  **Download `review_instructions.txt`** from this repository (it's pre-generated and always up-to-date).
2.  **Go to [https://gemini.google.com/](https://gemini.google.com/)** (or another AI with file upload support).
3.  **Upload two things:**
    -   The `review_instructions.txt` file
    -   Your design files (schematic images, PCB layout screenshots, etc.)
4.  **Type:** `Please begin the review.`

The AI will perform a pre-review assessment, ask for any missing information (datasheets, component values, stackup details), and then provide a comprehensive review with specific rule references.

---

### 5.2. For Contributors

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
3.  **Validate your changes:** Run `python validate_json.py`.
4.  **Regenerate the review file:**
    ```bash
    ./gen_context.sh > review_instructions.txt
    ```

---

### 5.3. Using with AI (Detailed Workflow)

#### **Step 1: Upload Files**

1.  Open **[https://gemini.google.com/](https://gemini.google.com/)** (or Claude, ChatGPT, etc.).
2.  Upload `review_instructions.txt` along with your design files (schematic images, PCB layout images).
3.  Type: `Please begin the review.`

#### **Step 2: Respond to the Pre-Review Assessment**

The AI will analyze your files and ask for missing information:
*   Datasheets for critical ICs
*   Component ratings (inductor saturation current, fuse ratings, etc.)
*   PCB stackup details

Provide these details via copy-paste or direct answers.

#### **Step 3: Receive the Review**

The AI will output a list of potential issues, each citing a specific `rule_id` from the knowledge base.

## 6. Using with Claude Code

Claude Code can perform ThomsonLint reviews directly from the terminal, reading the exported design data and knowledge base from the repository. No file uploads needed.

### Prerequisites

- Claude Code CLI installed and authenticated
- ThomsonLint repository cloned locally
- Fusion Electronics design exported (see below)

### Step 1: Export Design Data from Fusion Electronics

The ULP exporter runs inside Fusion Electronics and must be run **twice** — once from each editor context:

1. **Open your design in Fusion Electronics**
2. **From the Schematic Editor**, run the ULP:
   ```
   RUN fusion-electronics-export.ulp
   ```
   This writes `<design_name>-thomson-export-sch.json` to the `exports/` directory.
3. **Switch to the Board Editor** (PCB), run the same ULP:
   ```
   RUN fusion-electronics-export.ulp
   ```
   This writes `<design_name>-thomson-export-brd.json` to the `exports/` directory.

The ULP auto-detects which editor you're in and exports the appropriate data. The output path is derived automatically from the ULP's own location (`argv[0]`): since the script lives at `<repo>/tools/fusion-electronics-export.ulp`, it walks up one directory to find the repo root and writes to `<repo>/exports/`. No hardcoded paths or configuration needed — it works wherever the repo is cloned.

The schematic export contains components, nets, pin connectivity, and signal analysis. The board export contains placement coordinates, trace routing, board geometry, and layout analysis.

### Step 2: Add Datasheets and Supporting Files

Place any datasheets, stackup specs, or other reference documents into the same `exports/` directory:

```
exports/
  Pendant_2_I_O_Schematic-thomson-export-sch.json
  Pendant_2_I_O_Board-thomson-export-brd.json
  TPS54302_datasheet.pdf
  stackup_4layer.pdf
  connector_pinout.pdf
```

Claude Code can read PDFs directly. Providing datasheets for critical ICs (power converters, MCUs, transceivers) up front saves back-and-forth and produces a more thorough review.

### Step 3: Start a Claude Code Review Session

Open a terminal in the ThomsonLint directory and start Claude Code:

```bash
cd ThomsonLint
claude
```

Then prompt Claude to perform the review:

**`Read the review instructions in review_instructions.txt, then review my design using the exported JSON files and datasheets in exports/. Please begin the review.`**

Claude Code will:
1. Read the ThomsonLint knowledge base, ontology, and examples from `review_instructions.txt`
2. Read both the `-sch.json` and `-brd.json` export files from `exports/`
3. Perform a pre-review assessment and ask for any missing information (datasheets, stackup details, etc.)
4. Run through all applicable rules and report issues with specific `rule_id` citations

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

## 7. Development Setup

Development (including Claude Code) runs on an **Ubuntu 24.04** host. The repository can be mounted into **Windows 11 WSL** via SSHFS so that Fusion Electronics (running on Windows) can execute the ULP exporter directly:

```bash
sshfs -o allow_other,default_permissions host:/home/user/ThomsonLint ThomsonLint/
```

The ULP auto-detects its own location and writes exports to `<repo>/exports/`, so no path configuration is needed regardless of where the repository is cloned.

## 8. Future Work

While the initial development is complete, the framework is designed for continuous improvement. Future work could include:

-   Expanding the ontology with even more specialized rules.
-   Adding more complex and nuanced examples.
-   Integrating the framework with actual AI models and hardware design tools.
