# AI Hardware Design Review Framework

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

## 6. Future Work

While the initial development is complete, the framework is designed for continuous improvement. Future work could include:

-   Expanding the ontology with even more specialized rules.
-   Adding more complex and nuanced examples.
-   Integrating the framework with actual AI models and hardware design tools.