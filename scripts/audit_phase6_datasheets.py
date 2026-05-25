#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from datasheet_smart_match import score_best_pdf_match


RAW_BOM = Path("input/example_bom.csv")
DATASHEET_DIR = Path("exports/datasheets")
ROOT_DATASHEET_DIR = Path("datasheets")
MANIFEST_JSONL = DATASHEET_DIR / "datasheet_manifest.jsonl"
MANIFEST_JSON = DATASHEET_DIR / "datasheet_manifest.json"
VALIDATION_JSON = DATASHEET_DIR / "datasheet_manifest_validation.json"

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


def read_bom_rows() -> list[dict[str, str]]:
    if not RAW_BOM.exists():
        fail(f"missing raw BOM: {RAW_BOM}")

    with RAW_BOM.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_manifest_rows() -> tuple[Path, list[dict[str, Any]]]:
    if MANIFEST_JSONL.exists():
        rows = []
        for line_no, line in enumerate(MANIFEST_JSONL.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                fail(f"invalid JSONL row {line_no}: {exc}")
            if not isinstance(row, dict):
                fail(f"manifest row {line_no} is not an object")
            rows.append(row)
        return MANIFEST_JSONL, rows

    if MANIFEST_JSON.exists():
        try:
            data = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid legacy JSON manifest: {exc}")
        rows = data.get("rows")
        if not isinstance(rows, list):
            fail(f"legacy JSON manifest has no rows[]: {MANIFEST_JSON}")
        # Strict new phase should produce JSONL, but keep this readable so it can fail with useful details.
        return MANIFEST_JSON, rows

    fail(f"missing manifest: expected {MANIFEST_JSONL}")


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


def resolve_local_path(row: dict[str, Any]) -> Path | None:
    value = row.get("local_saved_path") or row.get("local_file")
    if not value:
        return None

    p = Path(str(value))
    if p.is_absolute():
        return p

    if p.exists():
        return p

    for base in [DATASHEET_DIR, ROOT_DATASHEET_DIR]:
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


def pdf_contains_mpn(row: dict[str, Any], raw: dict[str, Any], text: str) -> tuple[bool, str | None]:
    text_n = norm(text)

    approved = row.get("approved_equivalent_or_family_match")
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
    manufacturer = (
        row.get("selected_manufacturer")
        or raw.get("MFG_1")
        or raw.get("MFG_2")
        or raw.get("MFG_3")
        or ""
    )
    description = row.get("description") or raw.get("DESCRIPTION") or ""
    source_url = row.get("selected_url") or row.get("local_saved_path") or ""

    smart = score_best_pdf_match(
        mpns=candidates,
        description=description,
        manufacturer=manufacturer,
        pdf_text=text,
        url=source_url,
    )

    if smart.get("decision") == "accept":
        return True, str(smart.get("matched"))

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
    bom_rows = read_bom_rows()
    bom_count = len(bom_rows)
    manifest_path, rows = load_manifest_rows()

    print("== Phase 6 strict datasheet audit ==")
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

        has_mpn = has_concrete_mpn_from_raw(raw)
        clear_non_device = is_clear_non_device_without_mpn(raw)

        if not has_mpn:
            if status != "not_applicable_generic" and clear_non_device:
                failures["no_mpn_rows_not_not_applicable"].append((idx, status, raw.get("DESCRIPTION")))
            continue

        # New hard rule:
        # Every concrete MPN row must be found/local with a verified datasheet.
        if status == "not_applicable_generic":
            failures["concrete_mpn_rows_marked_not_applicable"].append(
                (idx, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if status not in {"found", "local"}:
            failures["concrete_mpn_rows_not_found_or_local"].append(
                (idx, status, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if status != "local" and row.get("search_attempted") is not True:
            failures["concrete_mpn_rows_not_searched"].append(
                (idx, status, raw.get("DESCRIPTION"), [raw.get("MFG P/N_1"), raw.get("MFG P/N_2"), raw.get("MFG P/N_3")])
            )

        if status in {"found", "local"}:
            path = resolve_local_path(row)
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
    for name, items in failures.items():
        if not items:
            continue
        any_failures = True
        print(f"\n{name}: {len(items)}")
        for item in items[:40]:
            print(f"  {item}")
        if len(items) > 40:
            print(f"  ... {len(items) - 40} more")

    if VALIDATION_JSON.exists():
        try:
            validation = json.loads(VALIDATION_JSON.read_text(encoding="utf-8"))
            if validation.get("overall_pass") is not True:
                any_failures = True
                print(f"\nvalidation overall_pass is not true: {validation.get('overall_pass')!r}")
        except Exception as exc:
            any_failures = True
            print(f"\nvalidation JSON parse failed: {exc}")
    else:
        any_failures = True
        print(f"\nmissing validation JSON: {VALIDATION_JSON}")

    if any_failures:
        fail("strict Phase 6 datasheet audit failed")

    print("PASS: strict Phase 6 datasheet audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
