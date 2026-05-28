from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


datasheet_helper = load_module(SCRIPTS / "datasheet_helper.py")
phase6_audit = load_module(SCRIPTS / "audit_phase6_datasheets.py")


def test_strip_approved_equivalent_prefix() -> None:
    assert datasheet_helper.strip_approved_equivalent_prefix("resistor:SG73P1EWTTP512J") == "SG73P1EWTTP512J"
    assert datasheet_helper.strip_approved_equivalent_prefix("connector:SFW20S-2STE1LF") == "SFW20S-2STE1LF"
    assert datasheet_helper.strip_approved_equivalent_prefix("SFW20S-2STE1LF") == "SFW20S-2STE1LF"
    assert datasheet_helper.strip_approved_equivalent_prefix("RC0402JR-070RL") == "RC0402JR-070RL"


def test_found_rows_are_not_unresolved_search_blockers() -> None:
    assert phase6_audit.is_unresolved_status_requiring_search("ambiguous") is True
    assert phase6_audit.is_unresolved_status_requiring_search("missing") is True
    assert phase6_audit.is_unresolved_status_requiring_search("error") is True
    assert phase6_audit.is_unresolved_status_requiring_search("found") is False
    assert phase6_audit.is_unresolved_status_requiring_search("local") is False


def test_prefixed_approved_equivalent_matches_pdf_text_after_normalization() -> None:
    row = {"approved_equivalent_or_family_match": "resistor:SG73P1EWTTP512J"}
    ok, match = phase6_audit.pdf_contains_mpn(row, {}, "KOA Speer SG73P1EWTTP512J datasheet")
    assert ok is True
    assert match == "SG73P1EWTTP512J"


def test_alternate_manufacturer_candidate_uses_matching_manufacturer_for_smart_match() -> None:
    row = {
        "selected_manufacturer": "Panasonic",
        "selected_mpn": "ERJ-PA2J512X",
        "selected_url": "https://www.koaspeer.com/pdfs/SG73P.pdf",
        "mpn_candidates": ["ERJ-PA2J512X", "SG73P1EWTTP512J"],
        "manufacturer_candidates": ["Panasonic", "KOA Speer"],
    }
    raw = {
        "DESCRIPTION": "RES_5K1_5%_1/4W_0402_200PPM",
        "MFG_1": "Panasonic",
        "MFG P/N_1": "ERJ-PA2J512X",
        "MFG_2": "KOA Speer",
        "MFG P/N_2": "SG73P1EWTTP512J",
    }
    text = "KOA Speer SG73P thick film chip resistor ordering 0402 512"
    ok, match = phase6_audit.pdf_contains_mpn(row, raw, text)
    assert ok is True
    assert match == "SG73P1EWTTP512J"
