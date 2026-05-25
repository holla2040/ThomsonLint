#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


PACKAGE_SIZES = {
    "0201", "0402", "0603", "0805", "1206", "1210", "1812", "2010", "2512",
}

CONNECTOR_WORDS = {
    "connector", "header", "receptacle", "socket", "zif", "ffc", "fpc",
    "dsub", "d-sub", "terminal", "housing", "plug",
}

ACTIVE_WORDS = {
    "ic", "ics", "mosfet", "fet", "regulator", "ldo", "logic", "buffer",
    "mux", "switch", "transceiver", "repeater", "opamp", "amplifier",
    "microcontroller", "mcu", "fpga", "diode", "led", "sensor",
}

RESISTOR_WORDS = {"res", "resistor", "ohm", "jumper"}
CAPACITOR_WORDS = {"cap", "capacitor", "ceramic", "mlcc", "x7r", "x5r", "np0", "c0g"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def words(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_.+-]+", str(s or "").lower()))


def text_has(text_norm: str, token: str) -> bool:
    nt = norm(token)
    return bool(nt) and nt in text_norm


def resistor_value_variants(raw: str, desc: str = "") -> list[str]:
    candidates: list[str] = []

    for source in [raw, desc]:
        s = str(source or "").upper()

        # 4K70, 4K7, 120R, 10R, 0R00
        for m in re.finditer(r"\b(\d+(?:R|K|M)\d*)\b", s):
            candidates.append(m.group(1))

        # RES_5K1 or 5K1
        for m in re.finditer(r"\b(\d+)K(\d*)\b", s):
            a, b = m.group(1), m.group(2)
            candidates.extend([f"{a}K{b}", f"{a}.{b}K" if b else f"{a}K"])

        # explicit 0 ohm / jumper
        if "0R" in s or "0OHM" in s or "0 OHM" in s or "JUMP" in s:
            candidates.extend(["0R", "0R00", "ZERO OHM", "JUMPER"])

        # 3-digit resistor code in MPN, e.g. 512 -> 5.1k when desc says 5K1
        for m in re.finditer(r"(\d{3})", s):
            code = m.group(1)
            if code.endswith("2"):
                candidates.append(code)

    return dedupe(candidates)


def capacitor_value_variants(raw: str, desc: str = "") -> list[str]:
    candidates: list[str] = []
    s = f"{raw} {desc}".upper()

    # EIA capacitance code, e.g. 104 = 100 nF / 0.1 uF, 106 = 10 uF
    for m in re.finditer(r"\b(\d{3})\b", s):
        code = m.group(1)
        if code == "104":
            candidates.extend(["104", "0.1UF", "100NF", "100N", "0.10UF"])
        elif code == "106":
            candidates.extend(["106", "10UF", "10.0UF"])
        elif code == "105":
            candidates.extend(["105", "1UF", "1.0UF"])

    # Direct values in description.
    for m in re.finditer(r"(\d+(?:\.\d+)?)(UF|NF|PF)", s):
        candidates.append(m.group(0))

    # Dielectric and voltage/tolerance tokens.
    for tok in ["X7R", "X5R", "C0G", "NP0", "50V", "25V", "16V", "10V", "10%", "5%"]:
        if tok in s:
            candidates.append(tok)

    return dedupe(candidates)


def package_variants(raw: str, desc: str = "") -> list[str]:
    candidates: list[str] = []
    s = f"{raw} {desc}".upper()

    for pkg in PACKAGE_SIZES:
        if pkg in s:
            candidates.append(pkg)

    # Murata GRM155 package commonly maps to 0402.
    if "GRM155" in s:
        candidates.extend(["155", "0402"])

    return dedupe(candidates)


def connector_position_variants(raw: str, desc: str = "") -> list[str]:
    candidates: list[str] = []
    s = f"{raw} {desc}".upper()

    # Description forms: 1X3, 2X5, 2X25, DB44.
    for m in re.finditer(r"\b(\d+)X(\d+)\b", s):
        rows = int(m.group(1))
        cols = int(m.group(2))
        candidates.extend([str(cols), str(rows * cols), f"{rows}X{cols}"])

    for m in re.finditer(r"\bDB(\d+)\b", s):
        candidates.append(m.group(1))

    # SFW20S, SFW10R.
    m = re.search(r"SFW(\d+)([SR])", s)
    if m:
        candidates.extend([m.group(1), f"SFW{m.group(1)}", m.group(2)])

    # ESQT-125 means 25 positions in Samtec ordering in many ESQT patterns.
    m = re.search(r"ESQT-(\d{3})", s)
    if m:
        code = m.group(1)
        candidates.append(code)
        if code.startswith("1"):
            candidates.append(str(int(code[1:])))

    return dedupe(candidates)


def orientation_variants(raw: str, desc: str = "") -> list[str]:
    s = f"{raw} {desc}".upper()
    out: list[str] = []

    if " RA" in s or "_RA" in s or "RIGHT" in s or re.search(r"SFW\d+R", s):
        out.extend(["RIGHT ANGLE", "RIGHT-ANGLE", "RIGHTANGLE", "RA"])

    if " VER" in s or "_VER" in s or "VERT" in s or re.search(r"SFW\d+S", s):
        out.extend(["VERTICAL", "STRAIGHT", "THROUGH HOLE", "TH"])

    return dedupe(out)


def series_candidates(mpn: str, desc: str = "") -> list[str]:
    raw = str(mpn or "").strip()
    base = raw.split(",")[0].strip()
    no_hyphen = base.replace("-", "")

    candidates = [base, no_hyphen]

    # Prefix family, e.g. RMCF0603, RMCF, CRCW0402, RC1206, SFW20S, M20, ESQT, SG73P.
    patterns = [
        r"^(RMC[FP]\d{4})",
        r"^(RMC[FP])",
        r"^(CRCW\d{4})",
        r"^(CRCW)",
        r"^(RC\d{4})",
        r"^(SR\d{4})",
        r"^(RCS\d{4})",
        r"^(RCS)",
        r"^(ERJ[-]?[A-Z0-9]+?)\d{3}",
        r"^(SG73P)",
        r"^(WJC\d{4})",
        r"^(WJC)",
        r"^(SFW\d+[SR])",
        r"^(SFW)",
        r"^(M20)",
        r"^(ESQT)",
        r"^(K86X)",
        r"^(043045|43045)",
        r"^(87224)",
    ]

    for pat in patterns:
        m = re.search(pat, base, flags=re.I)
        if m:
            candidates.append(m.group(1))

    # Numeric series inside leading-zero Molex style: 043045-0414 -> 43045.
    m = re.match(r"^0?(\d{5})-\d+", base)
    if m:
        candidates.append(m.group(1))

    # Description-derived family words/codes.
    d = str(desc or "").upper()
    for tok in re.findall(r"\b[A-Z]{2,}\d*[A-Z0-9-]*\b", d):
        if len(tok) >= 3 and tok not in {"CON", "HDR", "RES", "CAP", "TH", "SM", "VER"}:
            candidates.append(tok)

    return dedupe(candidates)


def manufacturer_candidates(manufacturer: str, url: str = "") -> list[str]:
    vals = [manufacturer]
    u = str(url or "").lower()

    domain_map = {
        "harwin": "Harwin",
        "molex": "Molex",
        "te.com": "TE Connectivity",
        "amphenol": "Amphenol",
        "kycon": "Kycon",
        "vishay": "Vishay",
        "seielect": "Stackpole",
        "yageo": "Yageo",
        "panasonic": "Panasonic",
        "koaspeer": "KOA",
        "littelfuse": "Littelfuse",
        "murata": "Murata",
        "tdk": "TDK",
        "samsung": "Samsung",
        "avx": "Kyocera AVX",
    }
    for key, name in domain_map.items():
        if key in u:
            vals.append(name)

    return dedupe(vals)


def infer_part_class(description: str, mpn: str) -> str:
    ws = words(f"{description} {mpn}")

    if ws & ACTIVE_WORDS:
        return "active"
    if ws & CAPACITOR_WORDS:
        return "capacitor"
    if ws & RESISTOR_WORDS:
        return "resistor"
    if ws & CONNECTOR_WORDS:
        return "connector"

    upper = f"{description} {mpn}".upper()
    if re.search(r"^(RMC|CRC|RC|SR|ERJ|SG73|WJC)", str(mpn or "").upper()):
        return "resistor"
    if re.search(r"^(GRM|CL\d|C\d{4}|0402|0603)", str(mpn or "").upper()):
        return "capacitor"
    if re.search(r"^(SFW|M20|ESQT|K86X|\d{5,}-\d+)", str(mpn or "").upper()):
        return "connector"

    return "unknown"


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        item = str(item or "").strip()
        if not item:
            continue
        key = norm(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def evidence_if_present(text_norm: str, label: str, tokens: list[str], points: int) -> tuple[int, list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    missing: list[str] = []

    found_any = False
    for tok in tokens:
        if text_has(text_norm, tok):
            evidence.append({"kind": label, "token": tok, "points": points})
            found_any = True
            break

    if not found_any and tokens:
        missing.append(label)

    return (points if found_any else 0, evidence, missing)


def exact_mpn_variants(mpn: str) -> list[str]:
    raw = str(mpn or "").strip()
    base = raw.split(",")[0].strip()
    no_parens = re.sub(r"\([^)]*\)", "", base).strip()
    variants = [raw, base, no_parens, no_parens.replace("-", ""), no_parens.replace(" ", "")]

    # One-character order suffix removal for passives.
    if re.match(r"^(GRM|CL\d|C\d{4})[A-Z0-9]+$", base, flags=re.I) and len(base) > 8:
        variants.append(base[:-1])

    return dedupe(variants)



def domain_manufacturer_family(url: str) -> str | None:
    u = str(url or "").lower()
    mapping = {
        "nexperia.com": "nexperia",
        "nxp.com": "nxp",
        "ti.com": "ti",
        "onsemi.com": "onsemi",
        "vishay.com": "vishay",
        "molex.com": "molex",
        "harwin.com": "harwin",
        "te.com": "te connectivity",
        "amphenol": "amphenol",
        "kycon.com": "kycon",
        "samtec.com": "samtec",
        "seielect.com": "stackpole",
        "yageogroup.com": "yageo",
        "panasonic.com": "panasonic",
        "koaspeer.com": "koa",
        "littelfuse.com": "littelfuse",
        "murata": "murata",
        "tdk.com": "tdk",
        "samsungsem.com": "samsung",
        "kyocera-avx.com": "kyocera avx",
        "avx.com": "kyocera avx",
    }
    for key, val in mapping.items():
        if key in u:
            return val
    return None


def manufacturer_matches_domain(manufacturer: str, url: str, pdf_text: str = "") -> bool:
    m = norm(manufacturer)
    d = domain_manufacturer_family(url)
    if not m or not d:
        return True

    nd = norm(d)
    textn = norm(pdf_text)

    aliases = {
        "teconnectivity": {"teconnectivity", "amp", "tyco"},
        "kyoceraavx": {"kyoceraavx", "avx"},
        "stackpole": {"stackpole", "sei", "seielectronics"},
        "koa": {"koa", "koaspeer"},
        "yagEO": {"yageo"},
    }

    if m in nd or nd in m:
        return True

    for canonical, vals in aliases.items():
        if m == canonical or m in vals:
            return nd in vals or nd == canonical

    # If the claimed manufacturer appears strongly in the PDF text, allow it.
    # This handles mirrors/CDNs. Do not allow unrelated manufacturer-hosted PDFs.
    if m and m in textn:
        return True

    return False


def pdf_category_conflict(part_class: str, pdf_text: str, url: str = "") -> str | None:
    textn = norm(pdf_text)
    urln = norm(url)

    # Connector rows must not pass semiconductor/capacitor/resistor PDFs.
    if part_class == "connector":
        bad_tokens = [
            "mosfet", "transistor", "diode", "semiconductor", "logicgate",
            "loadswitch", "voltageregulator", "capacitor", "resistor",
            "crystal", "oscillator",
        ]
        good_tokens = [
            "connector", "header", "receptacle", "socket", "contacts",
            "terminal", "housing", "fpc", "ffc", "zif", "dsub", "pitch",
        ]
        if any(t in textn or t in urln for t in bad_tokens) and not any(t in textn for t in good_tokens):
            return "connector_row_pdf_category_conflict"

    # Resistor rows must not pass capacitor/connector/semiconductor PDFs.
    if part_class == "resistor":
        bad_tokens = ["capacitor", "connector", "header", "mosfet", "transistor", "diode"]
        good_tokens = ["resistor", "resistance", "ohm", "jumper", "thickfilm", "thinfilm"]
        if any(t in textn or t in urln for t in bad_tokens) and not any(t in textn for t in good_tokens):
            return "resistor_row_pdf_category_conflict"

    # Capacitor rows must not pass resistor/connector/semiconductor PDFs.
    if part_class == "capacitor":
        bad_tokens = ["resistor", "connector", "header", "mosfet", "transistor", "diode"]
        good_tokens = ["capacitor", "capacitance", "ceramic", "mlcc", "dielectric"]
        if any(t in textn or t in urln for t in bad_tokens) and not any(t in textn for t in good_tokens):
            return "capacitor_row_pdf_category_conflict"

    return None


def score_pdf_match(
    *,
    mpn: str,
    description: str,
    manufacturer: str = "",
    pdf_text: str,
    url: str = "",
) -> dict[str, Any]:
    part_class = infer_part_class(description, mpn)
    text_norm = norm(pdf_text)

    # Hard guardrails before generic family scoring. These prevent numeric-token
    # false positives such as a Molex connector row accepting a Nexperia MOSFET PDF.
    if not manufacturer_matches_domain(manufacturer, url, pdf_text):
        return {
            "decision": "reject",
            "score": 0,
            "match_type": "manufacturer_domain_mismatch",
            "matched": None,
            "part_class": part_class,
            "evidence": [],
            "missing_evidence": ["manufacturer_domain_match"],
            "notes": [f"manufacturer={manufacturer!r} does not match url={url!r}"],
        }

    category_conflict = pdf_category_conflict(part_class, pdf_text, url)
    if category_conflict:
        return {
            "decision": "reject",
            "score": 0,
            "match_type": category_conflict,
            "matched": None,
            "part_class": part_class,
            "evidence": [],
            "missing_evidence": ["compatible_pdf_category"],
            "notes": [category_conflict],
        }

    evidence: list[dict[str, Any]] = []
    missing: list[str] = []
    score = 0
    negative = 0

    # Exact and strong variant match.
    for v in exact_mpn_variants(mpn):
        nv = norm(v)
        if len(nv) >= 5 and nv in text_norm:
            return {
                "decision": "accept",
                "score": 100,
                "match_type": "exact_or_variant_mpn",
                "matched": v,
                "part_class": part_class,
                "evidence": [{"kind": "exact_or_variant_mpn", "token": v, "points": 100}],
                "missing_evidence": [],
                "notes": [],
            }

    series = series_candidates(mpn, description)
    packages = package_variants(mpn, description)
    manufacturers = manufacturer_candidates(manufacturer, url)
    resistor_values = resistor_value_variants(mpn, description)
    capacitor_values = capacitor_value_variants(mpn, description)
    positions = connector_position_variants(mpn, description)
    orientations = orientation_variants(mpn, description)

    notes: list[str] = []

    # Active devices remain strict.
    if part_class == "active":
        return {
            "decision": "reject",
            "score": 0,
            "match_type": "active_requires_exact_mpn",
            "matched": None,
            "part_class": part_class,
            "evidence": evidence,
            "missing_evidence": ["exact_or_variant_mpn"],
            "notes": ["Active/semiconductor class requires exact or strong MPN variant evidence."],
        }

    # Shared evidence.
    pts, ev, miss = evidence_if_present(text_norm, "manufacturer", manufacturers, 20)
    score += pts
    evidence += ev
    missing += miss

    pts, ev, miss = evidence_if_present(text_norm, "series", series, 35)
    score += pts
    evidence += ev
    missing += miss

    if "order" in text_norm or "ordering" in text_norm or "partnumber" in text_norm or "partnumbering" in text_norm:
        score += 10
        evidence.append({"kind": "ordering_language", "token": "ordering/part number language", "points": 10})

    if url:
        for tok in series:
            if text_has(norm(url), tok):
                score += 10
                evidence.append({"kind": "url_series", "token": tok, "points": 10})
                break

    # Class-specific required evidence.
    required_missing: list[str] = []

    if part_class == "resistor":
        pts, ev, miss = evidence_if_present(text_norm, "package_size", packages, 25)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("package_size")

        pts, ev, miss = evidence_if_present(text_norm, "resistance_value", resistor_values, 30)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("resistance_value")

    elif part_class == "capacitor":
        pts, ev, miss = evidence_if_present(text_norm, "package_size", packages, 20)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("package_size")

        pts, ev, miss = evidence_if_present(text_norm, "capacitance_or_dielectric", capacitor_values, 30)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("capacitance_or_dielectric")

    elif part_class == "connector":
        pts, ev, miss = evidence_if_present(text_norm, "positions_or_contact_count", positions, 25)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("positions_or_contact_count")

        pts, ev, miss = evidence_if_present(text_norm, "orientation", orientations, 15)
        score += pts
        evidence += ev

        # If the BOM/MPN implies orientation, require matching orientation evidence.
        # This prevents SFW-R right-angle rows from passing against SFW-S straight PDFs.
        if orientations and miss:
            required_missing.append("orientation")

        if "pitch" in text_norm or "254mm" in text_norm or "100mm" in text_norm or "1mm" in text_norm:
            score += 10
            evidence.append({"kind": "connector_pitch_language", "token": "pitch text", "points": 10})

    else:
        # Unknown class requires stronger generic evidence.
        pts, ev, miss = evidence_if_present(text_norm, "package_or_position_or_value", packages + positions + resistor_values + capacitor_values, 30)
        score += pts
        evidence += ev
        if miss:
            required_missing.append("package_or_position_or_value")

    score = max(0, min(100, score - negative))

    if required_missing:
        decision = "reject" if score < 90 else "needs_review"
    elif score >= 80:
        decision = "accept"
    elif score >= 55:
        decision = "needs_review"
    else:
        decision = "reject"

    match_type = "family_order_code" if decision == "accept" else "weak_family"

    return {
        "decision": decision,
        "score": score,
        "match_type": match_type,
        "matched": f"{part_class}:{mpn}",
        "part_class": part_class,
        "evidence": evidence,
        "missing_evidence": dedupe(missing + required_missing),
        "notes": notes,
        "tokens": {
            "series": series,
            "package_sizes": packages,
            "resistor_values": resistor_values,
            "capacitor_values": capacitor_values,
            "positions": positions,
            "orientations": orientations,
            "manufacturers": manufacturers,
        },
    }


def score_best_pdf_match(
    *,
    mpns: list[str],
    description: str,
    manufacturer: str = "",
    pdf_text: str,
    url: str = "",
) -> dict[str, Any]:
    results = [
        score_pdf_match(
            mpn=mpn,
            description=description,
            manufacturer=manufacturer,
            pdf_text=pdf_text,
            url=url,
        )
        for mpn in mpns
        if str(mpn or "").strip()
    ]

    if not results:
        return {
            "decision": "reject",
            "score": 0,
            "match_type": "no_mpn",
            "matched": None,
            "part_class": "unknown",
            "evidence": [],
            "missing_evidence": ["mpn"],
            "notes": [],
        }

    order = {"accept": 2, "needs_review": 1, "reject": 0}
    return sorted(results, key=lambda r: (order.get(r["decision"], 0), r["score"]), reverse=True)[0]


def pdftotext(pdf_path: Path) -> str:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out.txt"
        subprocess.run(
            ["pdftotext", str(pdf_path), str(out)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return out.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--mpn", action="append", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--manufacturer", default="")
    ap.add_argument("--url", default="")
    args = ap.parse_args()

    text = pdftotext(Path(args.pdf))
    result = score_best_pdf_match(
        mpns=args.mpn,
        description=args.description,
        manufacturer=args.manufacturer,
        pdf_text=text,
        url=args.url or args.pdf,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["decision"] == "accept" else 1


if __name__ == "__main__":
    raise SystemExit(main())
