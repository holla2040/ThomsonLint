# Contributing to the AI Hardware Design Review Knowledge Base

Thanks for your interest in improving this project!

This repository is intended to be a **living knowledge base and ontology** for AI-assisted hardware design review. Contributions from experienced hardware engineers, EDA tool builders, and ML practitioners are welcome.

---

## Ways to Contribute

1. **Add or refine rules**
   - Propose new rules for domains like:
     - Power electronics
     - RF / microwave
     - Automotive / aerospace
     - Safety-critical systems
   - Improve descriptions, failure modes, or recommended actions.

2. **Extend the ontology**
   - Add more detailed fields to `ontology/ontology.json`.
   - Introduce new domains, component classes, or condition patterns.

3. **Add more examples**
   - Contribute real-world or synthesized examples to `examples/examples.json`.
   - Each example should:
     - Describe the pattern.
     - List triggered rules.
     - Include the expected AI issue output.

4. **Improve documentation**
   - Expand the main knowledge base in `docs/AI_Hardware_Design_Review_KnowledgeBase.md`.
   - Add domain-specific appendices or diagrams.

---

## Guidelines

- **Clarity first:** Rules and descriptions should be unambiguous and grounded in sound engineering practice.
- **No proprietary info:** Do not add confidential or NDA-bound material.
- **Keep it tool-neutral:** Avoid tying rules to any single EDA tool or vendor.
- **Maintain machine-friendliness:** When editing the ontology or examples, ensure JSON remains valid and schemas are preserved.
- **Acknowledge your sources:** Content providers supply valuable knowledge to this project, and their efforts deserve credit. Any knowledge-base addition derived from external material (video, article, checklist, book, or another person's work) must include a `**Source:**` attribution line near the top of the relevant section in `docs/AI_Hardware_Design_Review_KnowledgeBase.md`, in the form `**Source:** <author>, <publication or channel>, <URL>`. See Appendix J (Hans Rosenberg, hans-rosenberg.com) and Appendix I.4 (John Teel, Predictable Designs, https://www.youtube.com/@PredictableDesigns) for the expected style.

---

## Process

1. Fork the repository.
2. Create a feature branch.
3. Make your changes:
   - Update relevant files (`docs/`, `ontology/`, `examples/`).
4. Run any available validation scripts (if present in future).
5. Open a pull request with:
   - A clear description of your changes.
   - Rationale and references, if applicable.

---

## Code of Conduct

Be respectful, technically constructive, and open to feedback. The goal is to build a robust, high-quality shared knowledge base.


