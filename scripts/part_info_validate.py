#!/usr/bin/env python3
"""Validate ThomsonLint part_info JSON artifacts.

This validator checks datasheet-derived part behavior artifacts only. It does
not extract datasheets, build topology, modify phase workflow state, or create
findings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
DEFAULT_PART_INFO_DIR = Path("exports/part_info")
DEFAULT_SCHEMA = Path("schemas/part_info_schema.json")
EXAMPLES_DIR = Path("examples/part_info_examples")

FORBIDDEN_TOPOLOGY_KEYS = {
    "refdes",
    "net_name",
    "board_nets",
    "branch_id",
    "copper_geometry_refs",
    "topology",
}

ACTIVE_CATEGORIES = {
    "buck_regulator",
    "ldo_regulator",
    "boost_regulator",
    "buck_boost_regulator",
    "isolated_converter",
    "mcu",
    "fpga",
    "connector",
    "switch",
    "transceiver",
    "logic",
    "sensor",
}

NUMERIC_KEYS = {"value", "min", "typ", "max"}
CURRENT_PATH_TOKENS = ("current", "_a", "load")
VOLTAGE_PATH_TOKENS = ("voltage", "_v")
THERMAL_PATH_TOKENS = ("thermal", "temp", "theta", "_w", "power_dissipation")
RATING_TOKENS = ("rating", "rated", "limit", "capability", "hold_current", "trip_current")
RATING_CONDITION_TOKENS = ("rating", "rated", "capability", "limit", "not actual board current")
ZERO_CURRENT_EXPLANATION_TOKENS = (
    "zero",
    "off",
    "shutdown",
    "sleep",
    "standby",
    "disabled",
    "no load",
    "not applicable",
)
CURRENT_UNRESOLVED_TOKENS = ("current", "load", "board_actual", "actual_current")


@dataclass
class FileResult:
    path: str
    status: str = "valid"
    schema_valid: bool = True
    semantic_valid: bool = True
    human_review_needed: bool = False
    missing_or_unresolved_current_model: bool = False
    low_confidence: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def finalize(self, *, strict: bool) -> None:
        if self.errors:
            self.status = "invalid"
            self.semantic_valid = False
            return
        if strict and (self.warnings or self.human_review_needed):
            self.status = "invalid"
            self.semantic_valid = False
            if self.warnings:
                self.errors.append("strict mode promotes warnings to invalid status")
            if self.human_review_needed:
                self.errors.append("strict mode promotes human_review_needed to invalid status")
            return
        if self.human_review_needed:
            self.status = "human_review_needed"
        elif self.warnings:
            self.status = "warning"
        else:
            self.status = "valid"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_path(path: tuple[Any, ...] | list[Any]) -> str:
    if not path:
        return "<root>"
    out = ""
    for part in path:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def iter_nodes(value: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[tuple[Any, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_nodes(child, path + (key,))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from iter_nodes(child, path + (idx,))


def is_numeric_object(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in NUMERIC_KEYS)


def path_text(path: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in path).lower()


def is_current_path(path: tuple[Any, ...]) -> bool:
    text = path_text(path)
    return any(token in text for token in CURRENT_PATH_TOKENS)


def is_voltage_or_thermal_path(path: tuple[Any, ...]) -> bool:
    text = path_text(path)
    return any(token in text for token in VOLTAGE_PATH_TOKENS + THERMAL_PATH_TOKENS)


def has_zero_current_explanation(condition: Any) -> bool:
    text = str(condition or "").lower()
    return any(token in text for token in ZERO_CURRENT_EXPLANATION_TOKENS)


def has_rating_condition(condition: Any) -> bool:
    text = str(condition or "").lower()
    return any(token in text for token in RATING_CONDITION_TOKENS)


def looks_like_rating(path: tuple[Any, ...], value: dict[str, Any]) -> bool:
    text = path_text(path)
    limit_type = str(value.get("limit_type") or "").lower()
    combined = f"{text} {limit_type}"
    words = set(re.split(r"[^a-z0-9]+", combined))
    return (
        bool(words.intersection({"rating", "rated", "limit", "capability"}))
        or "hold_current" in combined
        or "trip_current" in combined
    )


def has_actual_current_model(data: dict[str, Any]) -> bool:
    power = data.get("power_behavior")
    if not isinstance(power, dict):
        return False
    nominal = power.get("nominal_current_by_rail")
    if not isinstance(nominal, list):
        return False
    return any(isinstance(item, dict) and any(key in item for key in NUMERIC_KEYS) for item in nominal)


def has_unresolved_current(data: dict[str, Any]) -> bool:
    unresolved = data.get("unresolved_fields")
    if not isinstance(unresolved, list):
        return False
    text = " ".join(str(item).lower() for item in unresolved)
    return any(token in text for token in CURRENT_UNRESOLVED_TOKENS)


def load_json_file(path: Path) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:
        return None, str(exc)


def load_jsonschema() -> Any:
    try:
        import jsonschema  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "jsonschema is required for part_info validation. Install it with "
            "`python3 -m pip install jsonschema` or add it to the project environment."
        ) from exc
    return jsonschema


def schema_errors(jsonschema: Any, schema: dict[str, Any], data: Any) -> list[str]:
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    return [f"{format_path(list(err.path))}: {err.message}" for err in errors]


def validate_schema_document(jsonschema: Any, schema: dict[str, Any]) -> None:
    jsonschema.Draft7Validator.check_schema(schema)


def validate_evidence_refs(data: dict[str, Any], result: FileResult) -> None:
    evidence = data.get("evidence")
    evidence_ids = {
        item.get("id")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    for path, value in iter_nodes(data):
        if not path:
            continue
        key = path[-1]
        if key == "evidence_ref" and isinstance(value, str) and value not in evidence_ids:
            result.errors.append(f"{format_path(path)} dangling evidence_ref: {value}")
        elif key == "evidence_refs" and isinstance(value, list):
            for idx, ref in enumerate(value):
                if isinstance(ref, str) and ref not in evidence_ids:
                    result.errors.append(f"{format_path(path + (idx,))} dangling evidence reference: {ref}")


def validate_forbidden_topology_keys(data: dict[str, Any], result: FileResult) -> None:
    for path, value in iter_nodes(data):
        if isinstance(value, dict):
            for key in value:
                if key in FORBIDDEN_TOPOLOGY_KEYS:
                    result.errors.append(f"{format_path(path + (key,))} forbidden board topology field in part_info")


def validate_numeric_objects(data: dict[str, Any], result: FileResult) -> None:
    for path, value in iter_nodes(data):
        if not is_numeric_object(value):
            continue
        assert isinstance(value, dict)
        loc = format_path(path)
        for required in ("unit", "condition", "confidence"):
            if required not in value:
                result.errors.append(f"{loc} numeric object missing {required}")

        confidence = value.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            result.errors.append(f"{loc}.confidence must be between 0.0 and 1.0")

        check_non_negative = is_current_path(path) or is_voltage_or_thermal_path(path)
        for key in NUMERIC_KEYS:
            raw = value.get(key)
            if not isinstance(raw, (int, float)):
                continue
            if check_non_negative and raw < 0:
                result.errors.append(f"{loc}.{key} has impossible negative value: {raw}")
            if is_current_path(path) and raw == 0 and not has_zero_current_explanation(value.get("condition")):
                result.warnings.append(f"{loc}.{key} is zero current without an explicit zero-current condition")

        if looks_like_rating(path, value) and not has_rating_condition(value.get("condition")):
            result.errors.append(
                f"{loc}.condition must identify rating/capability/limit semantics and avoid treating ratings as board load"
            )


def validate_current_semantics(data: dict[str, Any], result: FileResult) -> None:
    category = data.get("component_category")
    if category not in ACTIVE_CATEGORIES:
        return

    actual_current_model = has_actual_current_model(data)
    unresolved_current = has_unresolved_current(data)
    if not actual_current_model:
        result.missing_or_unresolved_current_model = True
        if not unresolved_current:
            result.errors.append(
                "active component has no nominal current model and unresolved_fields does not record unresolved current/load"
            )
        else:
            result.human_review_needed = True
            result.notes.append("active component current behavior is unresolved")


def validate_confidence(data: dict[str, Any], result: FileResult) -> None:
    confidence = data.get("confidence")
    extraction = data.get("extraction_method")
    overall = None
    if isinstance(confidence, dict) and isinstance(confidence.get("overall"), (int, float)):
        overall = float(confidence["overall"])

    human_reviewed = False
    if isinstance(extraction, dict):
        human_reviewed = extraction.get("human_reviewed") is True

    if overall is None:
        result.errors.append("confidence.overall missing or non-numeric")
        return
    if overall < 0.7:
        result.low_confidence = True
        result.human_review_needed = True
        result.notes.append("confidence.overall below 0.7")
    if not human_reviewed and overall < 0.85:
        result.human_review_needed = True
        result.notes.append("AI/unreviewed extraction below 0.85 confidence")


def validate_part_info_file(
    path: Path,
    *,
    jsonschema: Any,
    schema: dict[str, Any],
    strict: bool = False,
) -> FileResult:
    result = FileResult(path=str(path))
    data, error = load_json_file(path)
    if error:
        result.schema_valid = False
        result.errors.append(f"invalid JSON: {error}")
        result.finalize(strict=strict)
        return result
    if not isinstance(data, dict):
        result.schema_valid = False
        result.errors.append("part_info file must contain a JSON object")
        result.finalize(strict=strict)
        return result

    schema_validation_errors = schema_errors(jsonschema, schema, data)
    if schema_validation_errors:
        result.schema_valid = False
        result.errors.extend(f"schema: {err}" for err in schema_validation_errors)

    validate_evidence_refs(data, result)
    validate_forbidden_topology_keys(data, result)
    validate_numeric_objects(data, result)
    validate_current_semantics(data, result)
    validate_confidence(data, result)

    result.semantic_valid = not result.errors
    result.finalize(strict=strict)
    return result


def result_to_dict(result: FileResult) -> dict[str, Any]:
    return {
        "path": result.path,
        "status": result.status,
        "schema_valid": result.schema_valid,
        "semantic_valid": result.semantic_valid,
        "human_review_needed": result.human_review_needed,
        "missing_or_unresolved_current_model": result.missing_or_unresolved_current_model,
        "low_confidence": result.low_confidence,
        "errors": result.errors,
        "warnings": result.warnings,
        "notes": result.notes,
    }


def collect_input_files(part_info_dir: Path, *, include_examples: bool) -> list[Path]:
    paths: list[Path] = []
    if part_info_dir.exists():
        if not part_info_dir.is_dir():
            raise ValueError(f"--part-info-dir is not a directory: {part_info_dir}")
        paths.extend(sorted(part_info_dir.glob("*.json")))
    if include_examples:
        if not EXAMPLES_DIR.exists():
            raise ValueError(f"examples directory does not exist: {EXAMPLES_DIR}")
        paths.extend(sorted(EXAMPLES_DIR.glob("*.json")))

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def build_artifact(
    *,
    project: str,
    part_info_dir: Path,
    schema_path: Path,
    results: list[FileResult],
    execution_pass: bool,
    artifact_validation_pass: bool,
    top_errors: list[str],
    top_warnings: list[str],
) -> dict[str, Any]:
    invalid = [r for r in results if r.status == "invalid"]
    review = [r for r in results if r.human_review_needed]
    low_confidence = [r for r in results if r.low_confidence]
    unresolved_current = [r for r in results if r.missing_or_unresolved_current_model]
    aggregate_errors = list(top_errors)
    aggregate_warnings = list(top_warnings)
    for result in results:
        aggregate_errors.extend(f"{result.path}: {err}" for err in result.errors)
        aggregate_warnings.extend(f"{result.path}: {warn}" for warn in result.warnings)

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "part_info_dir": str(part_info_dir),
        "schema_path": str(schema_path),
        "files_checked": len(results),
        "valid_files": sum(1 for r in results if r.status in {"valid", "warning", "human_review_needed"}),
        "invalid_files": len(invalid),
        "human_review_needed": len(review),
        "missing_or_unresolved_current_models": len(unresolved_current),
        "low_confidence_files": len(low_confidence),
        "files": [result_to_dict(r) for r in results],
        "errors": aggregate_errors,
        "warnings": aggregate_warnings,
        "execution_pass": execution_pass,
        "artifact_validation_pass": artifact_validation_pass,
        "overall_pass": execution_pass and artifact_validation_pass and not invalid,
    }


def write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate ThomsonLint part_info JSON files.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--part-info-dir", default=str(DEFAULT_PART_INFO_DIR))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--out", default=None)
    parser.add_argument("--examples", action="store_true", help="Also validate examples/part_info_examples/*.json")
    parser.add_argument("--strict", action="store_true", help="Promote warnings and human-review flags to invalid status")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    part_info_dir = Path(args.part_info_dir)
    schema_path = Path(args.schema)
    out_path = Path(args.out) if args.out else Path("exports") / f"{project}-part-info-validation.json"

    top_errors: list[str] = []
    top_warnings: list[str] = []
    results: list[FileResult] = []

    try:
        jsonschema = load_jsonschema()
        if not schema_path.exists():
            raise FileNotFoundError(f"missing schema: {schema_path}")
        schema_data, schema_error = load_json_file(schema_path)
        if schema_error:
            raise ValueError(f"invalid schema JSON {schema_path}: {schema_error}")
        if not isinstance(schema_data, dict):
            raise ValueError(f"schema must be a JSON object: {schema_path}")
        validate_schema_document(jsonschema, schema_data)

        input_files = collect_input_files(part_info_dir, include_examples=args.examples)
        if not input_files:
            raise ValueError(
                f"no part_info JSON files found in {part_info_dir}"
                + (" or examples/part_info_examples" if args.examples else "")
            )

        results = [
            validate_part_info_file(path, jsonschema=jsonschema, schema=schema_data, strict=args.strict)
            for path in input_files
        ]
        artifact = build_artifact(
            project=project,
            part_info_dir=part_info_dir,
            schema_path=schema_path,
            results=results,
            execution_pass=True,
            artifact_validation_pass=True,
            top_errors=top_errors,
            top_warnings=top_warnings,
        )
        write_artifact(out_path, artifact)
    except Exception as exc:
        top_errors.append(str(exc))
        artifact = build_artifact(
            project=project,
            part_info_dir=part_info_dir,
            schema_path=schema_path,
            results=results,
            execution_pass=False,
            artifact_validation_pass=False,
            top_errors=top_errors,
            top_warnings=top_warnings,
        )
        try:
            write_artifact(out_path, artifact)
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    invalid_count = sum(1 for result in results if result.status == "invalid")
    print(
        f"part_info validation: files_checked={len(results)} "
        f"invalid_files={invalid_count} human_review_needed={sum(1 for r in results if r.human_review_needed)} "
        f"out={out_path}"
    )
    return 1 if invalid_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
