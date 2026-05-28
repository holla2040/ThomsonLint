#!/usr/bin/env python3
"""Build an index of validated part_info artifacts.

This script maps BOM refdes and normalized MPNs to existing part_info JSON
files. It does not extract datasheets, build board topology, modify workflow
state, or create findings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
DEFAULT_PART_INFO_DIR = Path("exports/part_info")
EXAMPLES_DIR = Path("examples/part_info_examples")


try:
    from datasheet_helper import norm as _datasheet_norm
except Exception:
    _datasheet_norm = None


def normalize_mpn(value: Any) -> str:
    if _datasheet_norm is not None:
        return _datasheet_norm(value)
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def key_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_value(sources: list[dict[str, Any]], aliases: set[str]) -> Any:
    for source in sources:
        for key, value in source.items():
            if key_name(key) in aliases and value not in (None, ""):
                return value
    return None


def row_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [row]
    for key in ("fields", "raw", "custom_metadata"):
        nested = row.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return sources


def expand_refdes_token(token: str) -> list[str]:
    token = token.strip()
    if not token:
        return []
    match = re.fullmatch(r"([A-Za-z]+)(\d+)-(?:(\1)?)(\d+)", token)
    if not match:
        return [token]
    prefix = match.group(1)
    start = int(match.group(2))
    end = int(match.group(4))
    if end < start or end - start > 200:
        return [token]
    return [f"{prefix}{idx}" for idx in range(start, end + 1)]


def parse_refdes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(parse_refdes(item))
        return refs
    text = str(value).strip()
    if not text:
        return []
    tokens = re.split(r"[\s,;]+", text)
    refs: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for ref in expand_refdes_token(token):
            if ref and ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


@dataclass
class BomEntry:
    row_index: int
    refdes: list[str]
    mpn: str | None
    manufacturer: str | None
    normalized_mpn: str | None
    raw: dict[str, Any]


@dataclass
class PartInfoEntry:
    file: str
    schema_version: str | None
    mpn: str | None
    manufacturer: str | None
    normalized_mpn: str
    component_category: str | None
    confidence_overall: float | None
    human_reviewed: bool | None
    unresolved_fields: list[Any]
    validation_status: str | None = None
    validation_human_review_needed: bool = False
    validation_errors: list[str] = field(default_factory=list)

    @property
    def invalid(self) -> bool:
        return self.validation_status == "invalid"

    @property
    def human_review_needed(self) -> bool:
        return self.validation_human_review_needed


def extract_bom_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("rows", "components", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    bom = data.get("bom")
    if isinstance(bom, list):
        return [row for row in bom if isinstance(row, dict)]
    if isinstance(bom, dict):
        for key in ("rows", "components", "items"):
            value = bom.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def parse_bom(data: Any) -> list[BomEntry]:
    rows = extract_bom_rows(data)
    entries: list[BomEntry] = []
    ref_aliases = {"refdes", "designator", "reference", "references", "refdes", "refdes", "refdes", "refdes"}
    ref_aliases.update({"refdes", "refdes", "refdes", "refdes", "refdes", "refdes", "refdes", "refdes", "refdes"})
    # key_name("REF DES") and key_name("ref_des") both normalize to refdes.
    mpn_aliases = {"mpn", "manufacturerpartnumber", "manufacturerpart", "partnumber", "value", "mfgpn1", "mfgpn2", "mfgpn3"}
    manufacturer_aliases = {"manufacturer", "mfr", "vendor", "mfg1", "mfg2", "mfg3"}

    for idx, row in enumerate(rows, 1):
        sources = row_sources(row)
        refdes = parse_refdes(first_value(sources, ref_aliases) or row.get("refdes"))
        mpn = first_value(sources, {"mpn", "manufacturerpartnumber", "manufacturerpart", "partnumber", "mfgpn1"})
        manufacturer = first_value(sources, {"manufacturer", "mfr", "vendor", "mfg1"})

        manufacturers = row.get("manufacturers")
        if (not mpn or not manufacturer) and isinstance(manufacturers, list) and manufacturers:
            first = as_dict(manufacturers[0])
            mpn = mpn or first.get("mpn")
            manufacturer = manufacturer or first.get("manufacturer")

        # Value is a last-resort part identifier for non-standard BOM shapes.
        if not mpn:
            mpn = first_value(sources, {"value"})
        if not manufacturer:
            manufacturer = first_value(sources, manufacturer_aliases)
        normalized = normalize_mpn(mpn) if mpn else None
        entries.append(
            BomEntry(
                row_index=idx,
                refdes=refdes,
                mpn=str(mpn).strip() if mpn is not None else None,
                manufacturer=str(manufacturer).strip() if manufacturer is not None else None,
                normalized_mpn=normalized or None,
                raw=row,
            )
        )
    return entries


def collect_part_info_files(part_info_dir: Path, include_examples: bool) -> list[Path]:
    paths: list[Path] = []
    if part_info_dir.exists():
        if not part_info_dir.is_dir():
            raise ValueError(f"--part-info-dir is not a directory: {part_info_dir}")
        paths.extend(sorted(part_info_dir.glob("*.json")))
    if include_examples:
        if not EXAMPLES_DIR.exists():
            raise ValueError(f"examples directory does not exist: {EXAMPLES_DIR}")
        paths.extend(sorted(EXAMPLES_DIR.glob("*.json")))
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def read_validation(validation_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not validation_path.exists():
        return {}, [f"validation artifact missing: {validation_path}"]
    data = load_json(validation_path)
    if not isinstance(data, dict):
        raise ValueError(f"validation artifact must be a JSON object: {validation_path}")
    rows = data.get("files")
    if not isinstance(rows, list):
        raise ValueError(f"validation artifact missing files[]: {validation_path}")
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path:
            continue
        p = Path(path)
        keys = {path, p.name}
        try:
            keys.add(str(p.resolve()))
        except Exception:
            pass
        for key in keys:
            by_key[key] = row
    return by_key, []


def validation_for(path: Path, validation_rows: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    keys = [str(path), path.name]
    try:
        keys.append(str(path.resolve()))
    except Exception:
        pass
    for key in keys:
        row = validation_rows.get(key)
        if row is not None:
            return row
    return None


def parse_part_info(path: Path, validation_rows: dict[str, dict[str, Any]]) -> PartInfoEntry:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"part_info file must be a JSON object: {path}")
    mpn = data.get("mpn")
    manufacturer = data.get("manufacturer")
    normalized = data.get("normalized_mpn") or normalize_mpn(mpn)
    if not normalized:
        raise ValueError(f"part_info file missing mpn/normalized_mpn: {path}")
    confidence = data.get("confidence")
    confidence_overall = None
    if isinstance(confidence, dict) and isinstance(confidence.get("overall"), (int, float)):
        confidence_overall = float(confidence["overall"])
    extraction = data.get("extraction_method")
    human_reviewed = extraction.get("human_reviewed") if isinstance(extraction, dict) else None
    unresolved = data.get("unresolved_fields")
    validation = validation_for(path, validation_rows)
    return PartInfoEntry(
        file=str(path),
        schema_version=data.get("schema_version") if isinstance(data.get("schema_version"), str) else None,
        mpn=str(mpn).strip() if mpn is not None else None,
        manufacturer=str(manufacturer).strip() if manufacturer is not None else None,
        normalized_mpn=str(normalized),
        component_category=data.get("component_category") if isinstance(data.get("component_category"), str) else None,
        confidence_overall=confidence_overall,
        human_reviewed=human_reviewed if isinstance(human_reviewed, bool) else None,
        unresolved_fields=unresolved if isinstance(unresolved, list) else [],
        validation_status=validation.get("status") if isinstance(validation, dict) else None,
        validation_human_review_needed=bool(validation.get("human_review_needed")) if isinstance(validation, dict) else False,
        validation_errors=validation.get("errors") if isinstance(validation, dict) and isinstance(validation.get("errors"), list) else [],
    )


def conflict_key(entry: PartInfoEntry) -> tuple[str, str]:
    return ((entry.mpn or "").lower(), (entry.manufacturer or "").lower())


def part_entry_to_dict(entry: PartInfoEntry) -> dict[str, Any]:
    return {
        "file": entry.file,
        "schema_version": entry.schema_version,
        "mpn": entry.mpn,
        "manufacturer": entry.manufacturer,
        "normalized_mpn": entry.normalized_mpn,
        "component_category": entry.component_category,
        "confidence_overall": entry.confidence_overall,
        "human_reviewed": entry.human_reviewed,
        "unresolved_fields": entry.unresolved_fields,
        "validation_status": entry.validation_status,
        "validation_human_review_needed": entry.validation_human_review_needed,
        "validation_errors": entry.validation_errors,
    }


def bom_entry_to_dict(entry: BomEntry) -> dict[str, Any]:
    return {
        "row_index": entry.row_index,
        "refdes": entry.refdes,
        "mpn": entry.mpn,
        "manufacturer": entry.manufacturer,
        "normalized_mpn": entry.normalized_mpn,
        "raw": entry.raw,
    }


def build_index(
    *,
    project: str,
    bom_path: Path,
    part_info_dir: Path,
    validation_path: Path,
    part_files: list[Path],
    bom_entries: list[BomEntry],
    validation_rows: dict[str, dict[str, Any]],
    validation_warnings: list[str],
    strict: bool,
) -> dict[str, Any]:
    warnings = list(validation_warnings)
    errors: list[str] = []
    part_entries: list[PartInfoEntry] = []
    for path in part_files:
        try:
            part_entries.append(parse_part_info(path, validation_rows))
        except Exception as exc:
            errors.append(str(exc))

    by_mpn: dict[str, list[PartInfoEntry]] = {}
    for entry in part_entries:
        by_mpn.setdefault(entry.normalized_mpn, []).append(entry)

    mpns: dict[str, Any] = {}
    ambiguous: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    human_review_needed: list[dict[str, Any]] = []
    for normalized, entries in sorted(by_mpn.items()):
        conflict_keys = {conflict_key(entry) for entry in entries}
        is_ambiguous = len(entries) > 1 and len(conflict_keys) > 1
        if is_ambiguous:
            ambiguous.append({
                "normalized_mpn": normalized,
                "reason": "multiple part_info files share normalized_mpn with conflicting mpn/manufacturer",
                "files": [part_entry_to_dict(entry) for entry in entries],
            })
        for entry in entries:
            if entry.invalid:
                invalid.append({"normalized_mpn": normalized, "file": entry.file, "reason": "validation status invalid"})
            if entry.human_review_needed:
                human_review_needed.append({"normalized_mpn": normalized, "file": entry.file, "reason": "validation human_review_needed"})
        mpns[normalized] = {
            "normalized_mpn": normalized,
            "ambiguous": is_ambiguous,
            "files": [part_entry_to_dict(entry) for entry in entries],
            "bom_rows": [],
            "refdes": [],
        }

    refdes_index: dict[str, Any] = {}
    missing: list[dict[str, Any]] = []
    matched_refdes = 0
    for bom in bom_entries:
        if not bom.normalized_mpn:
            if bom.refdes:
                missing.append({"reason": "bom row missing mpn", "bom": bom_entry_to_dict(bom)})
            continue
        entry = mpns.get(bom.normalized_mpn)
        if entry is not None:
            entry["bom_rows"].append(bom_entry_to_dict(bom))
            entry["refdes"].extend(ref for ref in bom.refdes if ref not in entry["refdes"])
        candidates = by_mpn.get(bom.normalized_mpn, [])
        if not candidates:
            missing.append({"reason": "no matching part_info", "bom": bom_entry_to_dict(bom)})
            continue
        conflict_keys = {conflict_key(candidate) for candidate in candidates}
        if len(candidates) > 1 and len(conflict_keys) > 1:
            ambiguous.append({
                "normalized_mpn": bom.normalized_mpn,
                "reason": "BOM row matches ambiguous part_info key",
                "bom": bom_entry_to_dict(bom),
                "files": [part_entry_to_dict(candidate) for candidate in candidates],
            })
            continue
        valid_candidates = [candidate for candidate in candidates if not candidate.invalid]
        if not valid_candidates:
            invalid.append({"normalized_mpn": bom.normalized_mpn, "reason": "BOM row matches only invalid part_info", "bom": bom_entry_to_dict(bom)})
            continue
        selected = valid_candidates[0]
        for ref in bom.refdes:
            refdes_index[ref] = {
                "refdes": ref,
                "row_index": bom.row_index,
                "mpn": bom.mpn,
                "manufacturer": bom.manufacturer,
                "normalized_mpn": bom.normalized_mpn,
                "part_info_file": selected.file,
                "component_category": selected.component_category,
                "confidence_overall": selected.confidence_overall,
                "human_review_needed": selected.human_review_needed,
            }
            matched_refdes += 1

    strict_blockers = bool(missing or ambiguous or invalid or validation_warnings)

    summary = {
        "bom_rows": len(bom_entries),
        "bom_refdes_count": sum(len(entry.refdes) for entry in bom_entries),
        "part_info_files": len(part_entries),
        "indexed_mpns": len(mpns),
        "matched_refdes": matched_refdes,
        "missing_part_info": len(missing),
        "invalid_part_info": len(invalid),
        "ambiguous_part_info": len(ambiguous),
        "human_review_needed": len(human_review_needed),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "bom": str(bom_path),
            "part_info_dir": str(part_info_dir),
            "validation": str(validation_path),
        },
        "summary": summary,
        "mpns": mpns,
        "refdes": refdes_index,
        "missing": missing,
        "ambiguous": ambiguous,
        "invalid": invalid,
        "human_review_needed": human_review_needed,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "artifact_validation_pass": not errors,
        "overall_pass": not errors and (not strict or not strict_blockers),
    }


def write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ThomsonLint part_info index.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--bom", default=None)
    parser.add_argument("--part-info-dir", default=str(DEFAULT_PART_INFO_DIR))
    parser.add_argument("--validation", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--examples", action="store_true", help="Also index examples/part_info_examples/*.json and allow missing BOM")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when missing, ambiguous, invalid, or validation warnings exist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    bom_path = Path(args.bom) if args.bom else Path("exports") / f"{project}-bom.json"
    part_info_dir = Path(args.part_info_dir)
    validation_path = Path(args.validation) if args.validation else Path("exports") / f"{project}-part-info-validation.json"
    out_path = Path(args.out) if args.out else Path("exports/part_info/part_info_index.json")

    try:
        bom_entries: list[BomEntry] = []
        if bom_path.exists():
            bom_entries = parse_bom(load_json(bom_path))
        elif not args.examples:
            raise FileNotFoundError(f"missing BOM JSON: {bom_path}")

        part_files = collect_part_info_files(part_info_dir, args.examples)
        if not part_files and not bom_entries:
            raise ValueError(f"no part_info JSON files found in {part_info_dir}" + (" or examples" if args.examples else ""))

        validation_rows, validation_warnings = read_validation(validation_path)
        artifact = build_index(
            project=project,
            bom_path=bom_path,
            part_info_dir=part_info_dir,
            validation_path=validation_path,
            part_files=part_files,
            bom_entries=bom_entries,
            validation_rows=validation_rows,
            validation_warnings=validation_warnings,
            strict=args.strict,
        )
        write_artifact(out_path, artifact)
    except Exception as exc:
        artifact = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "generated_at_utc": utc_now(),
            "sources": {"bom": str(bom_path), "part_info_dir": str(part_info_dir), "validation": str(validation_path)},
            "summary": {
                "bom_rows": 0,
                "bom_refdes_count": 0,
                "part_info_files": 0,
                "indexed_mpns": 0,
                "matched_refdes": 0,
                "missing_part_info": 0,
                "invalid_part_info": 0,
                "ambiguous_part_info": 0,
                "human_review_needed": 0,
            },
            "mpns": {},
            "refdes": {},
            "missing": [],
            "ambiguous": [],
            "invalid": [],
            "human_review_needed": [],
            "warnings": [],
            "errors": [str(exc)],
            "execution_pass": False,
            "artifact_validation_pass": False,
            "overall_pass": False,
        }
        try:
            write_artifact(out_path, artifact)
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "part_info index: "
        f"part_info_files={summary['part_info_files']} indexed_mpns={summary['indexed_mpns']} "
        f"matched_refdes={summary['matched_refdes']} missing={summary['missing_part_info']} "
        f"ambiguous={summary['ambiguous_part_info']} invalid={summary['invalid_part_info']} out={out_path}"
    )
    return 1 if args.strict and not artifact["overall_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
