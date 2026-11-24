"""DRC type naming: airwires are recognised by description, not by the enum."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import fusion_export as fx  # noqa: E402


def test_live_airwire_row_is_named_airwire():
    # What Fusion actually returns for an unrouted connection.
    row = {"description": "Air Wire", "type": 4, "layer": 19}
    assert fx.drc_type_name(row) == "airwire"


def test_other_rows_use_the_schema_enum():
    assert fx.drc_type_name({"description": "Board Outline Clearance", "type": 2}) == "consistency"
    assert fx.drc_type_name({"description": "Overlap", "type": 1}) == "failure"


def test_unknown_type_passes_through():
    assert fx.drc_type_name({"description": "Something New", "type": 9}) == 9
