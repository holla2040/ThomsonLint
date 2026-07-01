#!/usr/bin/env python3
"""Regression tests for tools/kicad-export.py net resolution (KiCad 9 & 10).

Standalone, standard-library only -- run directly:

    python tests/test_kicad_export.py

Uses tiny inline synthetic .kicad_pcb fixtures so no real (proprietary)
project files need to live in the repo.  Guards the two net-reference
formats the exporter must handle:

  * KiCad 9  (.kicad_pcb version 20241229): a top-level net table declares
    (net <ordinal> "name"); pads carry (net <ordinal> "name") and
    tracks/vias/zones carry the ordinal alone as (net <ordinal>).

  * KiCad 10 (.kicad_pcb version 20260206): no net table, no ordinals --
    pads/tracks/vias/zones all carry the name inline as (net "name").

The KiCad 9 case is the one the initial KiCad 10 support (commit 0bc6aaf)
silently regressed: the integer ordinal in (net 2) was mis-read as a net
*name* "2", so every track/via resolved to net_id 0 and all per-net trace
statistics collapsed to zero.  These tests fail loudly if that returns.
"""

import importlib.util
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPORT_PY = os.path.join(_HERE, os.pardir, "tools", "kicad-export.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("kicad_export", _EXPORT_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kx = _load_module()


# A resistor across VCC (net 2) and GND (net 1), one VCC track segment + via,
# and a GND zone -- enough to exercise pad / segment / via / zone net refs.
KICAD9_PCB = """\
(kicad_pcb
  (version 20241229) (generator "pcbnew") (generator_version "9.0")
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (footprint "R_0603"
    (layer "F.Cu") (at 10 10 0)
    (property "Reference" "R1") (property "Value" "10k")
    (pad "1" smd roundrect (at -0.8 0) (net 2 "VCC"))
    (pad "2" smd roundrect (at 0.8 0) (net 1 "GND"))
  )
  (segment (start 10 10) (end 20 10) (width 0.25) (layer "F.Cu") (net 2))
  (segment (start 20 10) (end 30 10) (width 0.25) (layer "F.Cu") (net 2))
  (via (at 20 10) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 2))
  (zone (net 1) (net_name "GND") (layer "B.Cu"))
)
"""

# Same board saved by KiCad 10: no net table, ordinals gone, names inline.
KICAD10_PCB = """\
(kicad_pcb
  (version 20260206) (generator "pcbnew") (generator_version "10.0")
  (footprint "R_0603"
    (layer "F.Cu") (at 10 10 0)
    (property "Reference" "R1") (property "Value" "10k")
    (pad "1" smd roundrect (at -0.8 0) (net "VCC"))
    (pad "2" smd roundrect (at 0.8 0) (net "GND"))
  )
  (segment (start 10 10) (end 20 10) (width 0.25) (layer "F.Cu") (net "VCC"))
  (segment (start 20 10) (end 30 10) (width 0.25) (layer "F.Cu") (net "VCC"))
  (via (at 20 10) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "VCC"))
  (zone (net "GND") (net_name "GND") (layer "B.Cu"))
)
"""


def _parse(text):
    fd, path = tempfile.mkstemp(suffix=".kicad_pcb")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return kx.parse_board(path)
    finally:
        os.remove(path)


_failures = []


def check(cond, msg):
    print(("  PASS: " if cond else "  FAIL: ") + msg)
    if not cond:
        _failures.append(msg)


def test_kicad9():
    print("KiCad 9 (top-level net table + integer ordinals):")
    bd = _parse(KICAD9_PCB)

    pad_nets = {p["name"]: (p["net_id"], p["net_name"])
                for f in bd["footprints"] for p in f["pads"]}
    check(pad_nets["1"] == (2, "VCC"), f"pad 1 -> VCC(2), got {pad_nets['1']}")
    check(pad_nets["2"] == (1, "GND"), f"pad 2 -> GND(1), got {pad_nets['2']}")

    seg_ids = [s["net_id"] for s in bd["segments"]]
    check(seg_ids == [2, 2], f"segment ordinals resolve to [2, 2], got {seg_ids}")

    via_ids = [v["net_id"] for v in bd["vias"]]
    check(via_ids == [2], f"via ordinal resolves to [2], got {via_ids}")

    # The regression guard: per-net trace stats must be non-zero for VCC.
    sig = {s["name"]: s for s in kx.compute_signal_stats(
        bd["segments"], bd["vias"], bd["nets"])}
    check(sig["VCC"]["trace_length_mm"] == 20.0,
          f"VCC trace length 20mm, got {sig['VCC']['trace_length_mm']}")
    check(sig["VCC"]["via_count"] == 1,
          f"VCC via_count 1, got {sig['VCC']['via_count']}")

    zone_nets = [(z["net_id"], z["net_name"]) for z in bd["zones"]]
    check(zone_nets == [(1, "GND")], f"zone -> GND(1), got {zone_nets}")


def test_kicad10():
    print("KiCad 10 (no net table, name-only inline refs):")
    bd = _parse(KICAD10_PCB)

    # Ordinals are synthesized in discovery order; 0 reserved for unconnected.
    check(bd["nets"].get(0) == "", "net_id 0 reserved for unconnected net")
    name_to_id = {v: k for k, v in bd["nets"].items()}
    check("VCC" in name_to_id and "GND" in name_to_id,
          f"VCC and GND present in synthesized net table, got {bd['nets']}")

    pad_nets = {p["name"]: p["net_name"]
                for f in bd["footprints"] for p in f["pads"]}
    check(pad_nets == {"1": "VCC", "2": "GND"},
          f"pads resolve to names, got {pad_nets}")

    # Every pad/segment/via ordinal must be a real (non-zero) synthesized id.
    all_ids = ([p["net_id"] for f in bd["footprints"] for p in f["pads"]]
               + [s["net_id"] for s in bd["segments"]]
               + [v["net_id"] for v in bd["vias"]])
    check(all(i != 0 for i in all_ids),
          f"no name-only ref collapses to net_id 0, got {all_ids}")

    sig = {s["name"]: s for s in kx.compute_signal_stats(
        bd["segments"], bd["vias"], bd["nets"])}
    check(sig["VCC"]["trace_length_mm"] == 20.0,
          f"VCC trace length 20mm, got {sig['VCC']['trace_length_mm']}")
    check(sig["VCC"]["via_count"] == 1,
          f"VCC via_count 1, got {sig['VCC']['via_count']}")


def main():
    test_kicad9()
    test_kicad10()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)} check(s))")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
