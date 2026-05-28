#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from datasheet_smart_match import score_best_pdf_match

ALLOWED_STATUSES = {
    "local",
    "found",
    "ambiguous",
    "missing",
    "error",
    "not_applicable_generic",
}

FORBIDDEN_STATUSES = {
    "found/url_only",
    "download_unavailable",
    "missing_generic",
}


def fail(msg: str) -> None:
    print(f"INVALID: {msg}")
    sys.exit(1)


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


APPROVED_EQUIVALENT_PREFIXES = {
    "active",
    "capacitor",
    "connector",
    "crystal",
    "diode",
    "ferrite",
    "fuse",
    "ic",
    "inductor",
    "led",
    "mosfet",
    "relay",
    "resistor",
    "switch",
    "transistor",
}


def strip_approved_equivalent_prefix(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    prefix, sep, rest = text.partition(":")
    if sep and prefix.strip().lower() in APPROVED_EQUIVALENT_PREFIXES:
        stripped = rest.strip()
        return stripped or None

    return text


def is_unresolved_status_requiring_search(status: Any) -> bool:
    return status in {"ambiguous", "missing", "error"}


def bom_candidate_paths(project: str, input_dir: Path) -> list[Path]:
    candidates = [
        input_dir / f"{project}_bom.csv",
        input_dir / project / "bom.csv",
        input_dir / project / "BOM.csv",
    ]
    candidates.extend(sorted((input_dir / project / "bom").glob("*.csv")))

    if project == "example":
        candidates.append(input_dir / "example_bom.csv")

    deduped: list[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def find_raw_bom(project: str, input_dir: Path) -> Path:
    candidates = bom_candidate_paths(project, input_dir)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    fail(
        "missing raw BOM for project "
        f"{project!r}; searched: {', '.join(str(path) for path in candidates)}"
    )


def read_bom_rows(raw_bom: Path) -> list[dict[str, str]]:
    if not raw_bom.exists():
        fail(f"missing raw BOM: {raw_bom}")

    with raw_bom.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_manifest_rows(datasheet_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    manifest_jsonl = datasheet_dir / "datasheet_manifest.jsonl"
    manifest_json = datasheet_dir / "datasheet_manifest.json"

    if manifest_jsonl.exists():
        rows = []
        for line_no, line in enumerate(manifest_jsonl.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                fail(f"invalid JSONL row {line_no}: {exc}")
            if not isinstance(row, dict):
                fail(f"manifest row {line_no} is not an object")
            row["approved_equivalent_or_family_match"] = strip_approved_equivalent_prefix(
                row.get("approved_equivalent_or_family_match")
            )
            rows.append(row)
        return manifest_jsonl, rows

    if manifest_json.exists():
        try:
            data = json.loads(manifest_json.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid legacy JSON manifest: {exc}")
        rows = data.get("rows")
        if not isinstance(rows, list):
            fail(f"legacy JSON manifest has no rows[]: {manifest_json}")
        # Strict new phase should produce JSONL, but keep this readable so it can fail with useful details.
        for row in rows:
            if isinstance(row, dict):
                row["approved_equivalent_or_family_match"] = strip_approved_equivalent_prefix(
                    row.get("approved_equivalent_or_family_match")
                )
        return manifest_json, rows

    fail(f"missing manifest: expected {manifest_jsonl}")


def has_concrete_mpn_from_raw(raw: dict[str, Any]) -> bool:
    mpns = [
        raw.get("MFG P/N_1"),
        raw.get("MFG P/N_2"),
        raw.get("MFG P/N_3"),
    ]
    return any(str(x or "").strip() and str(x or "").strip() != "?" for x in mpns)


def is_clear_non_device_without_mpn(raw: dict[str, Any]) -> bool:
    item = str(raw.get("ITEM NAME") or "").upper()
    desc = str(raw.get("DESCRIPTION") or "").upper()
    refdes = str(raw.get("REF DES") or "").upper()

    if has_concrete_mpn_from_raw(raw):
        return False

    non_device_markers = [
        "LBL",
        "SCH",
        "PCB",
        "FAB",
        "ASY",
        "SERIALNUM",
        "DOCUMENT",
        "DRAWING",
    ]

    return (
        any(item.startswith(x) for x in non_device_markers)
        or any(x + "_" in desc for x in ["SCH", "PCB", "FAB", "ASY", "LBL"])
        or refdes.startswith(("SCH", "PCB", "FAB", "ASM"))
        or not any(str(raw.get(k) or "").strip() for k in ["MFG_1", "MFG P/N_1", "MFG_2", "MFG P/N_2", "MFG_3", "MFG P/N_3"])
    )


def resolve_local_path(row: dict[str, Any], datasheet_dir: Path, root_datasheet_dir: Path) -> Path | None:
    value = row.get("local_saved_path") or row.get("local_file")
    if not value:
        return None

    p = Path(str(value))
    if p.is_absolute():
        return p

    if p.exists():
        return p

    for base in [datasheet_dir, root_datasheet_dir]:
        candidate = base / p
        if candidate.exists():
            return candidate
        candidate = base / p.name
        if candidate.exists():
            return candidate

    return p


def pdftotext(pdf: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf), "-"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pdftotext failed")
    return result.stdout


def mpn_candidates(row: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    out = []

    for key in ["selected_mpn", "mpn"]:
        v = row.get(key)
        if v:
            out.append(str(v))

    vals = row.get("mpn_candidates")
    if isinstance(vals, list):
        out += [str(x) for x in vals if str(x or "").strip()]

    for key in ["MFG P/N_1", "MFG P/N_2", "MFG P/N_3"]:
        v = raw.get(key)
        if v:
            out.append(str(v))

    expanded = []
    for x in out:
        x = x.strip()
        if not x:
            continue
        expanded.append(x)
        expanded.append(x.split(",")[0].strip())
        expanded.append(re.sub(r"\([^)]*\)", "", x).strip())
        expanded.append(x.replace(" ", ""))

    deduped = []
    seen = set()
    for x in expanded:
        nx = norm(x)
        if nx and nx not in seen:
            seen.add(nx)
            deduped.append(x)
    return deduped


def mpn_candidate_pairs(row: dict[str, Any], raw: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    selected_mpn = row.get("selected_mpn") or row.get("mpn")
    selected_manufacturer = row.get("selected_manufacturer")
    if selected_mpn:
        pairs.append((str(selected_mpn), str(selected_manufacturer or "")))

    row_mpns = row.get("mpn_candidates")
    row_mfgs = row.get("manufacturer_candidates")
    if isinstance(row_mpns, list):
        for index, mpn in enumerate(row_mpns):
            manufacturer = ""
            if isinstance(row_mfgs, list) and index < len(row_mfgs):
                manufacturer = str(row_mfgs[index] or "")
            if str(mpn or "").strip():
                pairs.append((str(mpn), manufacturer))

    for n in ("1", "2", "3"):
        mpn = raw.get(f"MFG P/N_{n}")
        manufacturer = raw.get(f"MFG_{n}")
        if mpn:
            pairs.append((str(mpn), str(manufacturer or "")))

    deduped: list[tuple[str, str]] = []
    seen = set()
    for mpn, manufacturer in pairs:
        mpn = mpn.strip()
        manufacturer = manufacturer.strip()
        key = (norm(mpn), norm(manufacturer))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        deduped.append((mpn, manufacturer))
    return deduped


def pdf_contains_mpn(row: dict[str, Any], raw: dict[str, Any], text: str) -> tuple[bool, str | None]:
    text_n = norm(text)

    approved = strip_approved_equivalent_prefix(row.get("approved_equivalent_or_family_match"))
    approved_n = norm(approved)
    if approved and approved_n and len(approved_n) >= 5 and approved_n in text_n:
        return True, str(approved)

    candidates = mpn_candidates(row, raw)
    for mpn in candidates:
        n = norm(mpn)
        if not n:
            continue
        if len(n) < 5:
            continue
        if re.fullmatch(r"\d+r\d*|\d+k\d*|\d+m\d*|\d+", n, flags=re.I):
            continue
        if n in text_n:
            return True, mpn

    # Smart-family fallback for connector/passive family datasheets.
    description = row.get("description") or raw.get("DESCRIPTION") or ""
    source_url = row.get("selected_url") or row.get("local_saved_path") or ""

    smart_results = [
        score_best_pdf_match(
            mpns=[mpn],
            description=description,
            manufacturer=manufacturer,
            pdf_text=text,
            url=source_url,
        )
        for mpn, manufacturer in mpn_candidate_pairs(row, raw)
    ]

    order = {"accept": 2, "needs_review": 1, "reject": 0}
    smart = (
        sorted(smart_results, key=lambda r: (order.get(r.get("decision"), 0), r.get("score") or 0), reverse=True)[0]
        if smart_results
        else {"decision": "reject", "matched": None}
    )

    if smart.get("decision") == "accept":
        return True, str(strip_approved_equivalent_prefix(smart.get("matched")))

    return False, None


def validate_pdf_for_row(path: Path, row: dict[str, Any], raw: dict[str, Any]) -> tuple[bool, str]:
    if not path.exists():
        return False, "file does not exist"

    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"cannot stat file: {exc}"

    if size < 1024:
        return False, f"file too small: {size} bytes"

    try:
        magic = path.read_bytes()[:5]
    except Exception as exc:
        return False, f"cannot read magic: {exc}"

    if magic != b"%PDF-":
        return False, f"bad PDF magic: {magic!r}"

    try:
        text = pdftotext(path)
    except Exception as exc:
        return False, f"pdftotext failed: {exc}"

    ok, match = pdf_contains_mpn(row, raw, text)
    if not ok:
        return False, "MPN/equivalent not found in extracted text"

    return True, f"verified match: {match}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict Phase 6 datasheet manifest audit")
    parser.add_argument("--project", default="example")
    parser.add_argument("--exports", default="exports")
    parser.add_argument("--input-dir", default="input")
    parser.add_argument("--datasheets", default="datasheets")
    args = parser.parse_args()

    exports = Path(args.exports)
    input_dir = Path(args.input_dir)
    datasheet_dir = exports / "datasheets"
    root_datasheet_dir = Path(args.datasheets)
    validation_json = datasheet_dir / "datasheet_manifest_validation.json"
    raw_bom = find_raw_bom(args.project, input_dir)

    bom_rows = read_bom_rows(raw_bom)
    bom_count = len(bom_rows)
    manifest_path, rows = load_manifest_rows(datasheet_dir)

    print("== Phase 6 strict datasheet audit ==")
    print(f"project: {args.project}")
    print(f"raw_bom: {raw_bom}")
    print(f"bom_rows: {bom_count}")
    print(f"manifest_path: {manifest_path}")
    print(f"manifest_rows: {len(rows)}")

    failures: dict[str, list[Any]] = {
        "manifest_row_count_mismatch": [],
        "missing_bom_row_indexes": [],
        "duplicate_bom_row_indexes": [],
        "extra_bom_row_indexes": [],
        "invalid_statuses": [],
        "forbidden_statuses": [],
        "error_status_rows": [],
        "concrete_mpn_rows_not_found_or_local": [],
        "concrete_mpn_rows_not_searched": [],
        "concrete_mpn_rows_marked_not_applicable": [],
        "concrete_mpn_rows_missing_verified_pdf": [],
        "no_mpn_rows_not_not_applicable": [],
    }

    if len(rows) != bom_count:
        failures["manifest_row_count_mismatch"].append((len(rows), bom_count))

    by_idx: dict[int, dict[str, Any]] = {}
    duplicates = []

    for fallback_idx, row in enumerate(rows, 1):
        idx = row.get("bom_row_index", fallback_idx)
        try:
            idx = int(idx)
        except Exception:
            idx = fallback_idx

        if idx in by_idx:
            duplicates.append(idx)
        by_idx[idx] = row

    expected = set(range(1, bom_count + 1))
    actual = set(by_idx)

    failures["missing_bom_row_indexes"].extend(sorted(expected - actual))
    failures["extra_bom_row_indexes"].extend(sorted(actual - expected))
    failures["duplicate_bom_row_indexes"].extend(sorted(set(duplicates)))

    for idx in sorted(expected & actual):
        raw = bom_rows[idx - 1]
        row = by_idx[idx]
        status = row.get("status")

        if status not in ALLOWED_STATUSES:
            failures["invalid_statuses"].append((idx, status))
        if status in FORBIDDEN_STATUSES:
            failures["forbidden_statuses"].append((idx, status))
        if status == "error":
            failures["error_status_rows"].append((idx, status, raw.get("DESCRIPTION")))

        has_mpn = has_concrete_mpn_from_raw(raw)
        clear_non_device = is_clear_non_device_without_mpn(raw)

        if not has_mpn:
            if status != "not_applicable_generic" and clear_non_device:
                failures["no_mpn_rows_not_not_applicable"].append((idx, status, raw.get("DESCRIPTION")))
            continue

        # Phase 6 policy:
        # Concrete MPN rows may remain ambiguous/missing after helper processing.
        # The blocking requirement is that they were processed/searched and that
        # any found/local rows have a verified PDF.
        if status == "not_applicable_generic":
            failures["concrete_mpn_rows_marked_not_applicable"].append(
                (idx, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if status not in {"found", "local"}:
            failures["concrete_mpn_rows_not_found_or_local"].append(
                (idx, status, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if is_unresolved_status_requiring_search(status) and row.get("search_attempted") is not True:
            failures["concrete_mpn_rows_not_searched"].append(
                (idx, status, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if status in {"found", "local"}:
            path = resolve_local_path(row, datasheet_dir, root_datasheet_dir)
            if path is None:
                failures["concrete_mpn_rows_missing_verified_pdf"].append((idx, status, "no local_saved_path/local_file"))
            else:
                ok, reason = validate_pdf_for_row(path, row, raw)
                if not ok:
                    failures["concrete_mpn_rows_missing_verified_pdf"].append((idx, status, str(path), reason))

    status_counts: dict[str, int] = {}
    for row in rows:
        s = str(row.get("status"))
        status_counts[s] = status_counts.get(s, 0) + 1
    print(f"status_counts: {status_counts}")

    any_failures = False
    report_only_failures = {"concrete_mpn_rows_not_found_or_local"}
    for name, items in failures.items():
        if not items:
            continue
        if name not in report_only_failures:
            any_failures = True
        print(f"\n{name}: {len(items)}" + (" (report-only)" if name in report_only_failures else ""))
        for item in items[:40]:
            print(f"  {item}")
        if len(items) > 40:
            print(f"  ... {len(items) - 40} more")

    if validation_json.exists():
        try:
            validation = json.loads(validation_json.read_text(encoding="utf-8"))
            if validation.get("overall_pass") is not True:
                any_failures = True
                print(f"\nvalidation overall_pass is not true: {validation.get('overall_pass')!r}")
        except Exception as exc:
            any_failures = True
            print(f"\nvalidation JSON parse failed: {exc}")
    else:
        any_failures = True
        print(f"\nmissing validation JSON: {validation_json}")

    if any_failures:
        fail("strict Phase 6 datasheet audit failed")

    print("PASS: strict Phase 6 datasheet audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
