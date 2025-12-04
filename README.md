# AI Hardware Design Review Framework

## 1. Project Overview

This repository hosts a knowledge and rule framework designed to empower AI models (like Gemini) with the specialized expertise required for comprehensive hardware design reviews. The goal is to provide a structured, machine-readable, and human-readable set of resources that enable an AI to analyze and identify potential issues in hardware designs, including schematics and PCB layouts.

The framework is built upon three core components:

1.  **Ontology (`ontology/ontology.json`):** A machine-readable JSON file that defines a rich set of rules, domains, severity levels, and failure modes for hardware design. This forms the core of the AI's knowledge base.
2.  **Knowledge Base (`docs/AI_Hardware_Design_Review_KnowledgeBase.md`):** A human-readable Markdown file that provides detailed explanations, appendices, and context for the rules defined in the ontology.
3.  **Examples (`examples/examples.json`):** A collection of practical examples, both good and bad, that map to the rules in the ontology. These can be used for training, testing, and validating the AI's understanding of the rules.

## 2. Project Status

The initial development phase of this project is complete. All tasks outlined in the `TODO.md` file have been implemented, resulting in a comprehensive and well-structured framework for AI-assisted hardware design review.

## 3. Repository Contents

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

## 4. How to Use

### 4.1. Validation

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

### 4.2. Extending the Framework

The framework is designed to be extensible. To add new rules, examples, or knowledge:

1.  **Modify the JSON files:** Add new entries to `ontology/ontology.json` or `examples/examples.json` following the existing structure.
2.  **Update the knowledge base:** If necessary, add new sections or appendices to `docs/AI_Hardware_Design_Review_KnowledgeBase.md` to provide context for the new rules.
3.  **Validate your changes:** Run the `validate_json.py` script to ensure your changes are syntactically correct.

## 5. Future Work

While the initial development is complete, the framework is designed for continuous improvement. Future work could include:

-   Expanding the ontology with even more specialized rules.
-   Adding more complex and nuanced examples.
-   Integrating the framework with actual AI models and hardware design tools.