#!/usr/bin/env python3
"""ThomsonLint Cross-Source Verification Engine

Deterministic cross-source reconciliation across Schematic, BOM, and Board/Layout files.
Performs tripartite set operations and topological mapping that LLMs cannot reliably execute
on large component lists (RefDes matching, package verification, netlist integrity).

Target Rules:
- DFM_BOM_001: RefDes consistency across sources
- DFM_LIB_002: Footprint/package mismatch detection
- SCH_SYMBOL_001: Pin mapping consistency
- SCH_POL_001 / COMP_CAP_002: Voltage derating verification

All outputs are LLM-optimized JSON with precise paths: refdes, net_name, rule_id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data Classes for Structured Output
# ---------------------------------------------------------------------------

@dataclass
class Discrepancy:
    """A single cross-source discrepancy."""
    refdes: str
    rule_id: str
    details: str
    severity: str = "WARNING"
    source_a: str | None = None
    source_b: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageMismatch:
    """A footprint/package size mismatch between BOM and Board."""
    refdes: str
    bom_mpn: str | None
    bom_footprint: str | None
    bom_specified_package: str | None
    layout_footprint: str
    rule_id: str = "DFM_LIB_002"
    severity: str = "CRITICAL"
    issue: str = ""


@dataclass
class VoltageViolation:
    """A voltage derating margin violation."""
    refdes: str
    net_name: str
    operating_voltage: float
    bom_mpn: str | None
    component_type: str | None
    rated_voltage: float | None
    derating_achieved: float | None
    minimum_margin: float
    rule_id: str
    severity: str
    issue: str


@dataclass 
class NetlistDiscrepancy:
    """A netlist topology mismatch between Schematic and Board."""
    net_name: str
    rule_id: str = "SCH_NET_001"
    severity: str = "CRITICAL"
    issue: str = ""
    schematic_pins: list[str] = field(default_factory=list)
    board_pins: list[str] = field(default_factory=list)
    missing_in_board: list[str] = field(default_factory=list)
    extra_in_board: list[str] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    """Result of RefDes reconciliation across sources."""
    status: str = "PASS"
    bom_count: int = 0
    schematic_count: int = 0
    board_count: int = 0
    schematic_missing_from_bom: list[Discrepancy] = field(default_factory=list)
    bom_missing_from_schematic: list[Discrepancy] = field(default_factory=list)
    schematic_missing_from_board: list[Discrepancy] = field(default_factory=list)
    board_missing_from_schematic: list[Discrepancy] = field(default_factory=list)


@dataclass
class PackageCheckResult:
    """Result of package/footprint verification."""
    status: str = "PASS"
    mismatch_count: int = 0
    mismatches: list[PackageMismatch] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class NetlistCheckResult:
    """Result of netlist topology verification."""
    status: str = "PASS"
    discrepancy_count: int = 0
    discrepancies: list[NetlistDiscrepancy] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class DeratingCheckResult:
    """Result of voltage derating verification."""
    status: str = "PASS"
    violation_count: int = 0
    violations: list[VoltageViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisOutput:
    """Complete cross-check analysis output."""
    status: str = "PASS"
    bom_file: str | None = None
    sch_file: str | None = None
    brd_file: str | None = None
    evidence_limitations: list[str] = field(default_factory=list)
    refdes_reconciliation: ReconciliationResult | None = None
    package_mismatches: PackageCheckResult | None = None
    netlist_integrity: NetlistCheckResult | None = None
    voltage_derating: DeratingCheckResult | None = None


# ---------------------------------------------------------------------------
# Parser Classes
# ---------------------------------------------------------------------------

class BOMParser:
    """Parser for BOM JSON export files."""
    
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.items: list[dict[str, Any]] = []
        self.refdes_to_item: dict[str, dict[str, Any]] = {}
        self.all_refdes: set[str] = set()
        self.dnp_refdes: set[str] = set()
        self._parse()
    
    def _parse(self) -> None:
        """Parse BOM data into structured format."""
        raw_items = self.data.get("items", [])
        
        for raw in raw_items:
            fields = raw.get("fields", {})
            refdes_list = raw.get("refdes", [])
            is_dnp = fields.get("dnp", False)
            
            item = {
                "refdes": refdes_list,
                "value": fields.get("value"),
                "description": fields.get("description"),
                "manufacturer": fields.get("manufacturer"),
                "mpn": fields.get("mpn"),
                "footprint": fields.get("footprint"),
                "dnp": is_dnp,
                "raw": raw
            }
            
            self.items.append(item)
            
            for rd in refdes_list:
                self.all_refdes.add(rd)
                self.refdes_to_item[rd] = item
                if is_dnp:
                    self.dnp_refdes.add(rd)
    
    def get_item(self, refdes: str) -> dict[str, Any] | None:
        """Get BOM item by refdes."""
        return self.refdes_to_item.get(refdes)


class SchematicParser:
    """Parser for Schematic JSON export files."""
    
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.components: dict[str, dict[str, Any]] = {}
        self.nets: dict[str, dict[str, Any]] = {}
        self.net_to_pins: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
        self.pin_to_net: dict[str, str] = {}
        self.all_refdes: set[str] = set()
        self._parse()
    
    def _parse(self) -> None:
        """Parse schematic data."""
        for comp in self.data.get("components", []):
            refdes = comp.get("refdes")
            if refdes:
                self.components[refdes] = comp
                self.all_refdes.add(refdes)
        
        for net in self.data.get("nets", []):
            net_name = net.get("name")
            if not net_name:
                continue
            self.nets[net_name] = net
            
            for node in net.get("nodes", []):
                refdes = node.get("refdes")
                pin_num = str(node.get("pin_number", ""))
                pin_name = node.get("pin_name")
                
                if refdes and pin_num:
                    self.net_to_pins[net_name].append((refdes, pin_num, pin_name))
                    self.pin_to_net[f"{refdes}-{pin_num}"] = net_name


class BoardParser:
    """Parser for Board/Layout JSON export files."""
    
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.components: dict[str, dict[str, Any]] = {}
        self.nets: dict[str, dict[str, Any]] = {}
        self.net_to_pins: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.all_refdes: set[str] = set()
        self._parse()
    
    def _parse(self) -> None:
        """Parse board data."""
        # Parse components - check both 'components' and 'placements' keys
        comps = self.data.get("components", [])
        if not comps:
            comps = self.data.get("placements", [])
        
        for comp in comps:
            refdes = comp.get("refdes")
            if refdes:
                self.components[refdes] = comp
                self.all_refdes.add(refdes)
        
        # Parse nets if available
        for net in self.data.get("nets", []):
            net_name = net.get("name") or net.get("net_name")
            if not net_name:
                continue
            self.nets[net_name] = net
            
            # Extract pins - structure may vary
            nodes = net.get("nodes", []) or net.get("pins", [])
            for node in nodes:
                refdes = node.get("refdes") or node.get("component")
                pin = node.get("pin_number") or node.get("pin") or node.get("pad")
                if refdes and pin:
                    self.net_to_pins[net_name].append((refdes, str(pin)))
    
    def get_footprint(self, refdes: str) -> str | None:
        """Get footprint for a component."""
        comp = self.components.get(refdes)
        return comp.get("footprint") if comp else None


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------

def reconcile_refdes_sets(
    bom: BOMParser | None,
    sch: SchematicParser | None,
    brd: BoardParser | None
) -> ReconciliationResult:
    """
    Perform tripartite RefDes reconciliation.
    
    Computes:
    - S \ B: Schematic components missing from BOM
    - B \ S: BOM components missing from Schematic  
    - L \ S: Board footprints missing from Schematic
    - S \ L: Schematic components missing from Board (excl. DNP)
    """
    result = ReconciliationResult()
    
    B = bom.all_refdes if bom else set()
    S = sch.all_refdes if sch else set()
    L = brd.all_refdes if brd else set()
    DNP = bom.dnp_refdes if bom else set()
    
    result.bom_count = len(B)
    result.schematic_count = len(S)
    result.board_count = len(L)
    
    # S \ B: Schematic components missing from BOM
    sch_not_in_bom = S - B
    for rd in sorted(sch_not_in_bom):
        # Skip test points
        if rd.startswith("TP"):
            continue
        result.schematic_missing_from_bom.append(Discrepancy(
            refdes=rd,
            rule_id="DFM_BOM_001",
            details="Present in schematic netlist but absent from BOM. Component cannot be ordered.",
            severity="WARNING",
            source_a="schematic",
            source_b="bom"
        ))
    
    # B \ S: BOM components missing from Schematic
    bom_not_in_sch = B - S
    for rd in sorted(bom_not_in_sch):
        result.bom_missing_from_schematic.append(Discrepancy(
            refdes=rd,
            rule_id="DFM_BOM_001",
            details="Present in BOM but has no logical symbol or connection in schematic.",
            severity="WARNING",
            source_a="bom",
            source_b="schematic"
        ))
    
    # S \ L: Schematic components missing from Board (excluding DNP)
    sch_not_in_brd = S - L - DNP
    for rd in sorted(sch_not_in_brd):
        # Skip test points and fiducials
        if rd.startswith("TP") or rd.startswith("FID"):
            continue
        result.schematic_missing_from_board.append(Discrepancy(
            refdes=rd,
            rule_id="DFM_LIB_002",
            details="Placed and connected in schematic, but no physical footprint is placed on board layout.",
            severity="CRITICAL",
            source_a="schematic",
            source_b="board"
        ))
    
    # L \ S: Board footprints missing from Schematic
    brd_not_in_sch = L - S
    for rd in sorted(brd_not_in_sch):
        # Skip test points and fiducials
        if rd.startswith("TP") or rd.startswith("FID"):
            continue
        result.board_missing_from_schematic.append(Discrepancy(
            refdes=rd,
            rule_id="DFM_LIB_002",
            details="Footprint placed on board but no corresponding symbol exists in schematic.",
            severity="WARNING",
            source_a="board",
            source_b="schematic"
        ))
    
    # Determine status
    if (result.schematic_missing_from_bom or result.bom_missing_from_schematic or
        result.schematic_missing_from_board or result.board_missing_from_schematic):
        result.status = "FAIL"
    
    return result


def extract_package_size(text: str | None) -> str | None:
    """
    Extract package size code from footprint name, MPN, or description.
    Returns normalized size like '0402', '0603', 'QFN-16', 'SOIC-8', etc.
    """
    if not text:
        return None
    
    text = text.upper()
    
    # Common SMD passive sizes (Imperial)
    size_patterns = [
        r'\b(01005|0201|0402|0603|0805|1206|1210|1218|1812|2010|2512)\b',
    ]
    
    # Metric passive sizes
    metric_patterns = [
        r'\b(0201M|0402M|0603M|0805M|1005M|1206M|1608|2012|3216|3225|4532|5025|6332)\b',
    ]
    
    # IC package patterns
    ic_patterns = [
        r'\b(QFN-?\d+|DFN-?\d+|SOIC-?\d+|SOP-?\d+|TSSOP-?\d+|SSOP-?\d+|MSOP-?\d+)\b',
        r'\b(SOT-?\d+|SOT23-?\d*|SC70-?\d*|SC88|SOD-?\d+)\b',
        r'\b(BGA-?\d+|FBGA-?\d+|WLCSP-?\d+)\b',
        r'\b(TQFP-?\d+|LQFP-?\d+|QFP-?\d+|PLCC-?\d+)\b',
        r'\b(VSSOP-?\d+|DSBGA-?\d+)\b',
    ]
    
    # Try SMD sizes first
    for pattern in size_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    # Try metric sizes
    for pattern in metric_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    # Try IC packages
    for pattern in ic_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    return None


def normalize_package_size(size: str | None) -> str | None:
    """Normalize package size for comparison."""
    if not size:
        return None
    
    size = size.upper().replace("-", "").replace("_", "")
    
    # Map metric to imperial equivalents
    metric_to_imperial = {
        "1005": "0402",
        "1608": "0603",
        "2012": "0805",
        "3216": "1206",
        "3225": "1210",
    }
    
    if size in metric_to_imperial:
        return metric_to_imperial[size]
    
    return size


def check_package_mismatches(
    bom: BOMParser | None,
    brd: BoardParser | None
) -> PackageCheckResult:
    """
    Check for footprint/package mismatches between BOM and Board.
    
    Compares package sizes from BOM MPN/footprint fields against
    physical footprint names in the board layout.
    """
    result = PackageCheckResult()
    
    if not bom or not brd:
        result.notes.append("Missing BOM or Board data for package comparison")
        result.status = "SKIPPED"
        return result
    
    # Find common refdes
    common = bom.all_refdes & brd.all_refdes
    
    for rd in sorted(common):
        bom_item = bom.get_item(rd)
        brd_footprint = brd.get_footprint(rd)
        
        if not bom_item or not brd_footprint:
            continue
        
        # Extract BOM package info from MPN and footprint fields
        bom_mpn = bom_item.get("mpn")
        bom_footprint_field = bom_item.get("footprint")
        
        # Try to extract package size from BOM
        bom_pkg = extract_package_size(bom_mpn) or extract_package_size(bom_footprint_field)
        brd_pkg = extract_package_size(brd_footprint)
        
        if not bom_pkg or not brd_pkg:
            continue  # Can't compare without both
        
        # Normalize and compare
        bom_norm = normalize_package_size(bom_pkg)
        brd_norm = normalize_package_size(brd_pkg)
        
        if bom_norm != brd_norm:
            result.mismatches.append(PackageMismatch(
                refdes=rd,
                bom_mpn=bom_mpn,
                bom_footprint=bom_footprint_field,
                bom_specified_package=bom_pkg,
                layout_footprint=brd_footprint,
                issue=f"BOM specifies {bom_pkg} package but board layout uses {brd_pkg} footprint. Physical assembly may fail."
            ))
    
    result.mismatch_count = len(result.mismatches)
    if result.mismatches:
        result.status = "FAIL"
    
    return result


def verify_netlist_integrity(
    sch: SchematicParser | None,
    brd: BoardParser | None
) -> NetlistCheckResult:
    """
    Verify netlist topology matches between Schematic and Board.
    
    For each net, compare the set of connected pins in schematic vs board.
    Flag any missing or extra connections.
    """
    result = NetlistCheckResult()
    
    if not sch or not brd:
        result.notes.append("Missing Schematic or Board data for netlist verification")
        result.status = "SKIPPED"
        return result
    
    if not brd.nets:
        result.notes.append("Board JSON does not contain netlist data - cannot verify topology")
        result.status = "SKIPPED"
        return result
    
    # Compare nets that exist in both
    common_nets = set(sch.nets.keys()) & set(brd.nets.keys())
    
    for net_name in sorted(common_nets):
        # Get pins from each source
        sch_pins = set(f"{rd}-{pin}" for rd, pin, _ in sch.net_to_pins.get(net_name, []))
        brd_pins = set(f"{rd}-{pin}" for rd, pin in brd.net_to_pins.get(net_name, []))
        
        missing_in_board = sch_pins - brd_pins
        extra_in_board = brd_pins - sch_pins
        
        if missing_in_board or extra_in_board:
            disc = NetlistDiscrepancy(
                net_name=net_name,
                schematic_pins=sorted(sch_pins),
                board_pins=sorted(brd_pins),
                missing_in_board=sorted(missing_in_board),
                extra_in_board=sorted(extra_in_board)
            )
            
            if missing_in_board:
                disc.issue += f"Missing {len(missing_in_board)} connection(s) on board. "
            if extra_in_board:
                disc.issue += f"Extra {len(extra_in_board)} connection(s) on board. "
            
            result.discrepancies.append(disc)
    
    result.discrepancy_count = len(result.discrepancies)
    if result.discrepancies:
        result.status = "FAIL"
    
    return result


def extract_voltage_from_net_name(net_name: str) -> float | None:
    """
    Extract voltage value from power rail net names.
    
    Handles patterns like: VCC_5V, 12V_IN, 3.3V, +5V, -12V, VDD_1V8
    """
    if not net_name:
        return None
    
    net_upper = net_name.upper()
    
    # Skip ground nets
    if any(g in net_upper for g in ["GND", "VSS", "GROUND"]):
        return None
    
    # Patterns: 5V, 3.3V, 12V, 1.8V, etc.
    patterns = [
        r'(\d+\.?\d*)\s*V',        # 5V, 3.3V, 12V
        r'V(\d+\.?\d*)',           # V5, V12
        r'VCC_?(\d+\.?\d*)V?',     # VCC_5V, VCC5
        r'VDD_?(\d+\.?\d*)V?',     # VDD_3.3V
        r'(\d+)V(\d+)',            # 1V8 -> 1.8
    ]
    
    for pattern in patterns:
        match = re.search(pattern, net_upper)
        if match:
            groups = match.groups()
            if len(groups) == 2 and pattern == r'(\d+)V(\d+)':
                # Handle 1V8 format
                return float(f"{groups[0]}.{groups[1]}")
            elif groups[0]:
                try:
                    return float(groups[0])
                except ValueError:
                    continue
    
    return None


def extract_rated_voltage_from_mpn(mpn: str | None, desc: str | None) -> float | None:
    """
    Extract rated voltage from MPN or description.
    
    Common patterns:
    - GRM155R71H104KE14D: "1H" = 50V (Murata code)
    - Tantalum: T491A106K010AT: 010 = 10V
    - Electrolytic: often in description like "16V" or "25V"
    """
    if not mpn and not desc:
        return None
    
    text = f"{mpn or ''} {desc or ''}".upper()
    
    # Direct voltage patterns in description
    patterns = [
        r'(\d+\.?\d*)\s*V\s*(DC|RATED)?',
        r'RATED\s*(\d+\.?\d*)\s*V',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    
    # Murata MLCC voltage codes (in position 6-7 of MPN)
    if mpn and len(mpn) > 8 and mpn.startswith("GRM"):
        voltage_codes = {
            "0J": 6.3, "1A": 10, "1C": 16, "1E": 25, "1H": 50,
            "1J": 63, "2A": 100, "2E": 250, "3A": 1000
        }
        # Try to find voltage code
        for code, voltage in voltage_codes.items():
            if code in mpn[5:9]:
                return voltage
    
    # TDK voltage codes
    if mpn and "TDK" in text:
        tdk_codes = {"1C": 16, "1E": 25, "1H": 50, "2A": 100}
        for code, voltage in tdk_codes.items():
            if code in mpn:
                return voltage
    
    # Tantalum: last 3 digits before suffix often = voltage
    if "TANT" in text or "T491" in mpn.upper() if mpn else False:
        match = re.search(r'(\d{3})A?T', mpn.upper() if mpn else "")
        if match:
            try:
                return float(match.group(1).lstrip("0") or "0")
            except ValueError:
                pass
    
    return None


def is_polarized_capacitor(desc: str | None, mpn: str | None) -> tuple[bool, str | None]:
    """
    Check if a component is a polarized capacitor and return its type.
    
    Returns (is_polarized, type_string)
    """
    text = f"{desc or ''} {mpn or ''}".upper()
    
    if "TANT" in text or "T491" in text or "T495" in text:
        return True, "Tantalum"
    if "ALUM" in text and ("ELEC" in text or "CAP" in text):
        return True, "Aluminum Electrolytic"
    if "POLYMER" in text and "CAP" in text:
        return True, "Polymer"
    if "ELEC" in text and "CAP" in text:
        return True, "Electrolytic"
    
    return False, None


def verify_voltage_derating(
    sch: SchematicParser | None,
    bom: BOMParser | None
) -> DeratingCheckResult:
    """
    Verify voltage derating margins for capacitors.
    
    Rules:
    - Tantalum: 50% derating required (rated >= 2x operating)
    - Ceramic MLCC: 20% derating recommended
    - Aluminum Electrolytic: 20% derating recommended
    """
    result = DeratingCheckResult()
    
    if not sch or not bom:
        result.notes.append("Missing Schematic or BOM data for derating verification")
        result.status = "SKIPPED"
        return result
    
    # Build map of net -> operating voltage
    net_voltages: dict[str, float] = {}
    for net_name in sch.nets.keys():
        voltage = extract_voltage_from_net_name(net_name)
        if voltage is not None:
            net_voltages[net_name] = voltage
    
    if not net_voltages:
        result.notes.append("No power rail voltages detected from net names")
        result.status = "SKIPPED"
        return result
    
    # Check each capacitor
    for item in bom.items:
        desc = item.get("description", "")
        mpn = item.get("mpn", "")
        
        # Check if capacitor
        if not (desc and ("CAP" in desc.upper() or "C0" in str(item.get("footprint", "")).upper())):
            continue
        
        is_polarized, cap_type = is_polarized_capacitor(desc, mpn)
        rated_v = extract_rated_voltage_from_mpn(mpn, desc)
        
        if rated_v is None:
            continue
        
        # Find operating voltage from connected nets
        for rd in item.get("refdes", []):
            # Get nets this component is connected to
            for pin_key, net_name in sch.pin_to_net.items():
                if pin_key.startswith(f"{rd}-"):
                    operating_v = net_voltages.get(net_name)
                    if operating_v is None:
                        continue
                    
                    # Determine required margin
                    if is_polarized and cap_type == "Tantalum":
                        min_margin = 50.0  # 50% derating
                        rule_id = "SCH_POL_001"
                    else:
                        min_margin = 20.0  # 20% derating
                        rule_id = "COMP_CAP_002"
                    
                    # Calculate achieved margin
                    if rated_v > 0:
                        achieved = ((rated_v - operating_v) / rated_v) * 100
                    else:
                        achieved = -100
                    
                    # Check for violation
                    if achieved < min_margin:
                        severity = "CRITICAL" if achieved < 0 else "WARNING"
                        
                        if achieved < 0:
                            issue = f"{cap_type or 'Capacitor'} operating ABOVE rated voltage ({operating_v}V applied to {rated_v}V part). High failure risk."
                        else:
                            issue = f"{cap_type or 'Capacitor'} on {operating_v}V rail has only {achieved:.1f}% margin (requires {min_margin}% minimum)."
                        
                        result.violations.append(VoltageViolation(
                            refdes=rd,
                            net_name=net_name,
                            operating_voltage=operating_v,
                            bom_mpn=mpn,
                            component_type=cap_type or "Ceramic Capacitor",
                            rated_voltage=rated_v,
                            derating_achieved=achieved,
                            minimum_margin=min_margin,
                            rule_id=rule_id,
                            severity=severity,
                            issue=issue
                        ))
                        break  # One violation per component
    
    result.violation_count = len(result.violations)
    if result.violations:
        result.status = "FAIL"
    
    return result


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def discrepancy_to_dict(d: Discrepancy) -> dict[str, Any]:
    """Convert Discrepancy to dict."""
    result = {
        "refdes": d.refdes,
        "rule_id": d.rule_id,
        "details": d.details,
        "severity": d.severity,
    }
    if d.extra:
        result["extra"] = d.extra
    return result


def reconciliation_to_dict(r: ReconciliationResult) -> dict[str, Any]:
    """Convert ReconciliationResult to dict."""
    d: dict[str, Any] = {
        "status": r.status,
        "summary": {
            "bom_count": r.bom_count,
            "schematic_count": r.schematic_count,
            "board_count": r.board_count,
        },
        "discrepancies_found": r.status == "FAIL"
    }
    
    if r.schematic_missing_from_bom or r.bom_missing_from_schematic or \
       r.schematic_missing_from_board or r.board_missing_from_schematic:
        d["discrepancies"] = {}
        
        if r.schematic_missing_from_bom:
            d["discrepancies"]["schematic_missing_from_bom"] = [
                discrepancy_to_dict(x) for x in r.schematic_missing_from_bom
            ]
        if r.bom_missing_from_schematic:
            d["discrepancies"]["bom_missing_from_schematic"] = [
                discrepancy_to_dict(x) for x in r.bom_missing_from_schematic
            ]
        if r.schematic_missing_from_board:
            d["discrepancies"]["schematic_missing_from_board"] = [
                discrepancy_to_dict(x) for x in r.schematic_missing_from_board
            ]
        if r.board_missing_from_schematic:
            d["discrepancies"]["board_missing_from_schematic"] = [
                discrepancy_to_dict(x) for x in r.board_missing_from_schematic
            ]
    
    return d


def package_check_to_dict(r: PackageCheckResult) -> dict[str, Any]:
    """Convert PackageCheckResult to dict."""
    d: dict[str, Any] = {
        "status": r.status,
        "mismatch_count": r.mismatch_count,
    }
    
    if r.mismatches:
        d["mismatches"] = []
        for m in r.mismatches:
            d["mismatches"].append({
                "refdes": m.refdes,
                "bom_mpn": m.bom_mpn,
                "bom_specified_package": m.bom_specified_package,
                "layout_footprint_used": m.layout_footprint,
                "severity": m.severity,
                "issue": m.issue,
                "rule_id": m.rule_id,
            })
    
    if r.notes:
        d["notes"] = r.notes
    
    return d


def netlist_check_to_dict(r: NetlistCheckResult) -> dict[str, Any]:
    """Convert NetlistCheckResult to dict."""
    d: dict[str, Any] = {
        "status": r.status,
        "discrepancy_count": r.discrepancy_count,
    }
    
    if r.discrepancies:
        d["discrepancies"] = []
        for disc in r.discrepancies:
            d["discrepancies"].append({
                "net_name": disc.net_name,
                "rule_id": disc.rule_id,
                "severity": disc.severity,
                "issue": disc.issue,
                "missing_in_board": disc.missing_in_board,
                "extra_in_board": disc.extra_in_board,
            })
    
    if r.notes:
        d["notes"] = r.notes
    
    return d


def derating_check_to_dict(r: DeratingCheckResult) -> dict[str, Any]:
    """Convert DeratingCheckResult to dict."""
    d: dict[str, Any] = {
        "status": r.status,
        "violation_count": r.violation_count,
    }
    
    if r.violations:
        d["violations"] = []
        for v in r.violations:
            d["violations"].append({
                "refdes": v.refdes,
                "net_name": v.net_name,
                "operating_voltage": v.operating_voltage,
                "bom_mpn": v.bom_mpn,
                "component_type": v.component_type,
                "rated_voltage": v.rated_voltage,
                "derating_percentage_achieved": v.derating_achieved,
                "minimum_required_margin": v.minimum_margin,
                "severity": v.severity,
                "issue": v.issue,
                "rule_id": v.rule_id,
            })
    
    if r.notes:
        d["notes"] = r.notes
    
    return d


def format_output(output: AnalysisOutput, json_mode: bool) -> str:
    """Format output as JSON or human-readable text."""
    result: dict[str, Any] = {
        "status": output.status,
    }
    
    if output.bom_file:
        result["bom_file"] = output.bom_file
    if output.sch_file:
        result["sch_file"] = output.sch_file
    if output.brd_file:
        result["brd_file"] = output.brd_file
    
    if output.evidence_limitations:
        result["evidence_limitations"] = output.evidence_limitations
    
    if output.refdes_reconciliation:
        result["refdes_reconciliation"] = reconciliation_to_dict(output.refdes_reconciliation)
    
    if output.package_mismatches:
        result["package_mismatches"] = package_check_to_dict(output.package_mismatches)
    
    if output.netlist_integrity:
        result["netlist_integrity"] = netlist_check_to_dict(output.netlist_integrity)
    
    if output.voltage_derating:
        result["voltage_derating_violations"] = derating_check_to_dict(output.voltage_derating)
    
    if json_mode:
        return json.dumps(result, indent=2)
    
    # Human-readable format
    lines = []
    lines.append("=== Cross-Source Verification Report ===")
    lines.append(f"Status: {output.status}")
    
    if output.bom_file:
        lines.append(f"BOM: {output.bom_file}")
    if output.sch_file:
        lines.append(f"Schematic: {output.sch_file}")
    if output.brd_file:
        lines.append(f"Board: {output.brd_file}")
    lines.append("")
    
    if output.evidence_limitations:
        lines.append("Evidence Limitations:")
        for lim in output.evidence_limitations:
            lines.append(f"  - {lim}")
        lines.append("")
    
    if output.refdes_reconciliation:
        r = output.refdes_reconciliation
        lines.append(f"--- RefDes Reconciliation [{r.status}] ---")
        lines.append(f"  BOM: {r.bom_count} | Schematic: {r.schematic_count} | Board: {r.board_count}")
        
        if r.schematic_missing_from_bom:
            lines.append(f"  Schematic → BOM missing: {len(r.schematic_missing_from_bom)}")
            for d in r.schematic_missing_from_bom[:5]:
                lines.append(f"    {d.refdes}: {d.details}")
        if r.bom_missing_from_schematic:
            lines.append(f"  BOM → Schematic missing: {len(r.bom_missing_from_schematic)}")
            for d in r.bom_missing_from_schematic[:5]:
                lines.append(f"    {d.refdes}: {d.details}")
        if r.schematic_missing_from_board:
            lines.append(f"  Schematic → Board missing: {len(r.schematic_missing_from_board)}")
            for d in r.schematic_missing_from_board[:5]:
                lines.append(f"    {d.refdes}: {d.details}")
        if r.board_missing_from_schematic:
            lines.append(f"  Board → Schematic missing: {len(r.board_missing_from_schematic)}")
            for d in r.board_missing_from_schematic[:5]:
                lines.append(f"    {d.refdes}: {d.details}")
        lines.append("")
    
    if output.package_mismatches:
        r = output.package_mismatches
        lines.append(f"--- Package Mismatches [{r.status}] ---")
        lines.append(f"  Found: {r.mismatch_count}")
        for m in r.mismatches[:5]:
            lines.append(f"    {m.refdes}: {m.issue}")
        if r.notes:
            for n in r.notes:
                lines.append(f"  Note: {n}")
        lines.append("")
    
    if output.netlist_integrity:
        r = output.netlist_integrity
        lines.append(f"--- Netlist Integrity [{r.status}] ---")
        lines.append(f"  Discrepancies: {r.discrepancy_count}")
        for d in r.discrepancies[:5]:
            lines.append(f"    {d.net_name}: {d.issue}")
        if r.notes:
            for n in r.notes:
                lines.append(f"  Note: {n}")
        lines.append("")
    
    if output.voltage_derating:
        r = output.voltage_derating
        lines.append(f"--- Voltage Derating [{r.status}] ---")
        lines.append(f"  Violations: {r.violation_count}")
        for v in r.violations[:5]:
            lines.append(f"    {v.refdes} on {v.net_name}: {v.issue}")
        if r.notes:
            for n in r.notes:
                lines.append(f"  Note: {n}")
        lines.append("")
    
    lines.append("\n--- JSON Output ---")
    lines.append(json.dumps(result, indent=2))
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File Loading
# ---------------------------------------------------------------------------

def load_json_file(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """
    Load and parse a JSON file.
    Returns (data, error_message)
    """
    path = Path(path)
    
    if not path.exists():
        return None, f"File not found: {path}"
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {path}: {e}"
    except Exception as e:
        return None, f"Failed to read {path}: {e}"


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser_arg = argparse.ArgumentParser(
        description="ThomsonLint Cross-Source Verification Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cross_check_helpers.py --bom proj-bom.json --sch proj-sch.json --brd proj-brd.json --run-reconciliation --json
  python cross_check_helpers.py --bom proj-bom.json --brd proj-brd.json --check-packages
  python cross_check_helpers.py --bom proj-bom.json --sch proj-sch.json --verify-derating
        """
    )
    
    parser_arg.add_argument("--bom", help="Path to BOM JSON export file")
    parser_arg.add_argument("--sch", help="Path to Schematic JSON export file")
    parser_arg.add_argument("--brd", help="Path to Board/Layout JSON export file")
    parser_arg.add_argument("--run-reconciliation", action="store_true", 
                           help="Run RefDes reconciliation across all sources")
    parser_arg.add_argument("--check-packages", action="store_true",
                           help="Check footprint/package mismatches (DFM_LIB_002)")
    parser_arg.add_argument("--verify-netlist", action="store_true",
                           help="Verify netlist topology integrity (SCH_NET_001)")
    parser_arg.add_argument("--verify-derating", action="store_true",
                           help="Verify voltage derating margins (SCH_POL_001, COMP_CAP_002)")
    parser_arg.add_argument("--json", action="store_true",
                           help="Output pure JSON (no human-readable text)")
    
    args = parser_arg.parse_args()
    
    # Validate at least one input file provided
    if not any([args.bom, args.sch, args.brd]):
        error = {
            "status": "ERROR",
            "error": "At least one input file must be provided (--bom, --sch, or --brd)"
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Load input files
    output = AnalysisOutput()
    bom_parser: BOMParser | None = None
    sch_parser: SchematicParser | None = None
    brd_parser: BoardParser | None = None
    
    if args.bom:
        output.bom_file = args.bom
        data, err = load_json_file(args.bom)
        if err:
            output.evidence_limitations.append(f"BOM: {err}")
        elif data:
            try:
                bom_parser = BOMParser(data)
            except Exception as e:
                output.evidence_limitations.append(f"BOM parse error: {e}")
    
    if args.sch:
        output.sch_file = args.sch
        data, err = load_json_file(args.sch)
        if err:
            output.evidence_limitations.append(f"Schematic: {err}")
        elif data:
            try:
                sch_parser = SchematicParser(data)
            except Exception as e:
                output.evidence_limitations.append(f"Schematic parse error: {e}")
    
    if args.brd:
        output.brd_file = args.brd
        data, err = load_json_file(args.brd)
        if err:
            output.evidence_limitations.append(f"Board: {err}")
        elif data:
            try:
                brd_parser = BoardParser(data)
            except Exception as e:
                output.evidence_limitations.append(f"Board parse error: {e}")
    
    # Determine which checks to run
    run_all = not any([args.run_reconciliation, args.check_packages, 
                       args.verify_netlist, args.verify_derating])
    
    has_failures = False
    
    # Run RefDes reconciliation
    if args.run_reconciliation or run_all:
        output.refdes_reconciliation = reconcile_refdes_sets(bom_parser, sch_parser, brd_parser)
        if output.refdes_reconciliation.status == "FAIL":
            has_failures = True
    
    # Run package checks
    if args.check_packages or run_all:
        output.package_mismatches = check_package_mismatches(bom_parser, brd_parser)
        if output.package_mismatches.status == "FAIL":
            has_failures = True
    
    # Run netlist verification
    if args.verify_netlist or run_all:
        output.netlist_integrity = verify_netlist_integrity(sch_parser, brd_parser)
        if output.netlist_integrity.status == "FAIL":
            has_failures = True
    
    # Run voltage derating verification
    if args.verify_derating or run_all:
        output.voltage_derating = verify_voltage_derating(sch_parser, bom_parser)
        if output.voltage_derating.status == "FAIL":
            has_failures = True
    
    output.status = "FAIL" if has_failures else "PASS"
    
    print(format_output(output, args.json))
    sys.exit(0)  # Exit 0 even with violations - reserve non-zero for errors


if __name__ == "__main__":
    main()
