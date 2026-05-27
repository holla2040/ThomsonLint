#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PHASES = {
    1: "Ingest ThomsonLint Workflow",
    2: "Inspect Inputs and Datasheets",
    3: "Setup and Tool Preflight",
    4: "Run Integrated Converter",
    5: "Inspect Findings Framework",
    6: "Full BOM Datasheet Retrieval",
    7: "Enforce Image Review Gate",
    8: "Review Schematic Evidence FULL",
    9: "Full Board/Layout JSON Evaluation",
    10: "Review Stackup and Manufacturing Evidence FULL",
    11: "Review DFM and Manufacturing Specifications",
    12: "Review BOM and Component Evidence FULL",
    13: "Review Image Evidence FULL",
    14: "Review Datasheet Evidence FULL",
    15: "Review Aerospace and Process Metadata",
    16: "Cross-Source Consistency Review",
    17: "Pre-Findings Gate Check",
    18: "Candidate Finding Development",
    19: "Write Findings JSON",
    20: "Validate and Repair Findings",
    21: "Generate Report",
    22: "Final Summary",
}

PHASE_ARTIFACTS = {
    # Phases 1, 2, 5: No external artifact — checkpoint row itself is the deliverable
    1: [],
    2: [],
    3: ["exports/tool-preflight-status.json"],
    4: [
        "exports/{project}-bom.json",
        "exports/{project}-thomson-export-sch.json",
        "exports/{project}-thomson-export-brd.json",
        "exports/{project}-thomson-export-stack.json",
    ],
    5: [],
    6: [
        "exports/datasheets/datasheet_manifest.jsonl",
        "exports/datasheets/datasheet_manifest_validation.json",
    ],
    7: ["exports/{project}-image-evidence-inventory.json"],
    8: [
        "exports/{project}-schematic-evidence-inventory.json",
        "exports/{project}-schematic-evidence-inventory-validation.json"
    ],
    9: [
        "exports/{project}-board-evidence-inventory.json",
        "exports/{project}-board-evidence-inventory-validation.json",
    ],
    10: [
        "exports/{project}-stackup-evidence-review.json",
        "exports/{project}-stackup-evidence-review-validation.json",
    ],
    11: [
        "exports/{project}-dfm-evidence-inventory.json",
        "exports/{project}-dfm-evidence-inventory-validation.json"
    ],
    12: [
        "exports/{project}-bom-evidence-inventory.json",
        "exports/{project}-bom-evidence-inventory-validation.json"
    ],
    13: [
        "exports/{project}-image-evidence-inventory.json",
        "exports/{project}-image-evidence-review.json",
        "exports/{project}-image-evidence-review-validation.json"
    ],
    14: [
        "exports/{project}-datasheet-evidence-review.json",
        "exports/{project}-datasheet-evidence-review-validation.json"
    ],
    15: [
        "exports/{project}-aerospace-evidence-inventory.json",
        "exports/{project}-aerospace-evidence-inventory-validation.json"
    ],
    16: [
        "exports/{project}-cross-source-review.json",
        "exports/{project}-cross-source-review-validation.json"
    ],
    17: ["exports/{project}-pre-findings-gate.json"],
    18: ["exports/{project}-candidate-findings.json"],
    19: ["exports/{project}-findings.json"],
    20: ["exports/{project}-findings.json"],
    21: [
        "exports/{project}-review.html",
        "exports/{project}-report-generation-validation.json",
    ],
    22: [
        "exports/{project}-review.html",
        "exports/{project}-report-generation-validation.json",
        "exports/{project}-phase-checkpoints.jsonl",
    ],
}

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def render(paths: list[str], project: str) -> list[str]:
    return [p.format(project=project) for p in paths]

def load_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            raise SystemExit(f"invalid JSONL row {line_no} in {path}: {exc}")
        rows.append(row)
    return rows

def artifact_passes(path: Path, phase: int) -> tuple[bool, list[str]]:
    blockers: list[str] = []

    if not path.exists():
        return False, [f"missing artifact: {path}"]

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return False, [f"invalid JSON artifact {path}: {exc}"]

        # Phase 3: tool-preflight-status.json uses overall_pass at top level
        if phase == 3 and path.name == "tool-preflight-status.json":
            if data.get("overall_pass") is not True:
                blockers.append(f"{path} overall_pass is not true")
            return not blockers, blockers

        # Universal rule: any -validation.json must have overall_pass=true at the top level.
        # Exception: pre-findings-gate.json uses overall_gate_pass (different semantic).
        if path.name.endswith("-validation.json") and data.get("overall_pass") is not True:
            blockers.append(f"{path} overall_pass is not true (expected top-level bool true)")
        if path.name.endswith("-pre-findings-gate.json") and data.get("overall_gate_pass") is not True:
            blockers.append(f"{path} overall_gate_pass is not true")
        # Phase 7: image-evidence-inventory.json (no separate validation artifact) uses overall_pass
        if phase == 7 and path.name.endswith("-image-evidence-inventory.json") and data.get("overall_pass") is not True:
            blockers.append(f"{path} overall_pass is not true")

    return not blockers, blockers

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="example")
    ap.add_argument("--phase", type=int, required=True)
    ap.add_argument("--exports", default="exports")
    ap.add_argument("--mode", choices=["append-if-missing", "replace"], default="append-if-missing")
    args = ap.parse_args()

    if args.phase not in PHASES:
        raise SystemExit(f"unknown phase: {args.phase}")

    exports = Path(args.exports)
    checkpoint = exports / f"{args.project}-phase-checkpoints.jsonl"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    rows = load_rows(checkpoint)
    existing = [r for r in rows if r.get("phase_number") == args.phase]

    if existing and args.mode == "append-if-missing":
        print(f"checkpoint already exists for phase {args.phase}; leaving unchanged")
        return 0

    artifact_templates = PHASE_ARTIFACTS.get(args.phase, [])
    artifacts = render(artifact_templates, args.project)

    blockers: list[str] = []
    verified: list[str] = []
    for artifact in artifacts:
        ok, artifact_blockers = artifact_passes(Path(artifact), args.phase)
        if ok:
            verified.append(artifact)
        blockers.extend(artifact_blockers)

    now = utc_now()
    phase_passed = not blockers
    row = {
        "phase_number": args.phase,
        "phase_name": PHASES[args.phase],
        "started_at_utc": now,
        "completed_at_utc": now,
        "required_artifacts": artifacts,
        "artifacts_verified": verified,
        "validation_artifacts": artifacts,
        "validation_passed": phase_passed,
        "blockers": blockers,
        "phase_passed": phase_passed,
        "repair_required": not phase_passed,
    }

    if args.mode == "replace":
        rows = [r for r in rows if r.get("phase_number") != args.phase]

    rows.append(row)
    checkpoint.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )

    print(f"wrote checkpoint for phase {args.phase}: phase_passed={row['phase_passed']}")
    if blockers:
        for b in blockers:
            print(f"BLOCKER: {b}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
