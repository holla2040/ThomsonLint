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
    11: "Review BOM and Component Evidence FULL",
    12: "Review Image Evidence FULL",
    13: "Review Datasheet Evidence FULL",
    14: "Cross-Source Consistency Review",
    15: "Pre-Findings Gate Check",
    16: "Candidate Finding Development",
    17: "Write Findings JSON",
    18: "Validate and Repair Findings",
    19: "Generate Report",
    20: "Final Summary",
}

PHASE_ARTIFACTS = {
    3: ["exports/tool-preflight-status.json"],
    4: [
        "exports/{project}-bom.json",
        "exports/{project}-thomson-export-sch.json",
        "exports/{project}-thomson-export-brd.json",
        "exports/{project}-thomson-export-stack.json",
    ],
    6: [
        "exports/datasheets/datasheet_manifest.jsonl",
        "exports/datasheets/datasheet_manifest_validation.json",
    ],
    7: ["exports/{project}-image-evidence-inventory.json"],
    8: ["exports/{project}-schematic-evidence-review.json"],
    9: [
        "exports/{project}-board-evidence-inventory.json",
        "exports/{project}-board-evidence-inventory-validation.json",
    ],
    10: ["exports/{project}-stackup-evidence-review.json"],
    11: ["exports/{project}-bom-review.json"],
    12: ["exports/{project}-image-vision-review.json"],
    13: ["exports/{project}-datasheet-evidence-review.json"],
    14: ["exports/{project}-cross-source-consistency-review.json"],
    15: ["exports/{project}-pre-findings-gate.json"],
    16: ["exports/{project}-candidate-findings.json"],
    17: ["exports/{project}-findings.json"],
    18: ["exports/{project}-findings.json"],
    19: [
        "exports/{project}-review.html",
        "exports/{project}-report-generation-validation.json",
    ],
    20: [
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

        # Known artifact-level pass fields.
        if phase == 7:
            for field in [
                "pdf_sources",
                "conversion_tool",
                "total_pages_expected",
                "total_pages_rendered",
                "output_files",
                "schematic_pngs",
                "layout_pngs",
                "pages_inspected",
                "overall_pass",
            ]:
                if field not in data:
                    blockers.append(f"{path} missing field {field}")
            if data.get("overall_pass") is not True:
                blockers.append(f"{path} overall_pass is not true")
        if phase == 9 and path.name.endswith("-validation.json") and data.get("overall_pass") is not True:
            blockers.append(f"{path} overall_pass is not true")
        if phase == 15 and data.get("overall_gate_pass") is not True:
            blockers.append(f"{path} overall_gate_pass is not true")
        if phase == 19 and path.name.endswith("-validation.json") and data.get("overall_pass") is not True:
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
    row = {
        "phase_number": args.phase,
        "phase_name": PHASES[args.phase],
        "started_at_utc": now,
        "completed_at_utc": now,
        "required_artifacts": artifacts,
        "artifacts_verified": verified,
        "validation_artifacts": artifacts,
        "validation_passed": not blockers,
        "blockers": blockers,
        "phase_passed": not blockers,
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
