#!/usr/bin/env python3
"""ThomsonLint BOM Analysis Engine

Deterministic parsing and filtering of Bill of Materials (BOM) data for hardware design review.
Provides component-level analysis that LLMs cannot reliably perform (multi-key filtering,
numerical threshold checks, MPN suffix parsing, dielectric classification).

Target Rules:
- AERO_VIB_001: Heavy component detection (>3g threshold)
- COMP_CAP_001: Capacitor dielectric audit (Y5V/Y5U risk)
- DFM_BOM_001: Incomplete MPN audit
- AERO_SLD_001: Lead-finish assessment (tin-whisker risk)
- SCH_POL_001: Polarized capacitor identification

All outputs are LLM-optimized JSON with precise paths: refdes, mpn, description, rule_id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data Classes for Structured Output
# ---------------------------------------------------------------------------

@dataclass
class BOMItem:
    """Represents a single BOM line item with all relevant fields."""
    refdes: list[str]
    value: str | None
    description: str | None
    manufacturer: str | None
    mpn: str | None
    quantity: str | None
    footprint: str | None
    dnp: bool | None
    manufacturers: list[dict[str, Any]] = field(default_factory=list)
    custom_metadata: dict[str, Any] = field(default_factory=dict)
    mass_g: float | None = None  # Extracted/parsed mass in grams


@dataclass
class Violation:
    """A single rule violation with full citation."""
    rule_id: str
    refdes: list[str]
    mpn: str | None = None
    description: str | None = None
    issue: str = ""
    requirement: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """Result of a single check category."""
    status: str  # PASS, FAIL, WARNING, SKIPPED
    violation_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisOutput:
    """Complete analysis output structure."""
    status: str = "OK"
    bom_file: str = ""
    total_line_items: int = 0
    total_refdes_count: int = 0
    evidence_limitations: list[str] = field(default_factory=list)
    heavy_components: CheckResult | None = None
    capacitor_dielectric_warnings: CheckResult | None = None
    ordering_code_audit: CheckResult | None = None
    lead_finish_assessment: CheckResult | None = None
    polarized_capacitors: CheckResult | None = None


# ---------------------------------------------------------------------------
# BOM Parser
# ---------------------------------------------------------------------------

class BOMParser:
    """Parser for ThomsonLint BOM JSON exports."""
    
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.items: list[BOMItem] = []
        self._parse_items()
    
    def _parse_items(self) -> None:
        """Parse all BOM line items into structured objects."""
        raw_items = self.data.get("items", [])
        
        for raw in raw_items:
            fields = raw.get("fields", {})
            item = BOMItem(
                refdes=raw.get("refdes", []),
                value=fields.get("value"),
                description=fields.get("description"),
                manufacturer=fields.get("manufacturer"),
                mpn=fields.get("mpn"),
                quantity=fields.get("quantity"),
                footprint=fields.get("footprint"),
                dnp=fields.get("dnp"),
                manufacturers=raw.get("manufacturers", []),
                custom_metadata=raw.get("custom_metadata", {})
            )
            
            # Try to extract mass if present in custom_metadata or fields
            item.mass_g = self._extract_mass(raw)
            self.items.append(item)
    
    def _extract_mass(self, raw: dict[str, Any]) -> float | None:
        """Extract and normalize mass to grams from various possible fields."""
        # Check common field names for mass/weight
        mass_fields = ["mass", "weight", "mass_g", "weight_g", "mass_kg", "weight_kg"]
        
        # Check in fields
        fields = raw.get("fields", {})
        for mf in mass_fields:
            val = fields.get(mf)
            if val:
                return self._parse_mass_value(str(val))
        
        # Check in custom_metadata
        custom = raw.get("custom_metadata", {})
        for mf in mass_fields:
            val = custom.get(mf)
            if val:
                return self._parse_mass_value(str(val))
        
        # Check description for mass patterns
        desc = fields.get("description", "")
        if desc:
            mass = self._extract_mass_from_description(str(desc))
            if mass is not None:
                return mass
        
        return None
    
    def _parse_mass_value(self, val: str) -> float | None:
        """Parse a mass value string and normalize to grams."""
        val = val.strip().lower()
        
        # Pattern: number followed by optional unit
        match = re.match(r'([0-9.]+)\s*(mg|g|grams?|kg|oz|ounces?|lbs?|pounds?)?', val)
        if not match:
            return None
        
        try:
            num = float(match.group(1))
            unit = match.group(2) or "g"
            
            # Normalize to grams
            if unit in ["mg"]:
                return num / 1000.0
            elif unit in ["g", "gram", "grams"]:
                return num
            elif unit in ["kg"]:
                return num * 1000.0
            elif unit in ["oz", "ounce", "ounces"]:
                return num * 28.3495
            elif unit in ["lb", "lbs", "pound", "pounds"]:
                return num * 453.592
            else:
                return num
        except (ValueError, TypeError):
            return None
    
    def _extract_mass_from_description(self, desc: str) -> float | None:
        """Try to extract mass from component description."""
        desc_lower = desc.lower()
        
        # Common patterns: "1.5g", "150mg", "0.05oz"
        patterns = [
            r'(\d+\.?\d*)\s*(?:mg)',
            r'(\d+\.?\d*)\s*(?:g\b|grams?)',
            r'(\d+\.?\d*)\s*(?:oz|ounces?)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, desc_lower)
            if match:
                return self._parse_mass_value(match.group(0))
        
        return None
    
    def get_capacitors(self) -> list[BOMItem]:
        """Get all capacitor components."""
        capacitors = []
        for item in self.items:
            if self._is_capacitor(item):
                capacitors.append(item)
        return capacitors
    
    def _is_capacitor(self, item: BOMItem) -> bool:
        """Check if an item is a capacitor."""
        # Check refdes prefix
        for ref in item.refdes:
            if ref.upper().startswith("C") and ref[1:2].isdigit():
                return True
        
        # Check description
        desc = (item.description or "").upper()
        if any(kw in desc for kw in ["CAP_", "CAP ", "CAPACITOR", "CAP_CER", "CAP_TANT", "CAP_ELEC", "CAP_POLY"]):
            return True
        
        # Check footprint
        fp = (item.footprint or "").upper()
        if fp.startswith("C0") or fp.startswith("C1"):  # C0402, C0603, C0805, C1206, etc.
            return True
        
        return False
    
    def get_polarized_capacitors(self) -> list[BOMItem]:
        """Get polarized capacitors (tantalum, electrolytic, polymer)."""
        polarized = []
        polarized_keywords = ["TANT", "TANTALUM", "ELEC", "ELECTROLYTIC", "POLY", "POLYMER", "ALUM"]
        
        for item in self.get_capacitors():
            desc = (item.description or "").upper()
            value = (item.value or "").upper()
            
            for kw in polarized_keywords:
                if kw in desc or kw in value:
                    polarized.append(item)
                    break
        
        return polarized
    
    def get_all_items(self) -> list[BOMItem]:
        """Get all BOM items."""
        return self.items


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------

def filter_heavy_components(parser: BOMParser, threshold_g: float = 3.0) -> CheckResult:
    """AERO_VIB_001: Find components exceeding mass threshold.
    
    Heavy components require mechanical staking or structural support
    to prevent damage under vibration.
    """
    items_found: list[dict[str, Any]] = []
    notes: list[str] = []
    has_mass_data = False
    
    for item in parser.get_all_items():
        if item.mass_g is not None:
            has_mass_data = True
            if item.mass_g >= threshold_g:
                items_found.append({
                    "refdes": item.refdes,
                    "mpn": item.mpn,
                    "mass_g": item.mass_g,
                    "description": item.description,
                    "requirement": f"Requires physical staking/bonding support under AERO_VIB_001",
                    "rule_id": "AERO_VIB_001"
                })
    
    if not has_mass_data:
        notes.append("No mass/weight data found in BOM. Cannot assess heavy component risk.")
        return CheckResult(
            status="SKIPPED",
            violation_count=0,
            items=[],
            notes=notes
        )
    
    status = "WARNING" if items_found else "PASS"
    return CheckResult(
        status=status,
        violation_count=len(items_found),
        items=items_found,
        notes=[f"Checked {len(parser.items)} items against {threshold_g}g threshold"]
    )


def check_capacitor_dielectrics(parser: BOMParser) -> CheckResult:
    """COMP_CAP_001: Audit capacitor dielectrics for unstable Class II ceramics.
    
    Y5V and Y5U dielectrics have severe temperature-voltage derating and
    should be avoided in critical applications.
    """
    violations: list[Violation] = []
    notes: list[str] = []
    
    capacitors = parser.get_capacitors()
    if not capacitors:
        return CheckResult(status="SKIPPED", notes=["No capacitors found in BOM"])
    
    # Dielectric patterns
    dielectric_patterns = {
        "C0G": r'\bC0G\b|\bNP0\b|\bNPO\b',
        "X7R": r'\bX7R\b',
        "X5R": r'\bX5R\b',
        "X6S": r'\bX6S\b',
        "X7S": r'\bX7S\b',
        "Y5V": r'\bY5V\b',
        "Y5U": r'\bY5U\b',
        "Z5U": r'\bZ5U\b',
    }
    
    # Bad dielectrics with high risk
    bad_dielectrics = {"Y5V", "Y5U", "Z5U"}
    
    caps_with_dielectric = 0
    caps_without_dielectric = 0
    
    for cap in capacitors:
        # Check description and value for dielectric info
        text_to_search = f"{cap.description or ''} {cap.value or ''} {cap.custom_metadata.get('ITEM NAME', '')}"
        text_upper = text_to_search.upper()
        
        detected_dielectric = None
        for diel_name, pattern in dielectric_patterns.items():
            if re.search(pattern, text_upper, re.IGNORECASE):
                detected_dielectric = diel_name
                break
        
        if detected_dielectric:
            caps_with_dielectric += 1
            
            if detected_dielectric in bad_dielectrics:
                violations.append(Violation(
                    rule_id="COMP_CAP_001",
                    refdes=cap.refdes,
                    mpn=cap.mpn,
                    description=cap.description,
                    issue=f"Unstable Class II ceramic dielectric detected: {detected_dielectric}",
                    requirement="Replace with X7R or X5R dielectric for better stability",
                    details={
                        "dielectric_detected": detected_dielectric,
                        "risk": "Up to 80% capacitance loss at voltage/temperature limits",
                        "recommendation": f"Replace {detected_dielectric} with X7R or X5R dielectric"
                    }
                ))
        else:
            # Only flag as missing if it's a ceramic capacitor (CER in description)
            if "CER" in text_upper or "MLCC" in text_upper:
                caps_without_dielectric += 1
    
    notes.append(f"Analyzed {len(capacitors)} capacitors: {caps_with_dielectric} with dielectric info, {caps_without_dielectric} ceramic caps missing dielectric spec")
    
    if caps_without_dielectric > 0:
        notes.append(f"LIMITATION: {caps_without_dielectric} ceramic capacitors lack explicit dielectric specification")
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(
        status=status,
        violation_count=len(violations),
        violations=violations,
        notes=notes
    )


def audit_ordering_codes(parser: BOMParser) -> CheckResult:
    """DFM_BOM_001: Audit MPNs for incomplete or generic ordering codes.
    
    Flags generic series names that lack exact suffix codes for tolerance,
    voltage rating, packaging, or temperature coefficient.
    """
    violations: list[Violation] = []
    notes: list[str] = []
    
    # Patterns for incomplete MPNs
    generic_series_patterns = [
        r'^GRM\d{3}$',          # Murata GRM series without full code
        r'^RC\d{4}$',           # Generic RC series
        r'^ERJ-\d$',            # Panasonic ERJ without full code
        r'^CL\d{2}$',           # Samsung CL series without full code
        r'^\d{4}$',             # Just 4 digits (size only)
    ]
    
    # Placeholder patterns
    placeholder_patterns = [
        r'^\?+$',               # Just question marks
        r'^TBD$',               # TBD placeholder
        r'^N/?A$',              # N/A
        r'^GENERIC$',
        r'^UNKNOWN$',
    ]
    
    items_checked = 0
    
    for item in parser.get_all_items():
        # Skip non-component items (labels, PCB, etc.)
        if not item.refdes or all(r in ["", "1", "PCB1", "FAB1", "ASM1", "SCH1"] for r in item.refdes):
            continue
        
        # Skip DNP items
        if item.dnp:
            continue
        
        items_checked += 1
        mpn = item.mpn or ""
        mpn_stripped = mpn.strip()
        
        # Check for missing MPN
        if not mpn_stripped:
            violations.append(Violation(
                rule_id="DFM_BOM_001",
                refdes=item.refdes,
                mpn=None,
                description=item.description,
                issue="Missing manufacturer part number",
                requirement="Specify complete MPN for procurement",
                details={"error": "MPN field is empty or null"}
            ))
            continue
        
        # Check for placeholder values
        for pattern in placeholder_patterns:
            if re.match(pattern, mpn_stripped, re.IGNORECASE):
                violations.append(Violation(
                    rule_id="DFM_BOM_001",
                    refdes=item.refdes,
                    mpn=mpn,
                    description=item.description,
                    issue="Placeholder MPN detected",
                    requirement="Replace placeholder with actual manufacturer part number",
                    details={"error": f"MPN '{mpn}' appears to be a placeholder"}
                ))
                break
        
        # Check for incomplete series-only MPNs
        for pattern in generic_series_patterns:
            if re.match(pattern, mpn_stripped, re.IGNORECASE):
                violations.append(Violation(
                    rule_id="DFM_BOM_001",
                    refdes=item.refdes,
                    mpn=mpn,
                    description=item.description,
                    issue="Incomplete MPN - series name only",
                    requirement="Provide complete ordering code with tolerance, voltage, and packaging",
                    details={"error": f"MPN '{mpn}' is a generic series, not a complete ordering code"}
                ))
                break
    
    notes.append(f"Audited {items_checked} component MPNs")
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(
        status=status,
        violation_count=len(violations),
        violations=violations,
        notes=notes
    )


def analyze_lead_finish(parser: BOMParser) -> CheckResult:
    """AERO_SLD_001: Assess lead finish for tin-whisker risk.
    
    Identifies components with pure-tin or matte-tin terminations
    that carry high tin-whisker risk in aerospace/defense environments.
    """
    items_flagged: list[dict[str, Any]] = []
    notes: list[str] = []
    
    # MPN suffix patterns indicating lead finish
    # These are manufacturer-specific; this is a simplified heuristic
    tin_whisker_risk_patterns = [
        (r'-E$', "Matte tin termination (potential tin-whisker risk)"),
        (r'-E3$', "Lead-free matte tin (Vishay/ON Semi - tin-whisker risk)"),
        (r'NG$', "Sn-only plating (tin-whisker risk)"),
        (r'PBF$', "Lead-free (check for tin-whisker mitigation)"),
    ]
    
    # Safe finish patterns
    safe_finish_patterns = [
        (r'-PB$', "SnPb finish (tin-whisker safe)"),
        (r'-M3$', "SnPb or annealed tin (typically safe)"),
        (r'SNPB$', "SnPb finish"),
        (r'AU$', "Gold finish (safe)"),
        (r'-AU$', "Gold termination (safe)"),
    ]
    
    # Lead-free indicators in description
    lead_free_patterns = [r'\(LF\)', r'\bLF\b', r'LEAD.?FREE', r'ROHS']
    
    items_checked = 0
    lead_free_count = 0
    
    for item in parser.get_all_items():
        # Skip non-component items
        if not item.refdes or not item.mpn:
            continue
        if item.dnp:
            continue
        
        items_checked += 1
        mpn_upper = item.mpn.upper()
        desc_upper = (item.description or "").upper()
        
        # Check for lead-free indicators
        is_lead_free = any(re.search(p, desc_upper) for p in lead_free_patterns)
        if is_lead_free:
            lead_free_count += 1
        
        # Check MPN suffixes for tin-whisker risk
        finish_note = None
        is_risky = False
        
        for pattern, note in tin_whisker_risk_patterns:
            if re.search(pattern, mpn_upper):
                finish_note = note
                is_risky = True
                break
        
        if not finish_note:
            for pattern, note in safe_finish_patterns:
                if re.search(pattern, mpn_upper):
                    finish_note = note
                    break
        
        # Flag items with detected tin-whisker risk
        if is_risky:
            items_flagged.append({
                "refdes": item.refdes,
                "mpn": item.mpn,
                "description": item.description,
                "lead_finish_indicator": finish_note,
                "risk": "Tin-whisker risk in aerospace/defense environments",
                "mitigation": "Verify nickel underplate or annealing treatment, or specify SnPb finish",
                "rule_id": "AERO_SLD_001"
            })
    
    notes.append(f"Checked {items_checked} components for lead finish indicators")
    notes.append(f"Found {lead_free_count} components with lead-free indicators")
    
    if not items_flagged:
        notes.append("No explicit tin-whisker risk indicators detected in MPNs")
        notes.append("LIMITATION: Lead finish often requires datasheet verification")
    
    status = "WARNING" if items_flagged else "PASS"
    return CheckResult(
        status=status,
        violation_count=len(items_flagged),
        items=items_flagged,
        notes=notes
    )


def identify_polarized_capacitors(parser: BOMParser) -> CheckResult:
    """SCH_POL_001: Identify polarized capacitors for voltage derating cross-check.
    
    Extracts tantalum, electrolytic, and polymer capacitors with their
    voltage ratings for downstream schematic operating margin verification.
    """
    items_found: list[dict[str, Any]] = []
    notes: list[str] = []
    
    polarized = parser.get_polarized_capacitors()
    
    if not polarized:
        return CheckResult(
            status="PASS",
            notes=["No polarized capacitors (tantalum, electrolytic, polymer) found in BOM"]
        )
    
    for cap in polarized:
        desc = (cap.description or "").upper()
        value = cap.value or ""
        
        # Determine capacitor type
        cap_type = "Unknown Polarized"
        if "TANT" in desc:
            cap_type = "Tantalum"
            derating_rule = "50% voltage derating required"
        elif "ELEC" in desc or "ALUM" in desc:
            cap_type = "Aluminum Electrolytic"
            derating_rule = "20% voltage derating recommended"
        elif "POLY" in desc:
            cap_type = "Polymer"
            derating_rule = "20% voltage derating recommended"
        else:
            derating_rule = "Verify polarized capacitor voltage derating"
        
        # Try to extract voltage rating from description
        voltage_match = re.search(r'(\d+\.?\d*)\s*V', desc)
        voltage_rating = voltage_match.group(1) + "V" if voltage_match else "Unknown"
        
        # Try to extract capacitance
        cap_match = re.search(r'(\d+\.?\d*)\s*(UF|MF|PF|NF)', desc)
        capacitance = cap_match.group(0) if cap_match else value
        
        items_found.append({
            "refdes": cap.refdes,
            "mpn": cap.mpn,
            "description": cap.description,
            "capacitor_type": cap_type,
            "voltage_rating": voltage_rating,
            "capacitance": capacitance,
            "derating_requirement": derating_rule,
            "rule_id": "SCH_POL_001"
        })
    
    notes.append(f"Found {len(items_found)} polarized capacitors requiring voltage derating verification")
    
    return CheckResult(
        status="PASS",  # This is informational, not a failure
        violation_count=0,
        items=items_found,
        notes=notes
    )


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def violation_to_dict(v: Violation) -> dict[str, Any]:
    """Convert Violation to JSON-serializable dict."""
    d: dict[str, Any] = {
        "rule_id": v.rule_id,
        "refdes": v.refdes,
        "issue": v.issue,
    }
    if v.mpn:
        d["mpn"] = v.mpn
    if v.description:
        d["description"] = v.description
    if v.requirement:
        d["requirement"] = v.requirement
    if v.details:
        d.update(v.details)
    return d


def check_result_to_dict(cr: CheckResult, include_items: bool = True) -> dict[str, Any]:
    """Convert CheckResult to JSON-serializable dict."""
    d: dict[str, Any] = {
        "status": cr.status,
        "violation_count": cr.violation_count,
    }
    
    if cr.violations:
        d["violations"] = [violation_to_dict(v) for v in cr.violations]
    
    if include_items and cr.items:
        d["items"] = cr.items
    
    if cr.notes:
        d["notes"] = cr.notes
    
    return d


def format_output(output: AnalysisOutput, json_mode: bool) -> str:
    """Format output as JSON or human-readable text."""
    result: dict[str, Any] = {
        "status": output.status,
        "bom_file": output.bom_file,
        "total_line_items": output.total_line_items,
        "total_refdes_count": output.total_refdes_count,
    }
    
    if output.evidence_limitations:
        result["evidence_limitations"] = output.evidence_limitations
    
    if output.heavy_components:
        result["heavy_components"] = check_result_to_dict(output.heavy_components)
    
    if output.capacitor_dielectric_warnings:
        result["capacitor_dielectric_warnings"] = check_result_to_dict(output.capacitor_dielectric_warnings)
    
    if output.ordering_code_audit:
        result["ordering_code_audit"] = check_result_to_dict(output.ordering_code_audit)
    
    if output.lead_finish_assessment:
        result["lead_finish_assessment"] = check_result_to_dict(output.lead_finish_assessment)
    
    if output.polarized_capacitors:
        result["polarized_capacitors"] = check_result_to_dict(output.polarized_capacitors)
    
    if json_mode:
        return json.dumps(result, indent=2)
    
    # Human-readable format
    lines = []
    lines.append(f"=== BOM Analysis: {output.bom_file} ===")
    lines.append(f"Status: {output.status}")
    lines.append(f"Total Line Items: {output.total_line_items}")
    lines.append(f"Total RefDes Count: {output.total_refdes_count}")
    lines.append("")
    
    if output.evidence_limitations:
        lines.append("Evidence Limitations:")
        for lim in output.evidence_limitations:
            lines.append(f"  - {lim}")
        lines.append("")
    
    def format_check(name: str, cr: CheckResult | None):
        if not cr:
            return
        lines.append(f"--- {name} [{cr.status}] ---")
        if cr.notes:
            for n in cr.notes:
                lines.append(f"  Note: {n}")
        if cr.violations:
            lines.append(f"  Violations: {cr.violation_count}")
            for v in cr.violations[:10]:
                lines.append(f"    [{v.rule_id}] {v.issue}")
                if v.refdes:
                    lines.append(f"      RefDes: {', '.join(v.refdes)}")
                if v.mpn:
                    lines.append(f"      MPN: {v.mpn}")
            if len(cr.violations) > 10:
                lines.append(f"    ... and {len(cr.violations) - 10} more")
        if cr.items:
            lines.append(f"  Items: {len(cr.items)}")
            for item in cr.items[:5]:
                lines.append(f"    - {item.get('refdes', [])} | {item.get('mpn', 'N/A')}")
            if len(cr.items) > 5:
                lines.append(f"    ... and {len(cr.items) - 5} more")
        lines.append("")
    
    format_check("Heavy Components (AERO_VIB_001)", output.heavy_components)
    format_check("Capacitor Dielectrics (COMP_CAP_001)", output.capacitor_dielectric_warnings)
    format_check("Ordering Code Audit (DFM_BOM_001)", output.ordering_code_audit)
    format_check("Lead Finish Assessment (AERO_SLD_001)", output.lead_finish_assessment)
    format_check("Polarized Capacitors (SCH_POL_001)", output.polarized_capacitors)
    
    # Append JSON block for easy parsing
    lines.append("=== JSON Output ===")
    lines.append(json.dumps(result, indent=2))
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser_arg = argparse.ArgumentParser(
        description="ThomsonLint BOM Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bom_helpers.py exports/project-bom.json --audit-components --json
  python bom_helpers.py exports/project-bom.json --heavy-threshold 3.0
  python bom_helpers.py exports/project-bom.json --check-dielectrics --audit-mpns
        """
    )
    
    parser_arg.add_argument("bom_json", help="Path to BOM JSON export file")
    parser_arg.add_argument("--audit-components", action="store_true", help="Run all component checks")
    parser_arg.add_argument("--heavy-threshold", type=float, default=3.0, 
                           help="Mass threshold in grams for heavy component flagging (default: 3.0)")
    parser_arg.add_argument("--check-dielectrics", action="store_true", help="Audit capacitor dielectrics (COMP_CAP_001)")
    parser_arg.add_argument("--audit-mpns", action="store_true", help="Audit ordering codes (DFM_BOM_001)")
    parser_arg.add_argument("--check-lead-finish", action="store_true", help="Assess lead finish for tin-whisker risk (AERO_SLD_001)")
    parser_arg.add_argument("--polarized", action="store_true", help="Identify polarized capacitors (SCH_POL_001)")
    parser_arg.add_argument("--json", action="store_true", help="Output pure JSON (no human-readable text)")
    
    args = parser_arg.parse_args()
    
    # Validate input file
    bom_path = Path(args.bom_json)
    if not bom_path.exists():
        error = {
            "status": "ERROR",
            "error": f"BOM file not found: {args.bom_json}",
            "bom_file": str(bom_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Load JSON
    try:
        with open(bom_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        error = {
            "status": "ERROR",
            "error": f"Invalid JSON: {e}",
            "bom_file": str(bom_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = {
            "status": "ERROR",
            "error": f"Failed to read file: {e}",
            "bom_file": str(bom_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Build parser
    output = AnalysisOutput(bom_file=str(bom_path))
    
    try:
        bom_parser = BOMParser(data)
    except Exception as e:
        output.status = "ERROR"
        output.evidence_limitations.append(f"Failed to parse BOM: {e}")
        print(format_output(output, args.json))
        sys.exit(1)
    
    # Record basic stats
    output.total_line_items = len(bom_parser.items)
    output.total_refdes_count = sum(len(item.refdes) for item in bom_parser.items)
    
    # Check for schema limitations
    if not data.get("items"):
        output.evidence_limitations.append("No 'items' array found in BOM JSON")
    
    # Determine which checks to run
    run_all = args.audit_components
    run_heavy = run_all  # Heavy always runs with audit-components
    run_dielectrics = args.check_dielectrics or run_all
    run_mpns = args.audit_mpns or run_all
    run_lead = args.check_lead_finish or run_all
    run_polarized = args.polarized or run_all
    
    # If no specific check requested and not --audit-components, default to all
    if not any([args.check_dielectrics, args.audit_mpns, args.check_lead_finish, 
                args.polarized, args.audit_components]):
        run_heavy = run_dielectrics = run_mpns = run_lead = run_polarized = True
    
    # Run analyses
    has_failures = False
    
    if run_heavy:
        output.heavy_components = filter_heavy_components(bom_parser, args.heavy_threshold)
        if output.heavy_components.status == "FAIL":
            has_failures = True
    
    if run_dielectrics:
        output.capacitor_dielectric_warnings = check_capacitor_dielectrics(bom_parser)
        if output.capacitor_dielectric_warnings.status == "FAIL":
            has_failures = True
    
    if run_mpns:
        output.ordering_code_audit = audit_ordering_codes(bom_parser)
        if output.ordering_code_audit.status == "FAIL":
            has_failures = True
    
    if run_lead:
        output.lead_finish_assessment = analyze_lead_finish(bom_parser)
        if output.lead_finish_assessment.status == "FAIL":
            has_failures = True
    
    if run_polarized:
        output.polarized_capacitors = identify_polarized_capacitors(bom_parser)
        if output.polarized_capacitors.status == "FAIL":
            has_failures = True
    
    # Collect evidence limitations
    if run_heavy and output.heavy_components and output.heavy_components.status == "SKIPPED":
        output.evidence_limitations.append("No mass/weight data available for heavy component analysis")
    
    output.status = "FAIL" if has_failures else "PASS"
    
    print(format_output(output, args.json))
    sys.exit(0)  # Exit 0 even with violations - reserve non-zero for errors


if __name__ == "__main__":
    main()
