#!/usr/bin/env python3
"""ThomsonLint direct capture — ULP-free export from a live Fusion session.

Replaces the three JSON export ULPs and the images ULP with direct
``fusion_mcp_electronics_read`` queries plus dispatched EAGLE commands
(``EDIT`` / ``RATSNEST`` / ``DISPLAY`` / ``WINDOW FIT`` / ``EXPORT IMAGE``),
per ``docs/Direct_Read_Feasibility.md``. Emits the exact
``-thomson-export-{sch,brd,stack}.json`` contracts the ULPs write, so nothing
downstream changes. None of the dispatched commands contain ``RUN``, so the
post-``RUN`` dialog latch never arms: the whole capture is zero-Escape.

Verbs (run with the wanted editor's design open; the tool switches tabs):

    python tools/fusion_export.py sch      # -sch.json
    python tools/fusion_export.py brd      # -brd.json + -stack.json
    python tools/fusion_export.py images   # schematic + board PNG passes
    python tools/fusion_export.py all      # everything

Known, deliberate differences from the ULP output (each favors this path;
see the feasibility doc):

- ``board.area`` is the **board outline** bbox (layer-20 wires), not EAGLE's
  drawing extent (``B.area`` includes silk/docu overhang). Edge distances
  are measured against the outline, which is what the rule actually means.
- Copper-layer detection uses the stackup ULP's wider test (1-16, 257-304,
  63/64, name fallback) everywhere, so Fusion inner layers like 303 "POWER"
  are counted and their pours exported (the board ULP missed them).
- ``nets[].class.clearance_mm`` is ``null`` — the MCP surface has no
  NetClass clearance (feasibility doc gap 1).
- ``project.variant`` is ``"''"`` (what Fusion's ``variant()`` returns) when
  the design defines no variants, else ``null`` — the *active* variant is
  not readable over MCP (gap 5).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fusion_bridge import DEFAULT_SHARE_WSL, BridgeError, FusionBridge, wsl_to_windows

VERSION = "1.0"

# ---------------------------------------------------------------------------
# Classification helpers — faithful ports of the ULP logic (bug-compatible
# where the ULP has quirks, e.g. "15V0-SERIES" guessing "5V", refs starting
# 'T' classifying as transformer before the TP test-point check). Parity
# with the committed exports matters more than fixing heuristics here.
# ---------------------------------------------------------------------------

_POWER_TOKENS = (
    "VCC", "VDD", "VBUS", "VIN", "VOUT", "VBAT", "VSYS",
    "+3V", "+5V", "+12V", "+24V", "3V3", "5V0", "1V8", "1V2", "2V5", "PWR",
)
_CLOCK_TOKENS = ("CLK", "XTAL", "SCK", "SCLK", "MCLK", "BCLK", "LRCK", "OSC")
_HS_TOKENS = ("USB", "ETH", "HDMI", "PCIE", "SATA", "MIPI", "LVDS")

PIN_DIRECTION = {0: "NC", 1: "IN", 2: "OUT", 3: "IO", 4: "OC",
                 5: "PWR", 6: "PAS", 7: "HIZ", 8: "SUP"}


def is_power_net(name: str) -> bool:
    upper = name.upper()
    return any(t in upper for t in _POWER_TOKENS)


def is_ground_net(name: str) -> bool:
    upper = name.upper()
    if upper in ("GND", "AGND", "DGND", "PGND", "SGND"):
        return True
    return "VSS" in upper or "GND" in upper


def is_clock_net(name: str) -> bool:
    upper = name.upper()
    return any(t in upper for t in _CLOCK_TOKENS)


def diff_pair_member(name: str) -> int:
    """1 = positive, -1 = negative, 0 = not differential (ULP port)."""
    upper = name.upper()
    if len(upper) >= 2:
        last2 = upper[-2:]
        if last2 == "_P" or last2 == "DP" or last2 == "D+":
            return 1
        if last2 == "_N" or last2 == "DN" or last2 == "D-":
            return -1
    return 0


def diff_partner(name: str) -> str:
    if len(name) < 2:
        return ""
    swaps = {"_P": "_N", "_N": "_P", "DP": "DN", "DN": "DP", "D+": "D-", "D-": "D+"}
    tail = name[-2:].upper()
    if tail in swaps:
        return name[:-2] + swaps[tail]
    return ""


def guess_voltage(name: str) -> str | None:
    upper = name.upper()
    if "3V3" in upper or "3.3" in upper or "+3V3" in upper:
        return "3.3V"
    if "5V0" in upper or "+5V" in upper or "5V" in upper:
        return "5V"
    if "1V8" in upper or "1.8" in upper:
        return "1.8V"
    if "1V2" in upper or "1.2" in upper:
        return "1.2V"
    if "2V5" in upper or "2.5" in upper:
        return "2.5V"
    if "12V" in upper:
        return "12V"
    if "24V" in upper:
        return "24V"
    if "VBUS" in upper:
        return "5V"
    if "VBAT" in upper:
        return "3.7V"
    return None


def guess_diff_interface(name: str) -> str:
    upper = name.upper()
    if "USB" in upper:
        return "USB"
    if "ETH" in upper or "MDIO" in upper:
        return "Ethernet"
    if "HDMI" in upper:
        return "HDMI"
    if "LVDS" in upper:
        return "LVDS"
    if "CAN" in upper:
        return "CAN"
    if "RS485" in upper or "RS-485" in upper:
        return "RS-485"
    if "PCIE" in upper or "PCI" in upper:
        return "PCIe"
    if "SATA" in upper:
        return "SATA"
    if "MIPI" in upper:
        return "MIPI"
    return "unknown"


def classify_component(ref: str, desc: str) -> str:
    if not ref:
        return "unknown"
    first = ref[0]
    if first == "U":
        return "IC"
    if first == "C":
        return "capacitor"
    if first == "R":
        return "resistor"
    if first == "L":
        return "inductor"
    if first == "D":
        upper = desc.upper()
        if "LED" in upper:
            return "LED"
        if "TVS" in upper or "ESD" in upper:
            return "TVS"
        if "ZENER" in upper:
            return "zener"
        return "diode"
    if first == "Q":
        return "transistor"
    if first == "J":
        return "connector"
    if first in ("X", "Y"):
        return "crystal"
    if first == "F":
        return "fuse"
    if first == "T":
        return "transformer"
    if first == "K":
        return "relay"
    if ref[:2] == "FB":
        return "ferrite_bead"
    if ref[:2] == "TP":
        return "test_point"
    if ref[:2] == "SW":
        return "switch"
    if ref[:2] == "BT":
        return "battery"
    return "other"


def needs_trace_detail(name: str) -> bool:
    if is_clock_net(name) or diff_pair_member(name) != 0:
        return True
    upper = name.upper()
    return any(t in upper for t in _HS_TOKENS)


def is_copper_layer(num: int, name: str = "") -> bool:
    """Copper detection: EAGLE 1-16, Fusion 257-304, 63/64 legacy, plus a
    name fallback for renamed layers in odd slots. Unlike the ULPs, the
    EAGLE system layers 17-52 (Pads/Vias/Unrouted/silk/docu...) are excluded
    unconditionally — the stackup ULP's bare name fallback classified layer
    19 "Unrouted" as copper ("ROUTE" substring), which drags airwires into
    trace aggregates and the copper stack."""
    if 1 <= num <= 16 or 257 <= num <= 304 or num in (63, 64):
        return True
    if 17 <= num <= 52:
        return False
    upper = name.upper()
    return upper in ("TOP", "BOTTOM") or "ROUTE" in upper or "INNER" in upper


def copper_rank(num: int) -> int:
    if num == 1:
        return 0
    if 2 <= num <= 15:
        return num
    if num == 16:
        return 200
    if num == 63:
        return 100
    if num == 64:
        return 101
    if 257 <= num <= 303:
        return 250 + (num - 257)
    if num == 304:
        return 400
    return 50 + num


def sanitize(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in s)


def extract_base_name(fullpath: str) -> str:
    """Design name from a path — the ULP's rules: strip dir, extension, a
    trailing Fusion ' v<digits>' suffix, and map spaces to underscores."""
    base = fullpath.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in base[1:]:
        base = base.rsplit(".", 1)[0]
    parts = base.rsplit(" v", 1)
    if len(parts) == 2 and parts[1].isdigit() and parts[0]:
        base = parts[0]
    return base.replace(" ", "_")


def r4(v: float) -> float:
    return round(v + 0.0, 4)


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

class CaptureError(RuntimeError):
    pass


LATCH_HINT = (
    "Fusion's execute channel is latched ('command dialog is open' — usually "
    "nothing is visible). Press Escape once in the Fusion window and re-run."
)


class Exporter:
    def __init__(self, bridge: FusionBridge):
        self.bridge = bridge

    # -- plumbing ----------------------------------------------------------

    def _read(self, entity: str, obj: dict | None = None) -> list[dict]:
        return self.bridge.read_all(entity, obj)

    def _dispatch(self, command: str) -> None:
        result = self.bridge.run_eagle(command)
        if not result.get("success", True):
            err = result.get("error") or result.get("message") or result
            raise CaptureError(f"dispatch refused: {command!r} -> {err}\n{LATCH_HINT}")

    def wait_channel(self, timeout: float = 120.0) -> None:
        """Block until the execute channel accepts dispatches.

        The dialog latch (a known Fusion bug — nothing visible on screen) can
        arm after a dispatch batch; only a keypress in the Fusion window
        clears it. Reads keep working, so we poll a no-op script and tell the
        user exactly what to do.
        """
        deadline = time.time() + timeout
        prompted = False
        while True:
            result = self.bridge.execute_script("def run(_context):\n    pass\n")
            if result.get("success", True):
                return
            if not prompted:
                print("Fusion's execute channel is latched (invisible dialog — "
                      "known Fusion bug). Press Escape once in the Fusion "
                      "window; waiting...", file=sys.stderr)
                prompted = True
            if time.time() > deadline:
                raise CaptureError("execute channel stayed latched. " + LATCH_HINT)
            time.sleep(2.0)

    def ensure_schematic(self) -> None:
        if self._read("electronics.Sheet", {"pagination": {"limit": 1, "offset": 0}}):
            return
        self.wait_channel()
        self._dispatch("EDIT .S1;")
        for _ in range(20):
            if self._read("electronics.Sheet", {"pagination": {"limit": 1, "offset": 0}}):
                return
            time.sleep(0.5)
        raise CaptureError("schematic editor did not become active after EDIT .S1; "
                           "is an Electronics design open?")

    def ensure_board(self) -> None:
        if self._read("electronics.Board", {"pagination": {"limit": 1, "offset": 0}}):
            return
        self.wait_channel()
        self._dispatch("EDIT .brd;")
        for _ in range(20):
            if self._read("electronics.Board", {"pagination": {"limit": 1, "offset": 0}}):
                return
            time.sleep(0.5)
        raise CaptureError("board editor did not become active after EDIT .brd; "
                           "does this design have a board?")

    @staticmethod
    def _by_id(rows: list[dict], key: str = "object_id") -> dict[int, dict]:
        return {row[key]: row for row in rows}

    @staticmethod
    def _now() -> str:
        return time.strftime("%m/%d/%Y %I:%M %p").lstrip("0").replace("/0", "/")

    # -- schematic ---------------------------------------------------------

    def gather_schematic(self) -> dict:
        self.ensure_schematic()
        sch_rows = self._read("electronics.Schematic")
        if not sch_rows:
            raise CaptureError("no schematic readable")
        sheets = self._read("electronics.Sheet")
        parts = self._read("electronics.Part")
        devices = self._by_id(self._read("electronics.Device"))
        devicesets = self._by_id(self._read("electronics.DeviceSet"))
        packages = self._by_id(self._read("electronics.Package"))
        nets = self._read("electronics.Net")
        classes = {c["number"]: c for c in self._read("electronics.NetClass")}
        pinrefs = self._read("electronics.PinRef")
        pins = self._by_id(self._read("electronics.Pin"))
        part_by_id = self._by_id(parts)
        variantdefs = self._read("electronics.VariantDef")

        attrs = self._read("electronics.Attribute")
        if not attrs and parts:
            # Some servers only surface attributes under a part filter.
            probe = self._read("electronics.Attribute", {"filters": [
                {"property": "part_object_id", "op": "eq",
                 "value": parts[0]["object_id"]}]})
            if probe:
                attrs = []
                for p in parts:
                    attrs.extend(self._read("electronics.Attribute", {"filters": [
                        {"property": "part_object_id", "op": "eq",
                         "value": p["object_id"]}]}))
        attrs_by_part: dict[int, dict[str, str]] = {}
        for a in attrs:
            pid = a.get("part_object_id", 0)
            if pid:
                attrs_by_part.setdefault(pid, {})[a["name"]] = a.get("value", "")

        # -- components --
        components = []
        for p in parts:
            dev = devices.get(p.get("device_object_id", 0), {})
            if not dev or not dev.get("package_object_id"):
                continue  # ULP: skip parts without a package (supply symbols)
            ds = devicesets.get(p.get("deviceset_object_id", 0), {})
            pkg = packages.get(dev.get("package_object_id", 0), {})
            p_attrs = attrs_by_part.get(p["object_id"], {})
            value = p.get("value", "")
            skip = value.startswith("FID") or value.startswith("DNP")
            if p_attrs.get("DNI") == "1" or p_attrs.get("DNP") == "1":
                skip = True
            headline = dev.get("headline", "")
            components.append({
                "ref": p["name"],
                "value": value,
                "package": pkg.get("name", ""),
                "device": ds.get("name", "") + dev.get("name", ""),
                "description": headline,
                "populate": not skip,
                "type": classify_component(p["name"], headline),
                "attributes": p_attrs,
            })

        # -- nets + analysis --
        # EAGLE's N.pinrefs omits supply-symbol stamps (GND1, +3V2, ...);
        # the MCP PinRef table includes them. Filter parts with no package —
        # the same rule that excludes them from components — for parity.
        packaged = {p["object_id"] for p in parts
                    if devices.get(p.get("device_object_id", 0), {}).get("package_object_id")}
        prefs_by_net: dict[int, list[dict]] = {}
        for pr in pinrefs:
            if pr.get("part_object_id") not in packaged:
                continue
            prefs_by_net.setdefault(pr.get("net_object_id", 0), []).append(pr)

        net_entries = []
        power_nets, ground_nets, clock_nets = [], [], []
        diff_pairs, floating, single_pin = [], [], []
        for n in nets:
            name = n["name"]
            cls = classes.get(n.get("net_class_number", 0), {})
            member = diff_pair_member(name)
            partner = diff_partner(name)
            pins_out = []
            has_driver = has_input = has_power = False
            input_pins = []
            for pr in prefs_by_net.get(n["object_id"], []):
                part = part_by_id.get(pr.get("part_object_id", 0), {})
                pin = pins.get(pr.get("pin_object_id", 0), {})
                direction = pin.get("direction", -1)
                pins_out.append({
                    "part": part.get("name", ""),
                    "pin": pin.get("name", ""),
                    "direction": PIN_DIRECTION.get(direction, "UNK"),
                })
                if direction in (2, 3):
                    has_driver = True
                if direction in (5, 8):
                    has_power = True
                if direction == 1:
                    has_input = True
                    input_pins.append((part.get("name", ""), pin.get("name", "")))
            pwr, gnd = is_power_net(name), is_ground_net(name)
            net_entries.append({
                "name": name,
                "class": {
                    "name": cls.get("name", ""),
                    "width_mm": r4(cls.get("width", 0)),
                    "clearance_mm": None,  # not exposed over MCP (gap 1)
                },
                "is_power": pwr,
                "is_ground": gnd,
                "is_clock": is_clock_net(name),
                "is_differential": member != 0,
                "diff_pair_partner": partner if member != 0 else None,
                "voltage_guess": guess_voltage(name),
                "pins": pins_out,
            })
            if pwr:
                power_nets.append(name)
            if gnd:
                ground_nets.append(name)
            if is_clock_net(name):
                clock_nets.append(name)
            if member == 1:
                diff_pairs.append({"positive": name, "negative": partner,
                                   "interface": guess_diff_interface(name)})
            if len(pins_out) == 1:
                single_pin.append(name)
            if has_input and not has_driver and not has_power and not pwr and not gnd:
                floating.extend({"part": pn, "pin": pin} for pn, pin in input_pins)

        return {
            "thomsonlint_version": VERSION,
            "export_date": self._now(),
            "mode": "schematic",
            "project": {
                "name": sch_rows[0].get("name", ""),
                # variant(): Fusion returns literally "''" with no variants
                # defined; the *active* variant is unreadable over MCP (gap 5).
                "variant": "''" if not variantdefs else None,
                "sheets": len(sheets),
            },
            "components": components,
            "nets": net_entries,
            "analysis": {
                "power_nets": power_nets,
                "ground_nets": ground_nets,
                "differential_pairs": diff_pairs,
                "clock_nets": clock_nets,
                "floating_inputs": floating,
                "single_pin_nets": single_pin,
            },
        }

    # -- board -------------------------------------------------------------

    @staticmethod
    def _element_transform(el: dict, lx: float, ly: float) -> tuple[float, float]:
        """Package-local contact -> absolute board position. Mirror flips X
        before the CCW rotation (validated live against Smd global rows)."""
        if el.get("mirror"):
            lx = -lx
        a = math.radians(el.get("angle", 0.0))
        ca, sa = math.cos(a), math.sin(a)
        return (el["x"] + lx * ca - ly * sa, el["y"] + lx * sa + ly * ca)

    def gather_board(self) -> tuple[dict, dict]:
        """Returns (brd_export, stack_export) — one editor pass for both."""
        self.ensure_board()
        board_rows = self._read("electronics.Board")
        if not board_rows:
            raise CaptureError("no board readable")
        board = board_rows[0]
        elements = self._read("electronics.Element")
        packages = self._by_id(self._read("electronics.Package"))
        contacts = self._read("electronics.Contact")
        contactrefs = self._read("electronics.ContactRef")
        smds = self._read("electronics.Smd")
        tht_pads = self._read("electronics.Pad")
        signals = self._read("electronics.Signal")
        wires = self._read("electronics.Wire")
        vias = self._read("electronics.Via")
        pours = self._read("electronics.PolyPour")
        layers = self._read("electronics.Layer")
        holes = self._read("electronics.Hole")

        layer_by_num = {l["number"]: l for l in layers}

        def copper(num: int) -> bool:
            return is_copper_layer(num, layer_by_num.get(num, {}).get("name", ""))

        # -- pad instances (global coords, resolved signal) --
        inst_pads = {}
        for row in smds:
            inst_pads[row["object_id"]] = row
        for row in tht_pads:
            inst_pads[row["object_id"]] = row

        contacts_by_pkg: dict[int, list[dict]] = {}
        for c in contacts:
            contacts_by_pkg.setdefault(c.get("package_object_id", 0), []).append(c)

        crefs_by_element: dict[int, list[dict]] = {}
        for cr in contactrefs:
            crefs_by_element.setdefault(cr.get("element_object_id", 0), []).append(cr)

        # -- components with pads --
        # Canonical pad list = the package's contacts transformed by the
        # element placement (covers unconnected pads — gap 6). Where the pad
        # is connected, cross-check against the Smd/Pad global row.
        components = []
        max_pad_dev = 0.0
        for el in elements:
            pkg = packages.get(el.get("package_object_id", 0), {})
            pads_out = []
            for c in contacts_by_pkg.get(el.get("package_object_id", 0), []):
                gx, gy = self._element_transform(el, c.get("x", 0), c.get("y", 0))
                pads_out.append({"name": c["name"], "x_mm": r4(gx), "y_mm": r4(gy)})
            for cr in crefs_by_element.get(el["object_id"], []):
                ref_pad = inst_pads.get(cr.get("contact_object_id", 0))
                if not ref_pad:
                    continue
                match = next((p for p in pads_out if p["name"] == ref_pad.get("name")), None)
                if match:
                    dev = math.hypot(match["x_mm"] - ref_pad["x"],
                                     match["y_mm"] - ref_pad["y"])
                    max_pad_dev = max(max_pad_dev, dev)
            components.append({
                "ref": el["name"],
                "package": pkg.get("name", ""),
                "value": el.get("value", ""),
                "x_mm": r4(el["x"]),
                "y_mm": r4(el["y"]),
                "rotation": round(el.get("angle", 0.0), 1),
                "side": "bottom" if el.get("mirror") else "top",
                "pads": pads_out,
            })
        if max_pad_dev > 0.01:
            print(f"WARNING: pad transform deviates from Smd/Pad global rows by "
                  f"up to {max_pad_dev:.4f} mm — investigate before trusting pads",
                  file=sys.stderr)

        # -- board geometry --
        # The outline is layer-20 board-parented geometry: wires for
        # rectangular boards, circles for round ones (comet is a circle).
        circles = self._read("electronics.Circle")
        xs, ys = [], []
        for w in wires:
            if w.get("layer") == 20 and w.get("board_object_id"):
                xs += [w["x1"], w["x2"]]
                ys += [w["y1"], w["y2"]]
        for c in circles:
            if c.get("layer") == 20 and c.get("board_object_id"):
                r = c.get("radius", 0)
                xs += [c["x"] - r, c["x"] + r]
                ys += [c["y"] - r, c["y"] + r]
        if xs:
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        else:
            x1 = y1 = x2 = y2 = 0.0
            print("WARNING: no layer-20 board outline geometry found — "
                  "board.area is zeroed and edge distances are meaningless",
                  file=sys.stderr)
        area = {"width_mm": r4(x2 - x1), "height_mm": r4(y2 - y1),
                "x1_mm": r4(x1), "y1_mm": r4(y1), "x2_mm": r4(x2), "y2_mm": r4(y2)}

        signal_by_id = self._by_id(signals)
        layers_used = [{"number": l["number"], "name": l["name"]}
                       for l in layers if l.get("used")]
        layer_count = sum(1 for l in layers
                          if l.get("used") and is_copper_layer(l["number"], l["name"]))

        # B.holes() in the ULP sees board-parented holes only; the MCP read
        # also returns footprint-definition holes in package space — exclude.
        holes_out = [{"x_mm": r4(h["x"]), "y_mm": r4(h["y"]),
                      "drill_mm": r4(h.get("drill", 0))}
                     for h in holes if h.get("board_object_id")]

        polygons = []
        for pp in pours:
            if not pp.get("signal_object_id") or not copper(pp.get("layer", 0)):
                continue
            polygons.append({
                "signal": signal_by_id.get(pp["signal_object_id"], {}).get("name", ""),
                "layer": pp["layer"],
                "thermals": bool(pp.get("thermals")),
                "isolate_mm": r4(pp.get("isolate", 0)),
                "rank": pp.get("rank", 0),
            })

        # -- signals with trace aggregates --
        wires_by_signal: dict[int, list[dict]] = {}
        for w in wires:
            sid = w.get("signal_object_id", 0)
            if sid:
                wires_by_signal.setdefault(sid, []).append(w)
        via_count_by_signal: dict[int, int] = {}
        for v in vias:
            sid = v.get("signal_object_id", 0)
            via_count_by_signal[sid] = via_count_by_signal.get(sid, 0) + 1

        signals_out = []
        for s in signals:
            name = s["name"]
            total = 0.0
            min_w, max_w, seg_count = 99999.0, 0.0, 0
            segs = []
            for w in wires_by_signal.get(s["object_id"], []):
                if not copper(w.get("layer", 0)):
                    continue
                total += math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"])
                width = w.get("width", 0)
                min_w, max_w = min(min_w, width), max(max_w, width)
                seg_count += 1
                segs.append({"layer": w["layer"],
                             "x1_mm": r4(w["x1"]), "y1_mm": r4(w["y1"]),
                             "x2_mm": r4(w["x2"]), "y2_mm": r4(w["y2"]),
                             "width_mm": r4(width)})
            if seg_count == 0:
                min_w = 0.0
            entry = {
                "name": name,
                "is_power": is_power_net(name),
                "is_ground": is_ground_net(name),
                "is_clock": is_clock_net(name),
                "trace_length_mm": r4(total),
                "min_width_mm": r4(min_w),
                "max_width_mm": r4(max_w),
                "via_count": via_count_by_signal.get(s["object_id"], 0),
                "segment_count": seg_count,
            }
            if needs_trace_detail(name):
                entry["trace_segments"] = segs
            signals_out.append(entry)

        # -- analysis --
        edge = []
        for el in elements:
            d = min(el["x"] - x1, x2 - el["x"], el["y"] - y1, y2 - el["y"])
            if d < 3.0:
                edge.append({"ref": el["name"], "min_distance_mm": r4(d)})

        element_by_id = self._by_id(elements)
        decap = []
        for s in signals:
            name = s["name"]
            if not is_power_net(name) or is_ground_net(name):
                continue
            ic_pins, cap_pins = [], []
            for cr in contactrefs:
                if cr.get("signal_object_id") != s["object_id"]:
                    continue
                el = element_by_id.get(cr.get("element_object_id", 0), {})
                pad = inst_pads.get(cr.get("contact_object_id", 0))
                ref = el.get("name", "")
                if not ref or pad is None:
                    continue
                row = (ref, pad.get("name", ""), pad["x"], pad["y"])
                if ref[0] == "U":
                    ic_pins.append(row)
                elif ref[0] == "C":
                    cap_pins.append(row)
            for ic in ic_pins:
                best, best_d = None, 99999.0
                for cp in cap_pins:
                    d = math.hypot(ic[2] - cp[2], ic[3] - cp[3])
                    if d < best_d:
                        best, best_d = cp, d
                if best:
                    decap.append({
                        "ic_ref": ic[0], "ic_pin": ic[1],
                        "ic_pin_x_mm": r4(ic[2]), "ic_pin_y_mm": r4(ic[3]),
                        "cap_ref": best[0], "cap_pin": best[1],
                        "cap_pin_x_mm": r4(best[2]), "cap_pin_y_mm": r4(best[3]),
                        "distance_mm": round(best_d, 2), "net": name,
                    })

        ground_planes = [p["layer"] for p in polygons if is_ground_net(p["signal"])]

        brd = {
            "thomsonlint_version": VERSION,
            "export_date": self._now(),
            "mode": "board",
            "components": components,
            "board": {"area": area, "layers_used": layers_used,
                      "layer_count": layer_count, "holes": holes_out,
                      "polygons": polygons},
            "signals": signals_out,
            "analysis": {
                "component_edge_distances": edge,
                "decoupling_proximity": decap,
                "ground_plane_layers": ground_planes,
            },
        }

        # -- stackup (same editor pass) --
        all_layers = [{"number": l["number"], "name": l["name"],
                       "used": bool(l.get("used")),
                       "is_copper": is_copper_layer(l["number"], l["name"]),
                       "visible": bool(l.get("visible"))} for l in layers]
        used_copper = sorted(
            (l for l in layers
             if l.get("used") and is_copper_layer(l["number"], l["name"])),
            key=lambda l: copper_rank(l["number"]))
        copper_stack = []
        for i, l in enumerate(used_copper):
            position = ("top" if i == 0 else
                        "bottom" if i == len(used_copper) - 1 else "inner")
            copper_stack.append({"index": i, "position": position,
                                 "layer_number": l["number"],
                                 "layer_name": l["name"]})
        stack = {
            "thomsonlint_version": VERSION,
            "export_date": self._now(),
            "mode": "stackup",
            "project": {
                "name": board.get("name", ""),
                "variant": "''",
            },
            "all_layers": all_layers,
            "copper_stack": copper_stack,
            "copper_layer_count": len(used_copper),
            "board_description": board.get("description", ""),
            "design_rule_note": ("Per-layer thickness/material lives in the .dru "
                                 "file; not accessible from ULP. Export the .dru "
                                 "alongside this JSON."),
        }
        return brd, stack

    # -- images ------------------------------------------------------------

    def images_schematic(self, prefix_wsl: str, dpi: int) -> list[str]:
        """Per-sheet PNGs. ``prefix_wsl`` must live under /mnt/<drive>."""
        self.ensure_schematic()
        sheets = self._read("electronics.Sheet")
        prefix_win = wsl_to_windows(prefix_wsl).replace("\\", "/")
        # A no-op EDIT (opening the sheet that is already open) arms the
        # dialog latch; a real switch does not (isolated live 2026-08-28:
        # EDIT .S1 from the board -> clean; EDIT .S1 again -> latched).
        # 1-sheet designs therefore get no EDIT at all, and multi-sheet
        # designs capture sheet 1 LAST so every EDIT is a real switch —
        # except possibly the first, which wait_channel() absorbs next pass.
        n = len(sheets)
        order = [1] if n == 1 else list(range(2, n + 1)) + [1]
        targets, cmds = [], []
        for i in order:
            wsl = f"{prefix_wsl}-img-sch-p{i}.png"
            targets.append(wsl)
            if os.path.exists(wsl):
                os.remove(wsl)  # steinmetz pattern: no overwrite prompt possible
            edit = "" if n == 1 else f"EDIT .S{i}; "
            cmds.append(f"{edit}WINDOW FIT; "
                        f"EXPORT IMAGE '{prefix_win}-img-sch-p{i}.png' {dpi};")
        self.wait_channel()
        self._dispatch(" ".join(cmds))
        return self._collect(targets)

    def images_board(self, prefix_wsl: str, dpi: int) -> list[str]:
        """Silk top/bottom + one PNG per in-use copper layer."""
        self.ensure_board()
        layers = self._read("electronics.Layer")
        wires = self._read("electronics.Wire")
        pours = self._read("electronics.PolyPour")
        smds = self._read("electronics.Smd")
        has_obj: set[int] = set()
        for w in wires:
            if w.get("signal_object_id"):
                has_obj.add(w["layer"])
        for p in pours:
            if p.get("signal_object_id"):
                has_obj.add(p["layer"])
        for s in smds:
            has_obj.add(s.get("layer", 0))

        prefix_win = wsl_to_windows(prefix_wsl).replace("\\", "/")
        plan = [("-img-silk-top.png", "DISPLAY NONE 20 21 25 51;"),
                ("-img-silk-bot.png", "DISPLAY NONE 20 22 26 52;")]
        for l in layers:
            if not is_copper_layer(l["number"], l["name"]):
                continue
            if not (l.get("used") or l["number"] in has_obj):
                continue
            plan.append((f"-img-cu-L{l['number']}-{sanitize(l['name'])}.png",
                         f"DISPLAY NONE 20 17 18 19 21 22 39 40 41 42 {l['number']};"))

        targets, cmds = [], ["RATSNEST;"]
        for suffix, display in plan:
            wsl = prefix_wsl + suffix
            targets.append(wsl)
            if os.path.exists(wsl):
                os.remove(wsl)
            cmds.append(f"{display} WINDOW FIT; "
                        f"EXPORT IMAGE '{prefix_win}{suffix}' {dpi};")
        cmds.append("DISPLAY ALL;")
        self.wait_channel()
        self._dispatch(" ".join(cmds))
        return self._collect(targets)

    @staticmethod
    def _collect(targets: list[str], timeout: float = 60.0) -> list[str]:
        """Wait for the dispatched EXPORT IMAGEs to land; error on any miss."""
        deadline = time.time() + timeout
        pending = list(targets)
        while pending and time.time() < deadline:
            pending = [t for t in pending if not os.path.exists(t)]
            if pending:
                time.sleep(1.0)
        if pending:
            raise CaptureError(f"image(s) never appeared: {pending} — a mid-chain "
                               f"error modal may have eaten the rest of the chain")
        return targets


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_json(doc: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    print(f"wrote {path}")


def _design_name(exp: Exporter, board_side: bool) -> str:
    rows = exp._read("electronics.Board" if board_side else "electronics.Schematic",
                     {"pagination": {"limit": 1, "offset": 0}})
    if not rows:
        raise CaptureError("cannot determine design name — no design readable")
    return extract_base_name(rows[0].get("name", "design"))


def cmd_sch(exp: Exporter, args) -> None:
    exp.ensure_schematic()
    doc = exp.gather_schematic()
    name = _design_name(exp, board_side=False)
    _write_json(doc, Path(args.out) / f"{name}-thomson-export-sch.json")


def cmd_brd(exp: Exporter, args) -> None:
    exp.ensure_board()
    brd, stack = exp.gather_board()
    name = _design_name(exp, board_side=True)
    _write_json(brd, Path(args.out) / f"{name}-thomson-export-brd.json")
    _write_json(stack, Path(args.out) / f"{name}-thomson-export-stack.json")


def _image_prefix(exp: Exporter, args, board_side: bool) -> str:
    share = Path(args.share) / "exports"
    share.mkdir(parents=True, exist_ok=True)
    return str(share / _design_name(exp, board_side))


def cmd_images(exp: Exporter, args) -> None:
    out = Path(args.out)
    exp.ensure_schematic()
    produced = exp.images_schematic(_image_prefix(exp, args, False), args.sch_dpi)
    exp.ensure_board()
    produced += exp.images_board(_image_prefix(exp, args, True), args.brd_dpi)
    out.mkdir(parents=True, exist_ok=True)
    for src in produced:
        dst = out / Path(src).name
        if Path(src).resolve() != dst.resolve():
            dst.write_bytes(Path(src).read_bytes())
        print(f"image {dst} ({dst.stat().st_size} bytes)")


def cmd_all(exp: Exporter, args) -> None:
    cmd_sch(exp, args)
    if not args.skip_images:
        exp.ensure_schematic()
        sch_imgs = exp.images_schematic(_image_prefix(exp, args, False), args.sch_dpi)
    else:
        sch_imgs = []
    cmd_brd(exp, args)
    if not args.skip_images:
        brd_imgs = exp.images_board(_image_prefix(exp, args, True), args.brd_dpi)
        out = Path(args.out)
        for src in sch_imgs + brd_imgs:
            dst = out / Path(src).name
            if Path(src).resolve() != dst.resolve():
                dst.write_bytes(Path(src).read_bytes())
            print(f"image {dst} ({dst.stat().st_size} bytes)")
    exp.wait_channel()
    exp._dispatch("EDIT .S1;")  # leave the session on the schematic tab


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fusion-host", default=None)
    p.add_argument("--out", default=str(repo / "exports"),
                   help="directory for JSON files and copied images")
    p.add_argument("--share", default=os.environ.get("THOMSONLINT_FUSION_SHARE",
                                                     DEFAULT_SHARE_WSL),
                   help="WSL path under /mnt/<drive> where Fusion writes PNGs")
    p.add_argument("--sch-dpi", type=int, default=300)
    p.add_argument("--brd-dpi", type=int, default=1200)
    p.add_argument("--skip-images", action="store_true",
                   help="'all' verb: JSON only")
    p.add_argument("verb", choices=["sch", "brd", "images", "all"])
    args = p.parse_args(argv)

    exp = Exporter(FusionBridge(host=args.fusion_host))
    try:
        {"sch": cmd_sch, "brd": cmd_brd, "images": cmd_images,
         "all": cmd_all}[args.verb](exp, args)
    except (BridgeError, CaptureError) as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
