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
-   `gen_context.sh`: A bash script to generate a consolidated knowledge base file for use with Gemini.

## 5. How to Use

### 5.1. Validation

To ensure the integrity and correctness of the JSON files (`ontology.json` and `examples.json`), a validation script is provided. To use it, follow these steps:

1.  **Install dependencies:**
    ```bash
    pip install jsonschema
    ```
2.  **Run the validation script:**
    ```bash
    python validate_json.py
    ```
    The script will output the validation status for each file.

### 5.2. Extending the Framework

The framework is designed to be extensible. To add new rules, examples, or knowledge:

1.  **Modify the JSON files:** Add new entries to `ontology/ontology.json` or `examples/examples.json` following the existing structure.
2.  **Update the knowledge base:** If necessary, add new sections or appendices to `docs/AI_Hardware_Design_Review_KnowledgeBase.md` to provide context for the new rules.
3.  **Validate your changes:** Run the `validate_json.py` script to ensure your changes are syntactically correct.

### 5.3. Using with Google Gemini (Web Interface)

You can use this framework to have an interactive, AI-assisted hardware design review. The included script now instructs Gemini to first assess if it has enough information before starting, making the review more thorough.

#### **Step 1: Generate the Context File**

A helper script `gen_context.sh` is provided to automatically consolidate the knowledge base and instructions into a single file.

1.  **Run the script** from your terminal and redirect the output to a file named `gemini_context.txt`:
    ```bash
    ./gen_context.sh > gemini_context.txt
    ```
2.  **Open the newly created `gemini_context.txt`** file in a text editor.

#### **Step 2: Start the Review Session in Gemini**

1.  Open your web browser and go to **[https://gemini.google.com/](https://gemini.google.com/)**.
2.  In the prompt box, click the **upload button** (usually a paperclip or a plus symbol `+`) and upload the `gemini_context.txt` file you just created.
3.  In the same prompt, upload your design files (e.g., schematic images, PCB layout images).
4.  Once all files are uploaded, type a simple starting command in the prompt box:
    ```
    Please begin the review.
    ```
5.  Press **Enter**.

#### **Step 3: Respond to the AI's Pre-Review Assessment**

Gemini will now follow the instructions inside `gemini_context.txt`. Its first step is to perform a **Pre-Review Assessment**.

*   It will analyze your request and the files you uploaded.
*   If critical information (like datasheets, component ratings, or PCB stackup details) is missing, **it will ask you to provide it.**

This is your opportunity to provide the specific details it needs. You can copy-paste text from datasheets or just write the component values directly into the chat.

#### **Step 4: Receive the Comprehensive Review**

Once Gemini has the information it needs, it will automatically proceed with the full, comprehensive review based on the rules from the knowledge base. It will output a list of potential issues, each with a corresponding `rule_id` for reference.

## 6. Future Work

While the initial development is complete, the framework is designed for continuous improvement. Future work could include:

-   Expanding the ontology with even more specialized rules.
-   Adding more complex and nuanced examples.
-   Integrating the framework with actual AI models and hardware design tools.