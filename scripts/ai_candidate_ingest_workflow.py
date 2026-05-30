#!/usr/bin/env python3
"""Run AI candidate adapter inputs through deterministic ingestion scripts.

PR31 scope only: execute existing current/rating ingestion scripts into
isolated AI candidate output paths. This wrapper does not call AI, rebuild
upstream AI artifacts, overwrite core artifacts, run allocation/calculations,
merge addenda, create findings, or make pass/fail/compliance judgments.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_VERSION = "ai_candidate_ingestion_workflow_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_candidate_ingestion_workflow_schema.json"
DEFAULT_CURRENT_SCRIPT = "scripts/current_model_ingest.py"
DEFAULT_RATING_SCRIPT = "scripts/rating_model_ingest.py"
PREVIEW_LIMIT = 4000

OUTPUTS = {
    "current_models_normalized": "ai-current-models-normalized.json",
    "rating_current_models_normalized": "ai-rating-current-models-normalized.json",
    "rating_models_normalized": "ai-rating-models-normalized.json",
    "addenda_index": "ai-addenda-index.json",
    "human_review_index": "ai-human-review-index.json",
    "review": "ai-candidate-ingestion-review.json",
    "status": "ai-candidate-ingestion-status.json",
}

ADAPTER_FILES = {
    "current": "ai-current-model-ingest-input.json",
    "rating": "ai-rating-model-ingest-input.json",
    "role": "ai-role-resolution-addenda-adapter.json",
    "pin": "ai-pin-role-addenda-adapter.json",
    "rail": "ai-rail-relationship-hints-adapter.json",
    "passive": "ai-passive-support-adapter.json",
    "human": "ai-human-review-adapter.json",
}

FORBIDDEN_OUTPUT_FILENAMES = {
    "{project}-current-models-normalized.json",
    "{project}-rating-models-normalized.json",
    "{project}-topology-current-allocation.json",
    "{project}-topology-copper-calculations.json",
    "{project}-topology-margin-calculations.json",
}

FORBIDDEN_FIELDS = {
    "finding_id", "issue_id", "violation", "severity", "compliance_pass", "compliance_fail", "pass_fail",
    "margin_pass", "margin_fail", "acceptable", "unacceptable", "final_finding", "recommendation_severity",
    "apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing",
}

AI_PROVENANCE_FIELDS = {
    "source_candidate_record_id",
    "source_patch_id",
    "source_packet_id",
    "source_item_id",
    "source_accepted_item_id",
    "missing_data_item_ids",
    "ai_evidence_refs",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def source_artifact(artifact_type: str, path: Path | None, notes: str | None = None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path) if path else None, "notes": notes}


def preview(text: str) -> str:
    if len(text) <= PREVIEW_LIMIT:
        return text
    return text[:PREVIEW_LIMIT] + "...[truncated]"


def walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(walk_keys(child))
    return keys


def safe_load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def verify_output_path(path: Path, out_dir: Path, project: str) -> None:
    forbidden = {name.format(project=project) for name in FORBIDDEN_OUTPUT_FILENAMES}
    if path.name in forbidden:
        raise ValueError(f"forbidden core output filename: {path.name}")
    if not path_is_relative_to(path, out_dir):
        raise ValueError(f"output path must be inside out-dir: {path}")


def verify_input_path(path: Path, adapter_dir: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"missing adapter file: {path}")
    if not path_is_relative_to(path, adapter_dir):
        raise ValueError(f"adapter input path must be inside adapter-dir: {path}")


def verify_script_path(path: Path) -> Path:
    if str(path).startswith(("http://", "https://")):
        raise ValueError(f"script path must be local: {path}")
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"missing ingestion script: {path}")
    if not resolved.is_file():
        raise ValueError(f"ingestion script must be a file: {path}")
    return resolved


def count_current_adapter_records(data: dict[str, Any]) -> int:
    return sum(len(as_list(data.get(key))) for key in ("branch_currents", "rail_currents", "component_currents"))


def count_rating_adapter_records(data: dict[str, Any]) -> int:
    return len(as_list(data.get("ratings")))


def current_normalized_count(path: Path) -> int:
    data = safe_load(path)
    return len(as_list(data.get("normalized_currents")))


def rating_normalized_count(path: Path) -> int:
    data = safe_load(path)
    return len(as_list(data.get("normalized_ratings")))


def step_record(
    *,
    step_id: str,
    status: str,
    input_path: Path | None,
    output_path: Path | None,
    command: list[str],
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "status": status,
        "input_path": str(input_path) if input_path else None,
        "output_path": str(output_path) if output_path else None,
        "command": command,
        "returncode": returncode,
        "stdout_preview": preview(stdout),
        "stderr_preview": preview(stderr),
        "errors": errors or [],
        "warnings": warnings or [],
    }


def run_step(step_id: str, command: list[str], input_path: Path, output_path: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True)
    status = "passed" if completed.returncode == 0 and output_path.exists() else "failed"
    errors = [] if status == "passed" else [f"{step_id} returned {completed.returncode}"]
    return step_record(
        step_id=step_id,
        status=status,
        input_path=input_path,
        output_path=output_path,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        errors=errors,
    )


def addenda_index(project: str, adapter_dir: Path, source_artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    role_path = adapter_dir / ADAPTER_FILES["role"]
    pin_path = adapter_dir / ADAPTER_FILES["pin"]
    rail_path = adapter_dir / ADAPTER_FILES["rail"]
    passive_path = adapter_dir / ADAPTER_FILES["passive"]
    role = safe_load(role_path)
    pin = safe_load(pin_path)
    rail = safe_load(rail_path)
    passive = safe_load(passive_path)
    return {
        "project": project,
        "schema_version": "ai_addenda_index_v1",
        "source_artifacts": source_artifacts,
        "role_resolution_addenda_adapter": str(role_path),
        "pin_role_addenda_adapter": str(pin_path),
        "rail_relationship_hints_adapter": str(rail_path),
        "passive_support_adapter": str(passive_path),
        "summary": {
            "role_addenda_count": len(as_list(role.get("role_addenda"))),
            "pin_role_addenda_count": len(as_list(pin.get("pin_role_addenda"))),
            "rail_relationship_hint_count": len(as_list(rail.get("rail_relationship_hints"))),
            "passive_support_count": len(as_list(passive.get("passive_support_records"))),
        },
        "safe_to_merge_automatically": False,
        "requires_merge_validator": True,
        "errors": [],
        "warnings": [],
    }


def workflow_review_records(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for step in steps:
        if step.get("status") == "failed":
            records.append({
                "review_id": f"workflow_{step['step_id']}",
                "reason_code": "workflow_step_failed",
                "detail": f"workflow step failed: {step['step_id']}",
                "step_id": step["step_id"],
                "input_path": step.get("input_path"),
                "output_path": step.get("output_path"),
                "returncode": step.get("returncode"),
                "usable_for_ingestion": False,
                "errors": as_list(step.get("errors")),
                "warnings": as_list(step.get("warnings")),
            })
        elif step.get("status") == "skipped":
            records.append({
                "review_id": f"workflow_{step['step_id']}",
                "reason_code": "workflow_step_skipped",
                "detail": f"workflow step skipped: {step['step_id']}",
                "step_id": step["step_id"],
                "input_path": step.get("input_path"),
                "output_path": step.get("output_path"),
                "returncode": step.get("returncode"),
                "usable_for_ingestion": False,
                "errors": [],
                "warnings": as_list(step.get("warnings")),
            })
    return records


def human_review_index(project: str, adapter_dir: Path, source_artifacts: list[dict[str, Any]], steps: list[dict[str, Any]]) -> dict[str, Any]:
    human_path = adapter_dir / ADAPTER_FILES["human"]
    human = safe_load(human_path)
    human_records = as_list(human.get("human_review_records"))
    workflow_records = workflow_review_records(steps)
    return {
        "project": project,
        "schema_version": "ai_human_review_index_v1",
        "source_artifacts": source_artifacts + [source_artifact("ai_human_review_adapter", human_path)],
        "human_review_records": human_records,
        "workflow_review_records": workflow_records,
        "summary": {
            "human_review_record_count": len(human_records),
            "workflow_review_record_count": len(workflow_records),
            "requires_human_review_count": len(human_records) + len(workflow_records),
        },
        "errors": [],
        "warnings": [],
    }


def detect_provenance_gaps(adapter_inputs: list[dict[str, Any]], output_paths: list[Path]) -> list[str]:
    source_fields = set()
    for artifact in adapter_inputs:
        for key in ("branch_currents", "rail_currents", "component_currents", "ratings"):
            for row in as_list(artifact.get(key)):
                if isinstance(row, dict):
                    source_fields.update(set(row).intersection(AI_PROVENANCE_FIELDS))
    output_fields = set()
    for path in output_paths:
        data = safe_load(path)
        for key in ("normalized_currents", "normalized_ratings"):
            for row in as_list(data.get(key)):
                if isinstance(row, dict):
                    output_fields.update(row.keys())
                    provenance = row.get("provenance")
                    if isinstance(provenance, dict):
                        output_fields.update(provenance.keys())
    gaps = []
    for field in sorted(source_fields - output_fields):
        gaps.append(f"{field} not present in normalized output from existing ingestion scripts")
    return gaps


def build_workflow(
    *,
    project: str,
    adapter_dir: Path,
    out_dir: Path,
    python_executable: Path,
    current_script: Path,
    rating_script: Path,
    skip_current: bool,
    skip_rating: bool,
    strict: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    adapter_dir = adapter_dir.resolve()
    out_dir = out_dir.resolve()
    manifest_path = adapter_dir / "ai-adapter-manifest.json"
    status_path = adapter_dir / "adapter-status.json"
    adapter_manifest = load_json(manifest_path)
    adapter_status = load_json(status_path)
    if not isinstance(adapter_manifest, dict):
        raise ValueError(f"adapter manifest must be a JSON object: {manifest_path}")
    if not isinstance(adapter_status, dict):
        raise ValueError(f"adapter status must be a JSON object: {status_path}")

    current_script = verify_script_path(current_script)
    rating_script = verify_script_path(rating_script)
    python_executable = verify_script_path(python_executable)

    for filename in ADAPTER_FILES.values():
        verify_input_path(adapter_dir / filename, adapter_dir)
    for filename in OUTPUTS.values():
        verify_output_path(out_dir / filename, out_dir, project)

    out_dir.mkdir(parents=True, exist_ok=True)
    source_artifacts = [
        source_artifact("ai_adapter_manifest", manifest_path),
        source_artifact("ai_adapter_status", status_path),
    ]
    current_input_path = adapter_dir / ADAPTER_FILES["current"]
    rating_input_path = adapter_dir / ADAPTER_FILES["rating"]
    current_input = load_json(current_input_path)
    rating_input = load_json(rating_input_path)
    if not isinstance(current_input, dict) or not isinstance(rating_input, dict):
        raise ValueError("adapter ingest inputs must be JSON objects")

    current_out = out_dir / OUTPUTS["current_models_normalized"]
    rating_current_out = out_dir / OUTPUTS["rating_current_models_normalized"]
    rating_out = out_dir / OUTPUTS["rating_models_normalized"]

    steps: list[dict[str, Any]] = []
    if skip_current:
        steps.append(step_record(
            step_id="current_model_ingest",
            status="skipped",
            input_path=current_input_path,
            output_path=current_out,
            command=[],
            returncode=None,
            warnings=["skip-current flag set"],
        ))
    else:
        command = [
            str(python_executable),
            str(current_script),
            "--project",
            project,
            "--current-model",
            str(current_input_path),
            "--out",
            str(current_out),
        ]
        steps.append(run_step("current_model_ingest", command, current_input_path, current_out))

    if skip_rating:
        steps.append(step_record(
            step_id="rating_current_model_ingest",
            status="skipped",
            input_path=rating_input_path,
            output_path=rating_current_out,
            command=[],
            returncode=None,
            warnings=["skip-rating flag set"],
        ))
        steps.append(step_record(
            step_id="rating_model_ingest",
            status="skipped",
            input_path=rating_current_out,
            output_path=rating_out,
            command=[],
            returncode=None,
            warnings=["skip-rating flag set"],
        ))
    else:
        rating_current_command = [
            str(python_executable),
            str(current_script),
            "--project",
            project,
            "--current-model",
            str(rating_input_path),
            "--out",
            str(rating_current_out),
        ]
        rating_current_step = run_step("rating_current_model_ingest", rating_current_command, rating_input_path, rating_current_out)
        steps.append(rating_current_step)
        if rating_current_step["status"] == "passed":
            rating_command = [
                str(python_executable),
                str(rating_script),
                "--project",
                project,
                "--current-models-normalized",
                str(rating_current_out),
                "--out",
                str(rating_out),
            ]
            steps.append(run_step("rating_model_ingest", rating_command, rating_current_out, rating_out))
        else:
            steps.append(step_record(
                step_id="rating_model_ingest",
                status="skipped",
                input_path=rating_current_out,
                output_path=rating_out,
                command=[],
                returncode=None,
                warnings=["rating current ingest failed; dependent rating ingest skipped"],
            ))

    addenda = addenda_index(project, adapter_dir, source_artifacts)
    human = human_review_index(project, adapter_dir, source_artifacts, steps)
    provenance_gaps = detect_provenance_gaps([current_input, rating_input], [current_out, rating_current_out, rating_out])

    step_statuses = [step["status"] for step in steps]
    errors = [error for step in steps for error in as_list(step.get("errors"))]
    warnings = [warning for step in steps for warning in as_list(step.get("warnings"))]
    if strict and human["summary"]["requires_human_review_count"]:
        errors.append("strict mode disallows human review records")
    workflow_pass = not errors and "failed" not in step_statuses
    status_text = "completed" if workflow_pass and not warnings else "completed_with_warnings" if workflow_pass else "failed"

    summary = {
        "current_adapter_record_count": count_current_adapter_records(current_input),
        "rating_adapter_record_count": count_rating_adapter_records(rating_input),
        "current_normalized_record_count": current_normalized_count(current_out),
        "rating_current_normalized_record_count": current_normalized_count(rating_current_out),
        "rating_normalized_record_count": rating_normalized_count(rating_out),
        "role_addenda_count": addenda["summary"]["role_addenda_count"],
        "pin_role_addenda_count": addenda["summary"]["pin_role_addenda_count"],
        "rail_relationship_hint_count": addenda["summary"]["rail_relationship_hint_count"],
        "passive_support_count": addenda["summary"]["passive_support_count"],
        "human_review_record_count": human["summary"]["human_review_record_count"],
        "workflow_review_record_count": human["summary"]["workflow_review_record_count"],
        "step_count": len(steps),
        "passed_step_count": sum(1 for step in steps if step["status"] == "passed"),
        "failed_step_count": sum(1 for step in steps if step["status"] == "failed"),
        "skipped_step_count": sum(1 for step in steps if step["status"] == "skipped"),
        "safe_to_use_as_candidate_inputs": workflow_pass,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }

    manifest = {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts,
        "source_adapter_manifest": str(manifest_path),
        "source_adapter_status": str(status_path),
        "workflow_pass": workflow_pass,
        "outputs": OUTPUTS,
        "steps": steps,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    status = {
        "project": project,
        "status": status_text,
        "workflow_pass": workflow_pass,
        "safe_to_use_as_candidate_inputs": workflow_pass,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "current_ingest_pass": any(step["step_id"] == "current_model_ingest" and step["status"] == "passed" for step in steps),
        "rating_current_ingest_pass": any(step["step_id"] == "rating_current_model_ingest" and step["status"] == "passed" for step in steps),
        "rating_ingest_pass": any(step["step_id"] == "rating_model_ingest" and step["status"] == "passed" for step in steps),
        "requires_human_review_count": human["summary"]["requires_human_review_count"],
        "errors": errors,
        "warnings": warnings,
    }
    review = {
        "project": project,
        "schema_version": "ai_candidate_ingestion_review_v1",
        "workflow_pass": workflow_pass,
        "candidate_outputs": {
            key: str(out_dir / value)
            for key, value in OUTPUTS.items()
            if key in {"current_models_normalized", "rating_current_models_normalized", "rating_models_normalized"}
        },
        "manual_next_steps": [
            "inspect isolated candidate-normalized outputs",
            "review human-review and addenda indexes before any promotion",
            "promote candidate data only through a future explicit approval workflow",
        ],
        "known_provenance_gaps": provenance_gaps,
        "not_performed": [
            "core artifact overwrite",
            "current allocation rerun",
            "copper calculation rerun",
            "margin calculation rerun",
            "role/pin/rail addenda merge",
        ],
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    return manifest, status, addenda, human, review


def validate_outputs(outputs: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for output in outputs:
        forbidden = sorted(walk_keys(output).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            raise ValueError(f"workflow output contains forbidden field(s): {', '.join(forbidden)}")
        jsonschema.validate(instance=output, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI candidate adapter inputs through isolated deterministic ingestion.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--skip-current", action="store_true")
    parser.add_argument("--skip-rating", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--current-model-ingest-script", default=DEFAULT_CURRENT_SCRIPT)
    parser.add_argument("--rating-model-ingest-script", default=DEFAULT_RATING_SCRIPT)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    adapter_dir = Path(args.adapter_dir)
    out_dir = Path(args.out_dir)
    try:
        if not adapter_dir.exists():
            raise FileNotFoundError(f"missing adapter directory: {adapter_dir}")
        if not (adapter_dir / "ai-adapter-manifest.json").exists():
            raise FileNotFoundError(f"missing adapter manifest: {adapter_dir / 'ai-adapter-manifest.json'}")
        if not (adapter_dir / "adapter-status.json").exists():
            raise FileNotFoundError(f"missing adapter status: {adapter_dir / 'adapter-status.json'}")
        manifest, status, addenda, human, review = build_workflow(
            project=args.project,
            adapter_dir=adapter_dir,
            out_dir=out_dir,
            python_executable=Path(args.python_executable),
            current_script=Path(args.current_model_ingest_script),
            rating_script=Path(args.rating_model_ingest_script),
            skip_current=args.skip_current,
            skip_rating=args.skip_rating,
            strict=args.strict,
        )
        validate_outputs([manifest, status, addenda, human, review], Path(args.schema))
        write_json(out_dir / "ai-candidate-ingestion-manifest.json", manifest)
        write_json(out_dir / "ai-candidate-ingestion-status.json", status)
        write_json(out_dir / "ai-addenda-index.json", addenda)
        write_json(out_dir / "ai-human-review-index.json", human)
        write_json(out_dir / "ai-candidate-ingestion-review.json", review)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(
        "ai candidate ingestion workflow: "
        f"project={manifest['project']} current={summary['current_normalized_record_count']} "
        f"rating={summary['rating_normalized_record_count']} steps={summary['passed_step_count']}/{summary['step_count']} "
        f"out={out_dir}"
    )
    return 0 if manifest["workflow_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
