#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from datasheet_smart_match import score_best_pdf_match


ROOT = Path.cwd()
PROJECT = "example"

INPUT_BOM = ROOT / "input" / "example_bom.csv"
ROOT_DATASHEETS = ROOT / "datasheets"
EXPORT_DATASHEETS = ROOT / "exports" / "datasheets"
MANIFEST_JSONL = EXPORT_DATASHEETS / "datasheet_manifest.jsonl"
VALIDATION_JSON = EXPORT_DATASHEETS / "datasheet_manifest_validation.json"
CHECKPOINTS_JSONL = ROOT / "exports" / "example-phase-checkpoints.jsonl"
MANUAL_DOWNLOADS_JSON = ROOT / ".agents_tmp" / "datasheet_manual_downloads.json"

SEARXNG_BASE = os.environ.get("SEARXNG_BASE", "http://192.168.5.5:8888")

MIN_PDF_SIZE = 1024
MAX_QUERIES_PER_ROW = 10
MAX_SEARCH_RESULTS_PER_QUERY = 8
MAX_DOWNLOAD_ATTEMPTS_PER_ROW = 12
FETCH_TIMEOUT = 25

ALLOWED_STATUSES = {
    "local",
    "found",
    "ambiguous",
    "missing",
    "not_applicable_generic",
}

DISTRIBUTOR_DOMAINS = (
    "digikey.",
    "mouser.",
    "arrow.",
    "avnet.",
    "newark.",
    "element14.",
    "farnell.",
    "rs-online.",
    "ttiinc.",
    "octopart.",
)

PDF_MIRROR_DOMAINS = (
    "alldatasheet",
    "datasheetarchive",
    "datasheetspdf",
    "datasheetq",
    "datasheet-pdf",
)

MANUFACTURER_DOMAINS = {
    "texas instruments": ["ti.com"],
    "ti": ["ti.com"],
    "nxp": ["nxp.com"],
    "nexperia": ["nexperia.com"],
    "diodes incorporated": ["diodes.com"],
    "diodes": ["diodes.com"],
    "onsemi": ["onsemi.com"],
    "on semiconductor": ["onsemi.com"],
    "infineon": ["infineon.com"],
    "microchip": ["microchip.com"],
    "analog": ["analog.com"],
    "stmicroelectronics": ["st.com"],
    "st": ["st.com"],
    "murata": ["murata.com"],
    "tdk": ["tdk.com"],
    "kemet": ["kemet.com"],
    "kyocera avx": ["kyocera-avx.com"],
    "avx": ["kyocera-avx.com"],
    "samsung": ["samsungsem.com"],
    "te connectivity": ["te.com"],
    "molex": ["molex.com"],
    "samtec": ["samtec.com"],
    "jst": ["jst.com"],
    "amphenol": ["amphenol-cs.com", "amphenol.com"],
    "harwin": ["harwin.com"],
    "keystone": ["keyelco.com"],
    "stackpole": ["seielect.com"],
    "vishay dale": ["vishay.com"],
    "vishay": ["vishay.com"],
    "yageo": ["yageo.com"],
    "panasonic": ["panasonic.com"],
    "koa speer": ["koaspeer.com"],
    "littelfuse": ["littelfuse.com"],
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    value = value.strip("._-")
    return value[:120] or "datasheet"


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def is_distributor_url(url: str) -> bool:
    d = domain_of(url)
    return any(x in d for x in DISTRIBUTOR_DOMAINS)


def is_mirror_url(url: str) -> bool:
    d = domain_of(url)
    return any(x in d for x in PDF_MIRROR_DOMAINS)


def is_probable_pdf_url(url: str) -> bool:
    u = url.lower()
    return ".pdf" in u or "datasheet" in u and "pdf" in u


def request_bytes(url: str, timeout: int = FETCH_TIMEOUT) -> tuple[bytes | None, str | None, str | None]:
    headers = {
        "User-Agent": "ThomsonLint-DatasheetHelper/1.0",
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type")
            data = resp.read()
        return data, content_type, None
    except Exception as exc:
        return None, None, str(exc)


def bom_rows(path: Path = INPUT_BOM) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing BOM: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = []
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, 1):
            rows.append({
                "bom_row_index": idx,
                "raw": {k: (v or "").strip() for k, v in row.items()},
            })
        return rows


def mpn_pairs(raw: dict[str, str]) -> list[dict[str, Any]]:
    pairs = []
    for n in ("1", "2", "3"):
        mfg = raw.get(f"MFG_{n}", "").strip()
        mpn = raw.get(f"MFG P/N_{n}", "").strip()
        if mfg and mpn and mpn != "?":
            pairs.append({"manufacturer": mfg, "mpn": mpn, "rank": int(n)})
    return pairs


def mpn_variants(mpn: str) -> list[str]:
    """Return exact and safe orderable/family variants for text verification."""
    original = str(mpn or "").strip()
    no_comma_suffix = original.split(",")[0].strip()
    no_parens = re.sub(r"\([^)]*\)", "", original).strip()
    no_space = original.replace(" ", "")
    no_hyphen = no_parens.replace("-", "")

    variants = [
        original,
        no_comma_suffix,
        no_parens,
        no_space,
        no_hyphen,
    ]

    # Common passive/orderable suffix handling.
    # These variants are intentionally conservative: they only remove likely
    # packaging/termination/order suffixes from already-specific part strings.
    base = no_comma_suffix or no_parens or original

    # Murata MLCC examples:
    # GRM155R71H104KE14D -> GRM155R71H104KE14
    if re.match(r"^GRM[A-Z0-9]+$", base, flags=re.I) and len(base) > 8:
        variants.append(base[:-1])

    # Samsung MLCC examples:
    # CL05B104KB5NNNC -> CL05B104KB5NNN
    # CL21A106KBYQNNE -> CL21A106KBYQNN
    if re.match(r"^CL\d{2}[A-Z0-9]+$", base, flags=re.I) and len(base) > 8:
        variants.append(base[:-1])

    # AVX/Kyocera MLCC examples:
    # 04025C104KAT2A -> 04025C104KAT2
    # 0402ZD106MAT2A -> 0402ZD106MAT2
    if re.match(r"^\d{4}[A-Z0-9]+$", base, flags=re.I) and len(base) > 8:
        variants.append(base[:-1])

    # Resistor series/value family variants.
    # RMCF0402FT4K70 -> RMCF0402, RMCF, 4K70
    m = re.match(r"^(RMCF\d{4})[A-Z0-9]*?(\d+[RK]\d+)$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), "RMCF", m.group(2)])

    # CRCW04024K70FKED -> CRCW0402, CRCW, 4K70
    m = re.match(r"^(CRCW\d{4})(\d+[RK]\d+)[A-Z0-9]*$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), "CRCW", m.group(2)])

    # RC0402FR-074K7L -> RC0402, RC0402FR, 4K7
    m = re.match(r"^(RC\d{4})([A-Z]+)?-?\d*(\d+[RK]\d*)[A-Z]*$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), (m.group(1) + (m.group(2) or "")), m.group(3)])

    # TE/product-family connector examples:
    # 1761608-3 -> 1761608
    m = re.match(r"^(\d{6,})-\d+$", base)
    if m:
        variants.append(m.group(1))

    out = []
    seen = set()
    for v in variants:
        nv = norm(v)
        if nv and nv not in seen:
            seen.add(nv)
            out.append(v)
    return out



def family_variants(mpn: str) -> list[str]:
    """Return broader family names likely used in datasheet filenames."""
    base = str(mpn or "").strip()
    base = base.split(",")[0].strip()
    base = re.sub(r"\([^)]*\)", "", base).strip()

    variants = []
    if base:
        variants.append(base)

    # IC/orderable package suffixes.
    suffix_re = (
        r"(DGKR|DGSR|DCKR|PWR|PW|DR|D|DBV|DBVR|DBVT|"
        r"ADP|GW|SE-7|H6327XTSA1|XTSA1)$"
    )

    stripped = re.sub(suffix_re, "", base, flags=re.I)
    if stripped and stripped != base:
        variants.append(stripped)

    # PCA9515BDGKR -> PCA9515B, PCA9515
    m = re.match(r"^(PCA\d+[A-Z]?)", base, flags=re.I)
    if m:
        v = m.group(1)
        variants.append(v)
        variants.append(re.sub(r"[A-Z]$", "", v, flags=re.I))

    # SN74LVC157APWR -> SN74LVC157A, SN74LVC157
    # SN74AHCT1G125DCKR -> SN74AHCT1G125
    m = re.match(r"^((?:SN)?74[A-Z0-9]+?)(?:DCKR|PWR|PW|DR|D)?$", base, flags=re.I)
    if m:
        v = m.group(1)
        variants.append(v)
        variants.append(re.sub(r"[A-Z]$", "", v, flags=re.I))

    # TS5A22362DGSR -> TS5A22362
    m = re.match(r"^(TS\d+[A-Z0-9]*?)(?:DGSR|DCKR|PWR|PW|DR|D)?$", base, flags=re.I)
    if m:
        variants.append(m.group(1))

    # TCAN3413DR -> TCAN3413
    m = re.match(r"^(TCAN\d+)(?:DR|D)?$", base, flags=re.I)
    if m:
        variants.append(m.group(1))

    # AP2127K-3.3TRG1 -> AP2127
    m = re.match(r"^(AP\d+)", base, flags=re.I)
    if m:
        variants.append(m.group(1))

    # MOSFET families.
    # FDS4435BZ -> FDS4435
    m = re.match(r"^([A-Z]+\d+)[A-Z]*$", base, flags=re.I)
    if m:
        variants.append(m.group(1))

    # TE/product-family connector examples:
    # 1761608-3 -> 1761608
    m = re.match(r"^(\d{6,})-\d+$", base)
    if m:
        variants.append(m.group(1))

    # Resistor / capacitor family helpers.
    # RMCF0402FT4K70 -> RMCF0402, RMCF, 4K70
    m = re.match(r"^(RMCF\d{4})[A-Z0-9]*?(\d+[RK]\d+)$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), "RMCF", m.group(2)])

    # CRCW04024K70FKED -> CRCW0402, CRCW, 4K70
    m = re.match(r"^(CRCW\d{4})(\d+[RK]\d+)[A-Z0-9]*$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), "CRCW", m.group(2)])

    # RC0402FR-074K7L -> RC0402, RC0402FR, 4K7
    m = re.match(r"^(RC\d{4})([A-Z]+)?-?\d*(\d+[RK]\d*)[A-Z]*$", base, flags=re.I)
    if m:
        variants.extend([m.group(1), (m.group(1) + (m.group(2) or "")), m.group(3)])

    out = []
    seen = set()
    for v in variants:
        nv = norm(v)
        if nv and nv not in seen:
            seen.add(nv)
            out.append(v)
    return out


def manufacturer_domains(manufacturer: str) -> list[str]:
    m = str(manufacturer or "").lower()
    out = []
    for key, domains in MANUFACTURER_DOMAINS.items():
        if key in m:
            out.extend(domains)
    return list(dict.fromkeys(out))


def direct_url_guesses(manufacturer: str, mpn: str) -> list[str]:
    """Legitimate direct URL guesses. No CAPTCHA or bot-block evasion."""
    variants = []
    variants.extend(mpn_variants(mpn))
    variants.extend(family_variants(mpn))

    normalized = []
    seen_norm = set()
    for v in variants:
        nv = norm(v)
        if nv and nv not in seen_norm:
            seen_norm.add(nv)
            normalized.append(v.lower())

    m = manufacturer.lower()
    urls = []

    if "texas instruments" in m or m == "ti":
        for v in normalized:
            urls.append(f"https://www.ti.com/lit/ds/symlink/{v}.pdf")

    if "onsemi" in m or "on semiconductor" in m:
        for v in normalized:
            urls.append(f"https://www.onsemi.com/pdf/datasheet/{v}-d.pdf")

    if "nexperia" in m:
        for v in normalized:
            urls.append(f"https://assets.nexperia.com/documents/data-sheet/{v.upper()}.pdf")

    if "nxp" in m:
        for v in normalized:
            urls.append(f"https://www.nxp.com/docs/en/data-sheet/{v.upper()}.pdf")

    if "diodes" in m:
        for v in normalized:
            urls.append(f"https://www.diodes.com/assets/Datasheets/{v.upper()}.pdf")

    if "infineon" in m:
        for v in normalized:
            urls.append(f"https://www.infineon.com/dgdl/{v.upper()}.pdf")

    deduped = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def build_queries(manufacturer: str, mpn: str) -> list[str]:
    variants = mpn_variants(mpn)
    primary = variants[0]
    no_suffix = variants[1] if len(variants) > 1 else primary
    domains = manufacturer_domains(manufacturer)

    queries = [
        f'{manufacturer} {primary} datasheet pdf',
        f'"{primary}" datasheet pdf',
        f'"{primary}" filetype:pdf',
        f'"{primary}" "datasheet"',
        f'"{primary}" "data sheet"',
        f'"{primary}" "product specification"',
        f'"{primary}" "technical datasheet"',
        f'"{manufacturer}" "{primary}"',
        f'"{no_suffix}" datasheet pdf',
        f'"{norm(no_suffix)}" datasheet pdf',
    ]

    for domain in domains:
        queries.insert(1, f'"{primary}" datasheet site:{domain}')
        queries.insert(2, f'{manufacturer} "{primary}" site:{domain}')

    deduped = []
    seen = set()
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped[:MAX_QUERIES_PER_ROW]


def searxng_search(query: str, limit: int = MAX_SEARCH_RESULTS_PER_QUERY) -> list[str]:
    encoded = urllib.parse.quote(query, safe="")
    url = f"{SEARXNG_BASE}/search?q={encoded}&format=json"
    data, _, err = request_bytes(url, timeout=20)
    if err or data is None:
        return []
    try:
        parsed = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return []
    urls = []
    for r in parsed.get("results", []):
        u = r.get("url")
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in urls:
            urls.append(u)
    return urls[:limit]


def extract_pdf_links_from_html(base_url: str, html_bytes: bytes) -> list[str]:
    text = html_bytes.decode("utf-8", "replace")
    links = []

    # href="...pdf..."
    for match in re.finditer(r'''href=["']([^"']+)["']''', text, flags=re.I):
        href = match.group(1)
        if "pdf" in href.lower() or "datasheet" in href.lower():
            links.append(urljoin(base_url, href))

    # Plain URLs in JS/text
    for match in re.finditer(r'''https?://[^\s"'<>]+''', text, flags=re.I):
        u = match.group(0)
        if "pdf" in u.lower() or "datasheet" in u.lower():
            links.append(u)

    deduped = []
    seen = set()
    for link in links:
        clean = link.replace("\\/", "/")
        if clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped[:20]


def resolve_candidate_urls(url: str) -> list[dict[str, Any]]:
    """Turn a candidate URL into direct PDF candidates where possible."""
    resolved = []
    d = domain_of(url)

    data, content_type, err = request_bytes(url, timeout=FETCH_TIMEOUT)

    if err or data is None:
        resolved.append({
            "url": url,
            "source_url": url,
            "resolution": "fetch_failed",
            "domain": d,
            "error": err,
            "direct_pdf_hint": is_probable_pdf_url(url),
            "distributor": is_distributor_url(url),
        })
        return resolved

    if data[:5] == b"%PDF-":
        resolved.append({
            "url": url,
            "source_url": url,
            "resolution": "fetched_direct_pdf",
            "domain": d,
        })
        return resolved

    ctype = (content_type or "").lower()
    if "html" in ctype or b"<html" in data[:1000].lower():
        links = extract_pdf_links_from_html(url, data)
        if links:
            for link in links:
                resolved.append({
                    "url": link,
                    "source_url": url,
                    "resolution": "html_extracted_pdf_link",
                    "domain": domain_of(link),
                })
        else:
            resolved.append({
                "url": url,
                "source_url": url,
                "resolution": "html_no_pdf_link_extracted",
                "domain": d,
                "distributor": is_distributor_url(url),
            })
        return resolved

    resolved.append({
        "url": url,
        "source_url": url,
        "resolution": "non_pdf_non_html",
        "domain": d,
        "content_type": content_type,
    })
    return resolved


def run_pdftotext(pdf_path: Path) -> tuple[bool, str, str | None]:
    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            text=True,
            capture_output=True,
            timeout=25,
        )
    except Exception as exc:
        return False, "", str(exc)

    if result.returncode != 0:
        return False, "", result.stderr.strip() or "pdftotext failed"

    return True, result.stdout, None


def validate_pdf_for_mpn(pdf_path: Path, mpns: list[str], description: str = "", manufacturer: str = "", source_url: str = "") -> dict[str, Any]:
    out = {
        "path": str(pdf_path),
        "exists": pdf_path.exists(),
        "size_bytes": None,
        "pdf_magic_valid": False,
        "pdftotext_succeeded": False,
        "mpn_text_verified": False,
        "matched_mpn": None,
        "smart_match": None,
        "match_type": None,
        "match_score": None,
        "match_evidence": [],
        "match_missing_evidence": [],
        "error": None,
    }

    if not pdf_path.exists():
        out["error"] = "file_missing"
        return out

    try:
        size = pdf_path.stat().st_size
        out["size_bytes"] = size
    except Exception as exc:
        out["error"] = f"stat_failed: {exc}"
        return out

    if size < MIN_PDF_SIZE:
        out["error"] = f"file_too_small: {size}"
        return out

    try:
        magic = pdf_path.read_bytes()[:5]
    except Exception as exc:
        out["error"] = f"read_failed: {exc}"
        return out

    if magic != b"%PDF-":
        out["error"] = f"bad_pdf_magic: {magic!r}"
        return out

    out["pdf_magic_valid"] = True

    text_ok, text, text_err = run_pdftotext(pdf_path)
    if not text_ok:
        out["error"] = f"pdftotext_failed: {text_err}"
        return out

    out["pdftotext_succeeded"] = True
    text_n = norm(text)

    variants = []
    for mpn in mpns:
        variants.extend(mpn_variants(mpn))

    for candidate in variants:
        candidate_n = norm(candidate)

        # Do not allow weak value-only fragments such as 0R, 10, 120R, or 4K7
        # to prove an exact MPN match. Those are common text fragments in many
        # unrelated passive datasheets. Family/value matching is handled below
        # by the smart matcher, which also checks series/package/category.
        if not candidate_n:
            continue
        if len(candidate_n) < 5:
            continue
        if re.fullmatch(r"\d+r\d*|\d+k\d*|\d+m\d*|\d+", candidate_n, flags=re.I):
            continue

        if candidate_n in text_n:
            out["mpn_text_verified"] = True
            out["matched_mpn"] = candidate
            out["error"] = None
            return out

    smart_match = score_best_pdf_match(
        mpns=mpns,
        description=description,
        manufacturer=manufacturer,
        pdf_text=text,
        url=source_url or str(pdf_path),
    )
    out["smart_match"] = smart_match
    out["match_type"] = smart_match.get("match_type")
    out["match_score"] = smart_match.get("score")
    out["match_evidence"] = smart_match.get("evidence", [])
    out["match_missing_evidence"] = smart_match.get("missing_evidence", [])

    if smart_match.get("decision") == "accept":
        out["mpn_text_verified"] = True
        out["matched_mpn"] = smart_match.get("matched")
        out["error"] = None
        return out

    out["error"] = "mpn_not_found_in_pdf_text"
    return out



def find_existing_export_datasheet(row: dict[str, Any]) -> dict[str, Any] | None:
    """Reuse previously downloaded/exported PDFs when they validate for this row.

    This is useful for family datasheets shared across multiple BOM rows.
    It does not trust filename alone; it reruns PDF validation against this row's MPNs.
    """
    if not EXPORT_DATASHEETS.exists():
        return None

    pairs = row.get("manufacturer_part_pairs") or []
    mpns = row.get("mpn_candidates") or [p.get("mpn") for p in pairs if p.get("mpn")]
    if not mpns:
        return None

    for pdf in sorted(EXPORT_DATASHEETS.glob("*.pdf")):
        result = validate_pdf_for_mpn(
            pdf,
            mpns,
            row.get("description", ""),
            row.get("selected_manufacturer", ""),
            str(pdf),
        )
        if result.get("mpn_text_verified"):
            # Exact text matches are safe to reuse across filenames.
            # Smart-family matches are broader, so require the exported PDF filename
            # to be manufacturer-compatible. This prevents false positives like
            # reusing a TDK capacitor PDF for an Amphenol connector row.
            smart = result.get("smart_match")
            if smart is not None:
                pdf_name_n = norm(pdf.name)
                candidate_mfgs = row.get("manufacturer_candidates") or []
                selected_mfg = row.get("selected_manufacturer")
                if selected_mfg:
                    candidate_mfgs.append(selected_mfg)

                mfg_ok = False
                for mfg in candidate_mfgs:
                    mfg_n = norm(mfg)
                    if mfg_n and mfg_n in pdf_name_n:
                        mfg_ok = True
                        break

                if not mfg_ok:
                    continue

            return {
                "status": "found",
                "local_saved_path": str(pdf),
                "selected_url": str(pdf),
                "pdf_validation": result,
                "mpn_text_verified": True,
                "approved_equivalent_or_family_match": result.get("matched_mpn"),
                "status_reason": f"reused verified exported datasheet matched {result.get('matched_mpn')}",
            }

    return None


def download_and_verify(url: str, mpns: list[str], description: str = "", manufacturer: str = "") -> tuple[Path | None, dict[str, Any]]:
    data, content_type, err = request_bytes(url, timeout=FETCH_TIMEOUT)
    meta = {
        "url": url,
        "content_type": content_type,
        "download_error": err,
    }

    if err or data is None:
        meta["verified"] = False
        meta["reason"] = f"download_failed: {err}"
        return None, meta

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
        tmp.close()
    except Exception as exc:
        try:
            tmp_path.unlink()
        except Exception:
            pass
        meta["verified"] = False
        meta["reason"] = f"temp_write_failed: {exc}"
        return None, meta

    validation = validate_pdf_for_mpn(tmp_path, mpns, description, manufacturer, url)
    meta.update(validation)
    meta["verified"] = validation["mpn_text_verified"]
    meta["reason"] = validation["error"]

    if not validation["mpn_text_verified"]:
        try:
            tmp_path.unlink()
        except Exception:
            pass
        return None, meta

    return tmp_path, meta


def find_existing_root_datasheet(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row["raw"]
    pairs = mpn_pairs(raw)
    if not pairs or not ROOT_DATASHEETS.exists():
        return None

    mpns = [p["mpn"] for p in pairs]
    for pdf in sorted(ROOT_DATASHEETS.glob("*.pdf")):
        result = validate_pdf_for_mpn(pdf, mpns, row.get("description", ""), row.get("selected_manufacturer", ""), str(pdf))
        if result["mpn_text_verified"]:
            return {
                "status": "local",
                "local_saved_path": str(pdf),
                "pdf_validation": result,
                "matched_mpn": result["matched_mpn"],
            }
    return None


def make_manifest_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = row["raw"]
    pairs = mpn_pairs(raw)
    return {
        "bom_row_index": row["bom_row_index"],
        "raw_bom_fields": raw,
        "reference_designators": raw.get("REF DES", ""),
        "manufacturer_candidates": [p["manufacturer"] for p in pairs],
        "mpn_candidates": [p["mpn"] for p in pairs],
        "selected_manufacturer": pairs[0]["manufacturer"] if pairs else None,
        "selected_mpn": pairs[0]["mpn"] if pairs else None,
        "description": raw.get("DESCRIPTION", ""),
        "quantity": raw.get("QTY", ""),
        "datasheet_applicable": bool(pairs),
        "search_attempted": False,
        "search_queries": [],
        "candidate_urls": [],
        "resolved_urls": [],
        "distributor_api_results": [],
        "failed_candidate_urls": [],
        "selected_url": None,
        "local_saved_path": None,
        "local_file_exists": False,
        "pdf_magic_valid": False,
        "pdftotext_succeeded": False,
        "mpn_text_verified": False,
        "approved_equivalent_or_family_match": None,
        "status": None,
        "status_reason": None,
    }


def secondary_resolution_queries(manufacturer: str, mpn: str) -> list[str]:
    """Stronger SearXNG queries used after initial direct PDF guesses fail."""
    variants = []
    variants.extend(mpn_variants(mpn))
    variants.extend(family_variants(mpn))

    domains = manufacturer_domains(manufacturer)
    queries = []

    for v in variants:
        if not v:
            continue

        queries.extend([
            f'"{v}" "datasheet" "pdf"',
            f'"{v}" "data sheet" "pdf"',
            f'"{v}" "product specification" "pdf"',
            f'"{v}" "symlink" "pdf"',
        ])

        for domain in domains:
            queries.extend([
                f'"{v}" datasheet site:{domain}',
                f'"{v}" "pdf" site:{domain}',
                f'"{v}" "data-sheet" site:{domain}',
                f'"{v}" "lit/ds" site:{domain}',
                f'"{v}" "symlink" site:{domain}',
            ])

    deduped = []
    seen = set()
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)

    return deduped[:20]


def expand_candidates_with_secondary_search(row: dict[str, Any], out: dict[str, Any]) -> None:
    """Use SearXNG to find stronger direct/family PDF URLs after initial discovery."""
    pairs = mpn_pairs(row["raw"])

    for pair in pairs:
        for query in secondary_resolution_queries(pair["manufacturer"], pair["mpn"]):
            if query not in out["search_queries"]:
                out["search_queries"].append(query)

            urls = searxng_search(query, limit=10)
            for url in urls:
                if url not in out["candidate_urls"]:
                    out["candidate_urls"].append(url)

            # Keep this bounded. We want better URLs, not an endless web crawl.
            if len(out["candidate_urls"]) >= 60:
                return


def digikey_get_token() -> tuple[str | None, str | None]:
    client_id = os.environ.get("DIGIKEY_CLIENT_ID")
    client_secret = os.environ.get("DIGIKEY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None, "missing DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET"

    token_url = "https://api.digikey.com/v1/oauth2/token"
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        return None, f"digikey_token_failed: {exc}"

    token = data.get("access_token")
    if not token:
        return None, f"digikey_token_missing: {data}"
    return token, None


def extract_possible_datasheet_urls(obj: Any) -> list[str]:
    """Recursively extract likely datasheet/document URLs from provider JSON."""
    urls = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                lk = str(k).lower()
                if isinstance(v, str):
                    lv = v.lower()
                    if v.startswith(("http://", "https://")) and (
                        "datasheet" in lk
                        or "data_sheet" in lk
                        or "document" in lk
                        or "pdf" in lk
                        or ".pdf" in lv
                        or "datasheet" in lv
                    ):
                        urls.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for item in x:
                walk(item)

    walk(obj)

    deduped = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def digikey_search_candidates(manufacturer: str, mpn: str) -> dict[str, Any]:
    """Use DigiKey Product Information API as a URL discovery provider."""
    token, err = digikey_get_token()
    if err:
        return {
            "provider": "digikey",
            "ok": False,
            "error": err,
            "candidate_urls": [],
        }

    client_id = os.environ.get("DIGIKEY_CLIENT_ID", "")
    site = os.environ.get("DIGIKEY_SITE", "US")
    locale = os.environ.get("DIGIKEY_LOCALE", "en")
    currency = os.environ.get("DIGIKEY_CURRENCY", "USD")

    # ProductInformation v4 keyword search is the least brittle first pass.
    url = "https://api.digikey.com/products/v4/search/keyword"
    body = json.dumps({
        "Keywords": mpn,
        "Limit": 10,
        "Offset": 0,
        "FilterOptionsRequest": {},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": client_id,
            "X-DIGIKEY-Locale-Site": site,
            "X-DIGIKEY-Locale-Language": locale,
            "X-DIGIKEY-Locale-Currency": currency,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        return {
            "provider": "digikey",
            "ok": False,
            "error": f"digikey_search_failed: {exc}",
            "candidate_urls": [],
        }

    urls = extract_possible_datasheet_urls(data)

    return {
        "provider": "digikey",
        "ok": True,
        "error": None,
        "candidate_urls": urls,
        "raw_result_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
    }


def distributor_api_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect candidate datasheet URLs from configured distributor APIs."""
    results = []
    for pair in mpn_pairs(row["raw"]):
        manufacturer = pair["manufacturer"]
        mpn = pair["mpn"]

        result = digikey_search_candidates(manufacturer, mpn)
        result["manufacturer"] = manufacturer
        result["mpn"] = mpn
        results.append(result)

    return results


def discover_for_row(row: dict[str, Any]) -> dict[str, Any]:
    out = make_manifest_row(row)
    pairs = mpn_pairs(row["raw"])

    if not pairs:
        out["status"] = "not_applicable_generic"
        out["status_reason"] = "no concrete manufacturer part number in BOM row"
        return out

    # Direct guesses first. These bypass distributor pages without bypassing blockers.
    for pair in pairs:
        for u in direct_url_guesses(pair["manufacturer"], pair["mpn"]):
            if u not in out["candidate_urls"]:
                out["candidate_urls"].append(u)

    for pair in pairs:
        for q in build_queries(pair["manufacturer"], pair["mpn"]):
            if len(out["search_queries"]) >= MAX_QUERIES_PER_ROW:
                break
            out["search_attempted"] = True
            out["search_queries"].append(q)
            for u in searxng_search(q):
                if u not in out["candidate_urls"]:
                    out["candidate_urls"].append(u)

    # Distributor APIs are secondary structured discovery sources.
    # They may provide datasheet/document URLs but are never proof by themselves.
    api_results = distributor_api_candidates(row)
    out["distributor_api_results"] = api_results

    for api_result in api_results:
        for u in api_result.get("candidate_urls", []):
            if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in out["candidate_urls"]:
                out["candidate_urls"].append(u)

    out["status"] = "ambiguous" if out["candidate_urls"] else "missing"
    out["status_reason"] = "discovery complete"
    return out


def candidate_rank(url: str) -> tuple[int, str]:
    """Lower rank is better."""
    d = domain_of(url)
    u = url.lower()

    manufacturer_domains_flat = {
        "ti.com",
        "nxp.com",
        "nexperia.com",
        "diodes.com",
        "onsemi.com",
        "infineon.com",
        "microchip.com",
        "analog.com",
        "st.com",
        "murata.com",
        "tdk.com",
        "kemet.com",
        "kyocera-avx.com",
        "samsungsem.com",
        "te.com",
        "molex.com",
        "samtec.com",
        "jst.com",
        "amphenol-cs.com",
        "amphenol.com",
        "harwin.com",
        "keyelco.com",
        "vishay.com",
        "yageo.com",
        "panasonic.com",
        "littelfuse.com",
    }

    is_mfg = any(d.endswith(x) or x in d for x in manufacturer_domains_flat)
    is_pdfish = is_probable_pdf_url(url)

    if is_mfg and is_pdfish:
        return (0, url)
    if is_mfg:
        return (1, url)
    if is_distributor_url(url) and is_pdfish:
        return (2, url)
    if is_distributor_url(url):
        return (3, url)
    if is_mirror_url(url) and is_pdfish:
        return (4, url)
    if is_pdfish:
        return (5, url)
    return (6, url)


def sort_candidate_urls(urls: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return sorted(deduped, key=candidate_rank)


def retrieve_for_row(row: dict[str, Any]) -> dict[str, Any]:
    out = make_manifest_row(row)
    pairs = mpn_pairs(row["raw"])

    if not pairs:
        out["status"] = "not_applicable_generic"
        out["status_reason"] = "no concrete manufacturer part number in BOM row"
        return out

    existing = find_existing_root_datasheet(row)
    if existing:
        v = existing["pdf_validation"]
        out["status"] = "local"
        out["status_reason"] = f"verified existing root datasheet matched {v['matched_mpn']}"
        out["local_saved_path"] = existing["local_saved_path"]
        out["local_file_exists"] = True
        out["pdf_magic_valid"] = True
        out["pdftotext_succeeded"] = True
        out["mpn_text_verified"] = True
        out["approved_equivalent_or_family_match"] = v["matched_mpn"]
        return out

    exported = find_existing_export_datasheet(out)
    if exported:
        out.update(exported)
        out["local_file_exists"] = True
        out["pdf_magic_valid"] = True
        out["pdftotext_succeeded"] = True
        out["mpn_text_verified"] = True
        return out

    discovered = discover_for_row(row)
    out.update({
        "search_attempted": discovered["search_attempted"],
        "search_queries": discovered["search_queries"],
        "candidate_urls": discovered["candidate_urls"],
    })

    # Stronger URL discovery pass:
    # If initial candidate list is mostly distributor/404/product pages, ask SearXNG
    # for family/manufacturer PDF URLs before download verification.
    expand_candidates_with_secondary_search(row, out)

    all_mpns = [p["mpn"] for p in pairs]
    attempts = 0

    out["candidate_urls"] = sort_candidate_urls(out["candidate_urls"])

    for candidate in out["candidate_urls"]:
        for resolved in resolve_candidate_urls(candidate):
            out["resolved_urls"].append(resolved)

            resolved_url = resolved.get("url")
            direct_pdf = resolved.get("resolution") == "fetched_direct_pdf"

            if not resolved_url or (not direct_pdf and not is_probable_pdf_url(resolved_url)):
                if resolved.get("resolution") in {"fetch_failed", "html_no_pdf_link_extracted", "non_pdf_non_html"}:
                    out["failed_candidate_urls"].append({
                        "url": resolved_url or candidate,
                        "source_url": candidate,
                        "reason": resolved.get("resolution"),
                        "detail": resolved.get("error"),
                        "domain": resolved.get("domain"),
                    })
                continue

            if attempts >= MAX_DOWNLOAD_ATTEMPTS_PER_ROW:
                break

            attempts += 1

            tmp_path = None
            meta = None
            selected_pair = None
            failed_pair_meta = []

            # Validate each resolved PDF against each approved manufacturer/MPN pair.
            # This prevents alternate-manufacturer PDFs, e.g. Molex, from being
            # rejected merely because selected_manufacturer is the first BOM option.
            for pair in pairs:
                pair_tmp_path, pair_meta = download_and_verify(
                    resolved_url,
                    [pair["mpn"]],
                    out.get("description", ""),
                    pair["manufacturer"],
                )

                if pair_tmp_path is not None:
                    tmp_path = pair_tmp_path
                    meta = pair_meta
                    selected_pair = pair
                    break

                failed_pair_meta.append({
                    "manufacturer": pair["manufacturer"],
                    "mpn": pair["mpn"],
                    "meta": pair_meta,
                })

            if tmp_path is None:
                first_meta = failed_pair_meta[0]["meta"] if failed_pair_meta else {}
                failed = {
                    "url": resolved_url,
                    "source_url": candidate,
                    "reason": first_meta.get("reason"),
                    "domain": domain_of(resolved_url),
                    "pair_failures": failed_pair_meta,
                }
                for key in [
                    "smart_match",
                    "match_type",
                    "match_score",
                    "match_evidence",
                    "match_missing_evidence",
                    "content_type",
                    "download_error",
                ]:
                    if key in first_meta:
                        failed[key] = first_meta.get(key)
                out["failed_candidate_urls"].append(failed)
                continue
            final_name = (
                f"{row['bom_row_index']:03d}_"
                f"{safe_filename(selected_pair['manufacturer'])}_"
                f"{safe_filename(selected_pair['mpn'])}.pdf"
            )
            EXPORT_DATASHEETS.mkdir(parents=True, exist_ok=True)
            final_path = EXPORT_DATASHEETS / final_name
            shutil.move(str(tmp_path), str(final_path))

            out["status"] = "found"
            out["status_reason"] = f"downloaded and verified datasheet matched {meta['matched_mpn']}"
            out["selected_url"] = resolved_url
            out["local_saved_path"] = str(final_path)
            out["local_file_exists"] = True
            out["pdf_magic_valid"] = True
            out["pdftotext_succeeded"] = True
            out["mpn_text_verified"] = True
            out["approved_equivalent_or_family_match"] = meta["matched_mpn"]
            return out

        if attempts >= MAX_DOWNLOAD_ATTEMPTS_PER_ROW:
            break

    if out["candidate_urls"]:
        out["status"] = "ambiguous"
        out["status_reason"] = "candidate URLs found but no verified matching PDF downloaded"
    else:
        out["status"] = "missing"
        out["status_reason"] = "no candidate URLs found"

    return out


def write_manifest(rows: list[dict[str, Any]]) -> None:
    EXPORT_DATASHEETS.mkdir(parents=True, exist_ok=True)
    with MANIFEST_JSONL.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_manifest() -> list[dict[str, Any]]:
    if not MANIFEST_JSONL.exists():
        return []
    return [
        json.loads(x)
        for x in MANIFEST_JSONL.read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]



def safe_retrieve_for_row(row: dict[str, Any]) -> dict[str, Any]:
    """Retrieve one row without allowing a row-level exception to abort Phase 6."""
    try:
        return retrieve_for_row(row)
    except Exception as e:
        out = {
            "bom_row_index": row.get("bom_row_index"),
            "raw_bom_fields": row.get("raw_bom_fields", row),
            "reference_designators": row.get("reference_designators", []),
            "description": row.get("description"),
            "manufacturer_part_pairs": row.get("manufacturer_part_pairs", []),
            "mpn_candidates": row.get("mpn_candidates", []),
            "status": "error",
            "status_reason": f"row processing exception: {type(e).__name__}: {e}",
            "selected_url": None,
            "local_saved_path": None,
            "mpn_text_verified": False,
            "candidate_urls": [],
            "resolved_urls": [],
            "failed_candidate_urls": [],
            "exception_type": type(e).__name__,
            "exception_message": str(e),
        }
        return out


def validate_manifest(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    bom = bom_rows()
    if rows is None:
        rows = read_manifest()

    status_counts: dict[str, int] = {}
    for r in rows:
        status_counts[str(r.get("status"))] = status_counts.get(str(r.get("status")), 0) + 1

    row_indexes = []
    duplicate_indexes = []
    seen = set()
    for r in rows:
        idx = int(r.get("bom_row_index"))
        row_indexes.append(idx)
        if idx in seen:
            duplicate_indexes.append(idx)
        seen.add(idx)

    expected = set(range(1, len(bom) + 1))
    covered = set(row_indexes)
    by_idx = {int(r["bom_row_index"]): r for r in rows if "bom_row_index" in r}

    invalid_statuses = []
    concrete_mpn_rows_not_found_or_local = []
    concrete_mpn_rows_missing_verified_pdf = []
    concrete_mpn_rows_not_searched = []
    concrete_mpn_rows_marked_not_applicable = []

    for source in bom:
        idx = source["bom_row_index"]
        raw = source["raw"]
        pairs = mpn_pairs(raw)
        row = by_idx.get(idx)

        if row is None:
            continue

        status = row.get("status")
        if status not in ALLOWED_STATUSES:
            invalid_statuses.append({"bom_row_index": idx, "status": status})

        if not pairs:
            continue

        if status == "not_applicable_generic":
            concrete_mpn_rows_marked_not_applicable.append(idx)

        if status not in {"found", "local"}:
            concrete_mpn_rows_not_found_or_local.append({
                "bom_row_index": idx,
                "status": status,
                "description": raw.get("DESCRIPTION"),
                "mpns": [p["mpn"] for p in pairs],
            })

        if status != "local" and row.get("search_attempted") is not True:
            concrete_mpn_rows_not_searched.append(idx)

        if status in {"found", "local"}:
            path = Path(str(row.get("local_saved_path") or ""))
            result = validate_pdf_for_mpn(path, [p["mpn"] for p in pairs], row.get("description", ""), row.get("selected_manufacturer", ""), str(path))
            if not result["mpn_text_verified"]:
                concrete_mpn_rows_missing_verified_pdf.append({
                    "bom_row_index": idx,
                    "path": str(path),
                    "reason": result["error"],
                })

    validation = {
        "bom_csv_path": str(INPUT_BOM),
        "bom_raw_row_count": len(bom),
        "manifest_path": str(MANIFEST_JSONL),
        "manifest_row_count": len(rows),
        "covered_bom_row_indexes": sorted(covered),
        "uncovered_bom_row_indexes": sorted(expected - covered),
        "duplicate_bom_row_indexes": sorted(set(duplicate_indexes)),
        "status_counts": status_counts,
        "invalid_statuses": invalid_statuses,
        "concrete_mpn_rows_not_found_or_local": concrete_mpn_rows_not_found_or_local,
        "concrete_mpn_rows_not_searched": concrete_mpn_rows_not_searched,
        "concrete_mpn_rows_marked_not_applicable": concrete_mpn_rows_marked_not_applicable,
        "concrete_mpn_rows_missing_verified_pdf": concrete_mpn_rows_missing_verified_pdf,
        "coverage_pass": covered == expected and not duplicate_indexes and len(rows) == len(bom),
        "local_file_validation_pass": not concrete_mpn_rows_missing_verified_pdf,
        "overall_pass": False,
        "datasheet_storage_dir": str(EXPORT_DATASHEETS),
        "root_datasheet_dir": str(ROOT_DATASHEETS),
        "downloaded_file_count": len(list(EXPORT_DATASHEETS.glob("*.pdf"))),
        "root_datasheet_file_count": len(list(ROOT_DATASHEETS.glob("*.pdf"))) if ROOT_DATASHEETS.exists() else 0,
        "manual_downloads_path": str(MANUAL_DOWNLOADS_JSON),
    }

    validation["overall_pass"] = (
        validation["coverage_pass"]
        and not validation["invalid_statuses"]
        and not validation["concrete_mpn_rows_not_found_or_local"]
        and not validation["concrete_mpn_rows_not_searched"]
        and not validation["concrete_mpn_rows_marked_not_applicable"]
        and validation["local_file_validation_pass"]
    )

    VALIDATION_JSON.write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8")
    return validation


def write_manual_downloads(rows: list[dict[str, Any]]) -> None:
    MANUAL_DOWNLOADS_JSON.parent.mkdir(parents=True, exist_ok=True)
    unresolved = []

    for row in rows:
        if row.get("status") in {"found", "local", "not_applicable_generic"}:
            continue

        raw = row.get("raw_bom_fields") or {}
        unresolved.append({
            "bom_row_index": row.get("bom_row_index"),
            "description": row.get("description"),
            "manufacturer_candidates": row.get("manufacturer_candidates"),
            "mpn_candidates": row.get("mpn_candidates"),
            "status": row.get("status"),
            "status_reason": row.get("status_reason"),
            "candidate_urls": row.get("candidate_urls", [])[:20],
            "resolved_urls": row.get("resolved_urls", [])[:20],
            "failed_candidate_urls": row.get("failed_candidate_urls", [])[:20],
            "manual_instruction": "Download the matching datasheet PDF manually into root datasheets/, then rerun Phase 6.",
        })

    MANUAL_DOWNLOADS_JSON.write_text(
        json.dumps({"unresolved_count": len(unresolved), "rows": unresolved}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def replace_phase6_checkpoint(validation: dict[str, Any], started_at: str) -> None:
    CHECKPOINTS_JSONL.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if CHECKPOINTS_JSONL.exists():
        for line in CHECKPOINTS_JSONL.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("phase_number") != 6:
                existing.append(row)

    checkpoint = {
        "phase_number": 6,
        "phase_name": "Full BOM Datasheet Retrieval",
        "started_at_utc": started_at,
        "completed_at_utc": now_utc(),
        "required_artifacts": [str(MANIFEST_JSONL), str(VALIDATION_JSON), str(MANUAL_DOWNLOADS_JSON)],
        "artifacts_verified": MANIFEST_JSONL.exists() and VALIDATION_JSON.exists(),
        "validation_artifacts": [str(VALIDATION_JSON)],
        "validation_passed": validation["overall_pass"],
        "blockers": [] if validation["overall_pass"] else [
            "one or more concrete MPN rows lack verified datasheets",
            f"manual download list: {MANUAL_DOWNLOADS_JSON}",
        ],
        "phase_passed": validation["overall_pass"],
        "failed_phase_number": None if validation["overall_pass"] else 6,
        "repair_required": not validation["overall_pass"],
    }

    existing.append(checkpoint)
    CHECKPOINTS_JSONL.write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in existing),
        encoding="utf-8",
    )


def cmd_bom_parse(_: argparse.Namespace) -> int:
    rows = bom_rows()
    out = []
    for row in rows:
        raw = row["raw"]
        pairs = mpn_pairs(raw)
        out.append({
            "bom_row_index": row["bom_row_index"],
            "description": raw.get("DESCRIPTION"),
            "refdes": raw.get("REF DES"),
            "manufacturer_candidates": [p["manufacturer"] for p in pairs],
            "mpn_candidates": [p["mpn"] for p in pairs],
            "has_concrete_mpn": bool(pairs),
        })
    print(json.dumps({"ok": True, "row_count": len(rows), "rows": out}, indent=2, ensure_ascii=False))
    return 0


def cmd_check_existing(_: argparse.Namespace) -> int:
    rows = bom_rows()
    results = []
    for row in rows:
        existing = find_existing_root_datasheet(row)
        results.append({
            "bom_row_index": row["bom_row_index"],
            "mpn_candidates": [p["mpn"] for p in mpn_pairs(row["raw"])],
            "local_match": existing,
        })
    print(json.dumps({"ok": True, "results": results}, indent=2, ensure_ascii=False))
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    row = next((r for r in bom_rows() if r["bom_row_index"] == args.bom_row_index), None)
    if not row:
        print(json.dumps({"ok": False, "error": "bom_row_not_found"}))
        return 2
    result = discover_for_row(row)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_search_download(args: argparse.Namespace) -> int:
    row = next((r for r in bom_rows() if r["bom_row_index"] == args.bom_row_index), None)
    if not row:
        print(json.dumps({"ok": False, "error": "bom_row_not_found"}))
        return 2
    result = safe_retrieve_for_row(row)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"found", "local"} else 1


def cmd_validate_manifest(_: argparse.Namespace) -> int:
    validation = validate_manifest()
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if validation["overall_pass"] else 1


def cmd_run_phase6(_: argparse.Namespace) -> int:
    started = now_utc()
    EXPORT_DATASHEETS.mkdir(parents=True, exist_ok=True)

    existing = read_manifest()
    covered_indices = {r["bom_row_index"] for r in existing if "bom_row_index" in r}
    results = list(existing)  # start with existing entries
    print(f"Resuming: {len(covered_indices)} rows already processed, skipping", flush=True)

    for row in bom_rows():
        idx = row["bom_row_index"]
        if idx in covered_indices:
            continue
        print(f"Phase 6 row {idx}: {row['raw'].get('DESCRIPTION', '')}", flush=True)
        result = safe_retrieve_for_row(row)
        print(f"  -> {result['status']}: {result['status_reason']}", flush=True)
        results.append(result)
        write_manifest(results)
        write_manual_downloads(results)

    validation = validate_manifest(results)
    write_manual_downloads(results)
    replace_phase6_checkpoint(validation, started)

    print(json.dumps(validation, indent=2, ensure_ascii=False))
    return 0 if validation["overall_pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ThomsonLint datasheet helper for Phase 6")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("bom-parse")
    p.set_defaults(func=cmd_bom_parse)

    p = sub.add_parser("check-existing")
    p.set_defaults(func=cmd_check_existing)

    p = sub.add_parser("discover")
    p.add_argument("--bom-row-index", required=True, type=int)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("search-download")
    p.add_argument("--bom-row-index", required=True, type=int)
    p.set_defaults(func=cmd_search_download)

    p = sub.add_parser("validate-manifest")
    p.set_defaults(func=cmd_validate_manifest)

    p = sub.add_parser("run-phase6")
    p.set_defaults(func=cmd_run_phase6)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
