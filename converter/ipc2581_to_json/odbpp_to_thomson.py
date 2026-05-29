#!/usr/bin/env python3
"""odbpp_to_thomson.py

ODB++ backfill module for ThomsonLint.  Parses Altium Designer ODB++ exports
and backfills routing geometry into existing Thomson board JSON files that were
produced from an IPC-2581 primary parse.

Supports .zip, .tgz / .tar.gz archives and uncompressed ODB++ directories.
All internal keys are normalised by stripping any leading ``odb/`` path prefix
so that the same code path handles both archive and directory inputs.

Phase 1 — Layer-level geometry (always populated)
  * Route segments   (x1/y1/x2/y2, width, length, layer)
  * trace_width_usage_by_layer  (width histogram per copper layer)
  * route_length_by_layer       (total length per copper layer)
  * copper_route_count

Phase 2 — Net-level routing data (populated when eda/data cross-reference
          is available, which is always the case for Altium v8.1 exports)
  * route_length_by_net   (total/min/max length per net)
  * trace_width_by_net    (min/max width per net)
  * routed_net_count
  * routing_topology_summary per-net route_count / trace width updates

Architecture note
-----------------
Altium ODB++ does NOT embed the net name directly on Line (L) feature records.
Net-to-feature mapping is carried exclusively in ``steps/pcb/eda/data``:

    LYR layer_name_0 layer_name_1 ...     ← layer index table
    NET <net_name>
    FID C <layer_idx> <feature_idx>       ← 0-based feature record index

Feature index counts every L / A / P / S record in order of appearance in
the features file (L and A are routing; P are pads; S are surfaces / pours).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

VERSION = "odbpp-adapter-0.1"

# ── Compiled regexes ──────────────────────────────────────────────────────────

_SYM_DEF_RE = re.compile(r"^\$(\d+)\s+(\S+)")
_L_RE = re.compile(
    r"^L\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+P\s+(\d+)"
)
_A_RE = re.compile(
    r"^A\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"
    r"\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+P\s+(\d+)\s+([NY])"
)
_NET_DEF_RE = re.compile(r"^\$(\d+)\s+(.+)$")
_NET_HDR_RE = re.compile(r"^NET\s+(.+)$")
_LYR_RE = re.compile(r"^LYR\s+(.+)$")
_FID_RE = re.compile(r"^FID\s+C\s+(\d+)\s+(\d+)$")

# ── Arc length helper ─────────────────────────────────────────────────────────


def _arc_length(
    xs: float, ys: float, xe: float, ye: float,
    xc: float, yc: float, direction: str,
) -> float:
    """Compute arc length from ODB++ arc record.

    ``direction`` values in Altium v8.1 ODB++:
      ``N`` → CCW (counter-clockwise, the short / natural arc)
      ``Y`` → CW  (clockwise)
    Falls back to chord length when the radius is degenerate.
    """
    r = math.sqrt((xs - xc) ** 2 + (ys - yc) ** 2)
    if r < 1e-12:
        return math.sqrt((xe - xs) ** 2 + (ye - ys) ** 2)
    a_s = math.atan2(ys - yc, xs - xc)
    a_e = math.atan2(ye - yc, xe - xc)
    if direction == "N":          # CCW
        span = a_e - a_s
        if span < 0:
            span += 2 * math.pi
    else:                         # CW
        span = a_s - a_e
        if span < 0:
            span += 2 * math.pi
    return r * span


# ── ODB++ archive / directory loader ─────────────────────────────────────────


def _is_odbpp_zip(path: Path) -> bool:
    """Quickly check whether a zip file contains ODB++ content."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = {e.filename.lower() for e in zf.filelist}
            return any(
                n in names
                for n in ("odb/matrix/matrix", "odb/misc/info", "matrix/matrix")
            )
    except Exception:
        return False


def _is_odbpp_tgz(path: Path) -> bool:
    """Quickly check whether a tar/tgz file contains ODB++ content."""
    try:
        with tarfile.open(path) as tf:
            names = {m.name.lower() for m in tf.getmembers() if m.isfile()}
            return any(
                n in names
                for n in ("odb/matrix/matrix", "odb/misc/info", "matrix/matrix")
            )
    except Exception:
        return False


class ODBppParser:
    """Parser for Altium Designer ODB++ exports.

    Accepts:
      * Uncompressed directory (the ``odb/`` root, or a directory containing it)
      * ``.zip`` archive
      * ``.tgz`` / ``.tar.gz`` archive

    Public attributes after ``__init__``:
      ``units``                   – ``"MM"`` or ``"INCH"``
      ``odb_version``             – e.g. ``"8.1"``
      ``copper_layer_names``      – ordered list of copper layer names
      ``route_segments``          – list of route segment dicts (all copper layers)
      ``route_length_by_layer``   – aggregate per layer
      ``trace_width_usage_by_layer`` – width histogram per layer
      ``route_length_by_net``     – per net (Phase 2; empty when eda/data absent)
      ``trace_width_by_net``      – per net (Phase 2; empty when eda/data absent)
      ``routed_nets``             – set of net names that have ≥1 route segment
    """

    def __init__(self, odb_path: Path):
        self.source_path = odb_path
        self._files: dict[str, bytes] = {}
        self._load_source(odb_path)

        self.units: str = "MM"
        self.odb_version: str = "unknown"
        self.copper_layer_names: list[str] = []

        # Net name table from cadnet/netlist: index → name
        self._net_by_index: dict[int, str] = {}

        # Phase 2 cross-reference: (layer_name, feat_idx) → net_name
        self._feat_to_net: dict[tuple[str, int], str] = {}

        self.route_segments: list[dict[str, Any]] = []
        self.route_length_by_layer: list[dict[str, Any]] = []
        self.trace_width_usage_by_layer: list[dict[str, Any]] = []
        self.route_length_by_net: list[dict[str, Any]] = []
        self.trace_width_by_net: list[dict[str, Any]] = []
        self.routed_nets: set[str] = set()

        self._parse_info()
        self._parse_net_table()
        self._parse_matrix()
        self._parse_eda_data()
        self._parse_all_copper_layers()
        self._build_derived_tables()

    # ── Source loading ─────────────────────────────────────────────────────

    def _normalize_key(self, path: str) -> str:
        """Normalise path to lowercase, forward slashes, strip leading ``odb/``."""
        p = path.replace("\\", "/").lower()
        if p.startswith("odb/"):
            p = p[4:]
        return p

    def _load_source(self, path: Path) -> None:
        name = path.name.lower()
        if path.is_dir():
            self._load_from_dir(path)
        elif name.endswith(".zip"):
            self._load_from_zip(path)
        elif name.endswith(".tgz") or name.endswith(".tar.gz"):
            self._load_from_tgz(path)
        else:
            raise ValueError(
                f"Unsupported ODB++ source: {path.suffix!r}. "
                "Expected .zip, .tgz, .tar.gz, or a directory."
            )

    def _load_from_dir(self, path: Path) -> None:
        for f in path.rglob("*"):
            if f.is_file():
                rel = self._normalize_key(str(f.relative_to(path).as_posix()))
                self._files[rel] = f.read_bytes()

    def _load_from_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path) as zf:
            for entry in zf.namelist():
                if not entry.endswith("/"):
                    self._files[self._normalize_key(entry)] = zf.read(entry)

    def _load_from_tgz(self, path: Path) -> None:
        with tarfile.open(path) as tf:
            for member in tf.getmembers():
                if member.isfile():
                    fobj = tf.extractfile(member)
                    if fobj:
                        self._files[self._normalize_key(member.name)] = fobj.read()

    def _read_text(self, key: str) -> str | None:
        data = self._files.get(key.lower())
        if data is None:
            return None
        return data.decode("utf-8", errors="replace")

    # ── Info / metadata ────────────────────────────────────────────────────

    def _parse_info(self) -> None:
        text = self._read_text("misc/info")
        if not text:
            return
        major = minor = ""
        for line in text.splitlines():
            if line.startswith("UNITS="):
                self.units = line[6:].strip().upper()
            elif line.startswith("ODB_VERSION_MAJOR="):
                major = line.split("=", 1)[1].strip()
            elif line.startswith("ODB_VERSION_MINOR="):
                minor = line.split("=", 1)[1].strip()
        if major:
            self.odb_version = f"{major}.{minor}" if minor else major

    # ── Net name table ─────────────────────────────────────────────────────

    def _parse_net_table(self) -> None:
        text = self._read_text("steps/pcb/netlists/cadnet/netlist")
        if not text:
            return
        for line in text.splitlines():
            m = _NET_DEF_RE.match(line.strip())
            if m:
                self._net_by_index[int(m.group(1))] = m.group(2).strip()

    # ── Matrix → copper layer list ─────────────────────────────────────────

    def _parse_matrix(self) -> None:
        text = self._read_text("matrix/matrix")
        if not text:
            return
        # Collect (ROW, NAME) for copper-type layers
        ordered: list[tuple[int, str]] = []
        current: dict[str, str] = {}
        in_layer = False

        def _flush(cur: dict[str, str]) -> None:
            ltype = cur.get("TYPE", "")
            name = cur.get("NAME", "").lower().strip()
            if ltype in {"SIGNAL", "POWER_GROUND", "MIXED"} and name:
                try:
                    row = int(cur.get("ROW", "999"))
                except ValueError:
                    row = 999
                ordered.append((row, name))

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "LAYER {" in line:
                if in_layer:
                    _flush(current)
                current = {}
                in_layer = True
            elif line == "}" and in_layer:
                _flush(current)
                current = {}
                in_layer = False
            elif in_layer and "=" in line:
                k, _, v = line.partition("=")
                current[k.strip()] = v.strip()

        if in_layer and current:
            _flush(current)

        self.copper_layer_names = [name for _, name in sorted(ordered)]

    # ── EDA data → Phase 2 net/feature cross-reference ─────────────────────

    def _parse_eda_data(self) -> None:
        text = self._read_text("steps/pcb/eda/data")
        if not text:
            return

        eda_layer_names: list[str] = []
        # Build (layer_name, feat_idx) → net_name lookup
        net_features: dict[str, list[tuple[str, int]]] = {}

        current_net: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()

            # Layer order line — maps integer index to layer name
            m = _LYR_RE.match(line)
            if m and not eda_layer_names:
                eda_layer_names = [t.strip().lower() for t in m.group(1).split()]
                continue

            # Net header
            m = _NET_HDR_RE.match(line)
            if m:
                current_net = m.group(1).strip()
                if current_net not in net_features:
                    net_features[current_net] = []
                continue

            # Feature ID cross-reference
            if current_net and current_net != "$NONE$":
                m = _FID_RE.match(line)
                if m:
                    layer_idx = int(m.group(1))
                    feat_idx = int(m.group(2))
                    if layer_idx < len(eda_layer_names):
                        net_features[current_net].append(
                            (eda_layer_names[layer_idx], feat_idx)
                        )

        # Invert to (layer_name, feat_idx) → net_name for O(1) lookups
        for net_name, refs in net_features.items():
            for layer_name, feat_idx in refs:
                self._feat_to_net[(layer_name, feat_idx)] = net_name

    # ── Symbol width conversion ────────────────────────────────────────────

    def _symbol_width(self, sym_str: str) -> float | None:
        """Return trace width in the file's native units (MM or INCH).

        ODB++ symbol dimensions are stored in the sub-unit of the UNITS setting:
          MM mode   → dimensions in µm  → divide by 1000 to get mm
          INCH mode → dimensions in mils (0.001 inch) → divide by 1000 to get in
        Only ``r<n>`` (circular) symbols represent trace widths; rectangular
        pad symbols are ignored.
        """
        m = _SYM_DEF_RE.match(sym_str) if " " in sym_str else None
        # sym_str here is already the RHS of the symbol table entry (e.g. "r152.4")
        m2 = re.match(r"^r([\d.]+)$", sym_str, re.IGNORECASE)
        if m2:
            try:
                return float(m2.group(1)) / 1000.0
            except ValueError:
                pass
        return None

    # ── Per-layer feature parsing ──────────────────────────────────────────

    def _parse_layer_features(
        self, layer_name: str
    ) -> list[dict[str, Any]]:
        """Parse L and A records from one copper layer's features file.

        Returns a list of raw segment dicts (not yet final route_segment schema).
        ``feat_idx`` is tracked for ALL feature record types (L/A/P/S) so that
        Phase 2 FID cross-references remain valid.
        """
        key = f"steps/pcb/layers/{layer_name}/features"
        text = self._read_text(key)
        if not text:
            return []

        lines = text.splitlines()

        # Build per-layer symbol table from ``$N sym_name`` lines
        sym_table: dict[int, str] = {}
        for line in lines:
            line = line.strip()
            m = _SYM_DEF_RE.match(line)
            if m:
                sym_table[int(m.group(1))] = m.group(2).strip()

        segments: list[dict[str, Any]] = []
        feat_idx = 0  # 0-based index across all feature record types

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("$"):
                continue

            first_char = line[0] if line else ""

            if first_char == "L":
                m = _L_RE.match(line)
                if m:
                    x1 = float(m.group(1))
                    y1 = float(m.group(2))
                    x2 = float(m.group(3))
                    y2 = float(m.group(4))
                    sym_idx = int(m.group(5))
                    sym_str = sym_table.get(sym_idx, "")
                    width = self._symbol_width(sym_str)
                    length = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                    net = self._feat_to_net.get((layer_name, feat_idx))
                    segments.append({
                        "feat_idx": feat_idx,
                        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                        "sym_str": sym_str,
                        "width": width,
                        "length": length,
                        "is_arc": False,
                        "length_is_estimated": False,
                        "net": net,
                    })
                feat_idx += 1

            elif first_char == "A":
                m = _A_RE.match(line)
                if m:
                    xs, ys = float(m.group(1)), float(m.group(2))
                    xe, ye = float(m.group(3)), float(m.group(4))
                    xc, yc = float(m.group(5)), float(m.group(6))
                    sym_idx = int(m.group(7))
                    direction = m.group(9)
                    sym_str = sym_table.get(sym_idx, "")
                    width = self._symbol_width(sym_str)
                    length = _arc_length(xs, ys, xe, ye, xc, yc, direction)
                    net = self._feat_to_net.get((layer_name, feat_idx))
                    segments.append({
                        "feat_idx": feat_idx,
                        "x1": xs, "y1": ys, "x2": xe, "y2": ye,
                        "sym_str": sym_str,
                        "width": width,
                        "length": length,
                        "is_arc": True,
                        "length_is_estimated": False,
                        "net": net,
                    })
                feat_idx += 1

            elif first_char in ("P", "S"):
                # Pads and surfaces are not routing segments but must be
                # counted to keep feat_idx aligned with eda/data FID refs.
                feat_idx += 1

        return segments

    # ── Full board parse ───────────────────────────────────────────────────

    def _parse_all_copper_layers(self) -> None:
        for layer_name in self.copper_layer_names:
            segs = self._parse_layer_features(layer_name)
            for seg in segs:
                self.route_segments.append({
                    "net": seg["net"],
                    "layer": layer_name,
                    "length": round(seg["length"], 6),
                    "length_units": self.units,
                    "length_is_estimated": seg["length_is_estimated"],
                    "line_width": (
                        round(seg["width"], 6)
                        if seg["width"] is not None else None
                    ),
                    "line_width_units": self.units,
                    "line_desc_ref": seg["sym_str"],
                    "feature_domain": "copper",
                    "curve_count": 1 if seg["is_arc"] else 0,
                    "x1": seg["x1"], "y1": seg["y1"],
                    "x2": seg["x2"], "y2": seg["y2"],
                })

    # ── Derived aggregate tables ───────────────────────────────────────────

    def _build_derived_tables(self) -> None:
        layer_length: dict[str, dict[str, Any]] = {}
        layer_width_key: dict[tuple[str, str | None, float | None], dict[str, Any]] = {}
        net_length: dict[str, dict[str, Any]] = {}
        net_widths: dict[str, list[float]] = {}
        net_sym_refs: dict[str, set[str]] = {}

        for seg in self.route_segments:
            layer = seg["layer"]
            length = seg["length"]
            width = seg["line_width"]
            sym = seg["line_desc_ref"] or ""
            net = seg["net"]

            # Per-layer length
            lr = layer_length.setdefault(layer, {
                "layer": layer,
                "total_route_length": 0.0,
                "length_units": self.units,
                "route_count": 0,
                "estimated_route_count": 0,
            })
            lr["total_route_length"] += length
            lr["route_count"] += 1
            if seg["length_is_estimated"]:
                lr["estimated_route_count"] += 1

            # Per-layer width usage
            wkey = (layer, sym, width)
            wu = layer_width_key.setdefault(wkey, {
                "layer": layer,
                "line_desc_ref": sym,
                "line_width": width,
                "units": self.units,
                "route_count": 0,
            })
            wu["route_count"] += 1

            # Per-net (Phase 2 — only when net attribution is available)
            if net:
                self.routed_nets.add(net)
                nr = net_length.setdefault(net, {
                    "net": net,
                    "total_route_length": 0.0,
                    "length_units": self.units,
                    "route_count": 0,
                    "layers": set(),
                    "_min": float("inf"),
                    "_max": 0.0,
                })
                nr["total_route_length"] += length
                nr["route_count"] += 1
                nr["layers"].add(layer)
                nr["_min"] = min(nr["_min"], length)
                nr["_max"] = max(nr["_max"], length)
                if width is not None:
                    net_widths.setdefault(net, []).append(width)
                if sym:
                    net_sym_refs.setdefault(net, set()).add(sym)

        self.route_length_by_layer = [
            {
                **v,
                "total_route_length": round(v["total_route_length"], 6),
            }
            for v in sorted(layer_length.values(), key=lambda x: x["layer"])
        ]

        self.trace_width_usage_by_layer = [
            v for v in sorted(
                layer_width_key.values(),
                key=lambda x: (x["layer"], x["line_width"] or 0.0),
            )
        ]

        self.route_length_by_net = [
            {
                "net": item["net"],
                "total_route_length": round(item["total_route_length"], 6),
                "length_units": item["length_units"],
                "route_count": item["route_count"],
                "layers": sorted(item["layers"]),
                "min_route_length": (
                    round(item["_min"], 6)
                    if item["_min"] != float("inf") else None
                ),
                "max_route_length": round(item["_max"], 6),
            }
            for item in sorted(net_length.values(), key=lambda x: x["net"])
        ]

        self.trace_width_by_net = [
            {
                "net": net,
                "min_trace_width": min(widths),
                "max_trace_width": max(widths),
                "route_count": net_length[net]["route_count"],
                "layers": sorted(net_length[net]["layers"]),
                "line_desc_refs": sorted(net_sym_refs.get(net, set())),
            }
            for net, widths in sorted(net_widths.items())
            if net in net_length
        ]


# ── Merge helpers ─────────────────────────────────────────────────────────────


def _is_empty(val: Any) -> bool:
    """Return True when a routing field carries no useful data."""
    if val is None:
        return True
    if isinstance(val, (list, dict)):
        return len(val) == 0
    if isinstance(val, (int, float)):
        return val == 0
    return False


def merge_odbpp_into_board(
    parser: ODBppParser,
    board_data: dict[str, Any],
) -> dict[str, Any]:
    """Backfill ODB++ routing geometry into an existing Thomson board JSON.

    Only writes into fields that are currently empty / zero — never overwrites
    data that already exists (i.e. OrCAD IPC-2581 projects are unaffected).

    Fields populated (using existing board JSON schema):
      Phase 1 (always):
        ``routes``                      ← route segment list
        ``route_length_by_layer``       ← per-layer totals
        ``trace_width_usage_by_layer``  ← per-layer width histogram
        ``extraction_counts.copper_route_count``

      Phase 2 (when net attribution available):
        ``route_length_by_net``         ← per-net totals
        ``trace_width_by_net``          ← per-net width summary
        ``routing_topology_summary`` per-net ``route_count`` / trace width
        ``routing_topology_summary.routed_net_count``
        ``extraction_counts.routed_net_count``
    """
    # ── Phase 1 ──────────────────────────────────────────────────────────
    if _is_empty(board_data.get("routes")):
        board_data["routes"] = parser.route_segments

    if _is_empty(board_data.get("route_length_by_layer")):
        board_data["route_length_by_layer"] = parser.route_length_by_layer

    if _is_empty(board_data.get("trace_width_usage_by_layer")):
        board_data["trace_width_usage_by_layer"] = parser.trace_width_usage_by_layer

    ec = board_data.setdefault("extraction_counts", {})
    if ec.get("copper_route_count", 0) == 0:
        ec["copper_route_count"] = len(parser.route_segments)

    # ── Phase 2 ──────────────────────────────────────────────────────────
    if parser.route_length_by_net:
        if _is_empty(board_data.get("route_length_by_net")):
            board_data["route_length_by_net"] = parser.route_length_by_net

        if _is_empty(board_data.get("trace_width_by_net")):
            board_data["trace_width_by_net"] = parser.trace_width_by_net

        if ec.get("routed_net_count", 0) == 0 and parser.routed_nets:
            ec["routed_net_count"] = len(parser.routed_nets)

        # Update routing_topology_summary sub-fields and per-net entries
        rts = board_data.get("routing_topology_summary")
        if isinstance(rts, dict):
            if _is_empty(rts.get("route_length_by_net")):
                rts["route_length_by_net"] = parser.route_length_by_net
            if _is_empty(rts.get("trace_width_by_net")):
                rts["trace_width_by_net"] = parser.trace_width_by_net
            if _is_empty(rts.get("route_length_by_layer")):
                rts["route_length_by_layer"] = parser.route_length_by_layer
            if _is_empty(rts.get("trace_width_usage_by_layer")):
                rts["trace_width_usage_by_layer"] = parser.trace_width_usage_by_layer
            if rts.get("routed_net_count", 0) == 0 and parser.routed_nets:
                rts["routed_net_count"] = len(parser.routed_nets)

            # Per-net topology entries: patch route_count and trace widths
            rln_map = {r["net"]: r for r in parser.route_length_by_net}
            twn_map = {r["net"]: r for r in parser.trace_width_by_net}
            for row in rts.get("nets", []):
                net = row.get("net")
                if not net:
                    continue
                if net in rln_map and row.get("route_count", 0) == 0:
                    row["route_count"] = rln_map[net]["route_count"]
                    row["is_routing_candidate"] = True
                if net in twn_map:
                    if row.get("min_trace_width") is None:
                        row["min_trace_width"] = twn_map[net]["min_trace_width"]
                    if row.get("max_trace_width") is None:
                        row["max_trace_width"] = twn_map[net]["max_trace_width"]

    # ── Source tracking (within existing ``source`` dict) ─────────────────
    source = board_data.get("source")
    if isinstance(source, dict):
        source["odbpp_file"] = parser.source_path.name
        source["odbpp_merge_status"] = "SUCCESS"
        source["odbpp_route_count"] = len(parser.route_segments)

    return board_data


def merge_odbpp_if_available(
    project_root: Path,
    board_data: dict[str, Any],
) -> dict[str, Any]:
    """Auto-discover an ODB++ source and backfill the board JSON if found.

    Searches ``project_root/``, ``input/``, and ``pre_conversion/`` for:
      * Uncompressed ``*.odb/`` directories
      * ``.zip`` archives that contain ODB++ content
      * ``.tgz`` / ``.tar.gz`` archives that contain ODB++ content

    On failure the board JSON is returned unmodified; parse errors are noted
    inside ``source.odbpp_merge_status`` (never raises).
    """
    search_dirs = [project_root]
    for sub in ("input", "pre_conversion"):
        d = project_root / sub
        if d.exists():
            search_dirs.append(d)

    chosen: Path | None = None

    for d in search_dirs:
        if chosen:
            break
        # Uncompressed directory first (unambiguous)
        for p in sorted(d.iterdir()):
            if p.is_dir() and p.suffix.lower() == ".odb":
                chosen = p
                break
        if chosen:
            break
        # zip archives
        for p in sorted(d.glob("*.zip")):
            if _is_odbpp_zip(p):
                chosen = p
                break
        if chosen:
            break
        # tgz archives
        for p in sorted(d.iterdir()):
            if p.is_file() and (
                p.name.lower().endswith(".tgz")
                or p.name.lower().endswith(".tar.gz")
            ):
                if _is_odbpp_tgz(p):
                    chosen = p
                    break

    if chosen is None:
        return board_data

    try:
        parser = ODBppParser(chosen)
        return merge_odbpp_into_board(parser, board_data)
    except Exception as exc:
        source = board_data.get("source")
        if isinstance(source, dict):
            source["odbpp_merge_status"] = f"ERROR: {exc}"
        return board_data


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """CLI: parse an ODB++ archive and backfill a Thomson board JSON."""
    ap = argparse.ArgumentParser(
        description=(
            "Backfill ODB++ routing geometry into a ThomsonLint board JSON. "
            "Accepts .zip, .tgz, .tar.gz archives or uncompressed ODB++ directories."
        )
    )
    ap.add_argument("odb_source", help="ODB++ archive or directory")
    ap.add_argument(
        "board_json",
        help="Target board JSON (e.g. *-thomson-export-brd.json)",
    )
    ap.add_argument("--output", help="Output path (defaults to overwriting board_json)")
    ap.add_argument("--json", action="store_true", help="Emit result summary as JSON")
    args = ap.parse_args()

    odb_path = Path(args.odb_source)
    brd_path = Path(args.board_json)
    out_path = Path(args.output) if args.output else brd_path

    if not odb_path.exists():
        print(f"Error: ODB++ source not found: {odb_path}", file=sys.stderr)
        sys.exit(1)
    if not brd_path.exists():
        print(f"Error: Board JSON not found: {brd_path}", file=sys.stderr)
        sys.exit(1)

    try:
        parser = ODBppParser(odb_path)
    except Exception as exc:
        print(f"Error: Failed to parse ODB++ source: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(brd_path, encoding="utf-8") as f:
            board_data = json.load(f)
    except Exception as exc:
        print(f"Error: Failed to read board JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    board_data = merge_odbpp_into_board(parser, board_data)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(board_data, f, indent=2)
    except Exception as exc:
        print(f"Error: Failed to write output: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps({
            "status": "SUCCESS",
            "odb_source": str(odb_path),
            "board_json": str(brd_path),
            "output": str(out_path),
            "units": parser.units,
            "odb_version": parser.odb_version,
            "copper_layers": parser.copper_layer_names,
            "route_segments": len(parser.route_segments),
            "routed_nets": len(parser.routed_nets),
            "route_length_by_layer_count": len(parser.route_length_by_layer),
        }, indent=2))
    else:
        print(
            f"Success: Backfilled ODB++ routing from {odb_path.name} into {out_path.name}"
        )
        print(f"  Copper layers : {', '.join(parser.copper_layer_names)}")
        print(f"  Route segments: {len(parser.route_segments)}")
        print(f"  Routed nets   : {len(parser.routed_nets)}")
        print(f"  Units         : {parser.units}")


if __name__ == "__main__":
    main()
