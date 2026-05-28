#!/usr/bin/env python3
"""ThomsonLint Schematic Analysis Engine

Deterministic structural parsing of schematic JSON exports for hardware design review.
Provides graph-based analysis that LLMs cannot reliably perform (multi-hop pathfinding,
bus topology analysis, pin counting, net connectivity tracing).

Target Rules:
- SCH_NET_002: Single-pin net detection
- SCH_UART_001: UART TX/RX crossover validation  
- SCH_FET_001: FET gate active termination
- SCH_FLOAT_001: Floating digital input detection
- MS_I2C_001: I2C bus pull-up validation
- SCH_I2C_002: I2C address conflict detection
- AN_OPAMP_002 / SCH_PULLUP_001: Unused op-amp tie-off

All outputs are LLM-optimized JSON with precise paths: refdes, pin_number, pin_name, net_name, rule_id.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data Classes for Structured Output
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """A single rule violation with full citation."""
    rule_id: str
    refdes: str | None = None
    pin_number: str | None = None
    pin_name: str | None = None
    net_name: str | None = None
    component_value: str | None = None
    issue: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """Result of a single check category."""
    status: str  # PASS, FAIL, SKIPPED, ERROR
    violation_count: int = 0
    violations: list[Violation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class I2CBusAnalysis:
    """Analysis of a single I2C bus."""
    bus_id: str
    sda_net: str | None = None
    scl_net: str | None = None
    pullups_detected: dict[str, bool] = field(default_factory=dict)
    address_conflicts: list[dict[str, Any]] = field(default_factory=list)
    components_on_bus: list[str] = field(default_factory=list)
    rule_violations: list[str] = field(default_factory=list)


@dataclass
class AnalysisOutput:
    """Complete analysis output structure."""
    status: str = "OK"
    schematic_file: str = ""
    conversion_limitations: list[str] = field(default_factory=list)
    single_pin_nets: CheckResult | None = None
    uart_crossover: CheckResult | None = None
    fet_gate_terminations: CheckResult | None = None
    floating_inputs: CheckResult | None = None
    i2c_bus_analysis: dict[str, Any] | None = None
    opamp_tieoff: CheckResult | None = None


# ---------------------------------------------------------------------------
# Schematic Graph Builder
# ---------------------------------------------------------------------------

class SchematicGraph:
    """In-memory graph representation of schematic connectivity."""
    
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.components: dict[str, dict[str, Any]] = {}  # refdes -> component dict
        self.nets: dict[str, dict[str, Any]] = {}  # net_name -> net dict
        self.net_to_pins: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)  # net -> [(refdes, pin_num, pin_name), ...]
        self.pin_to_net: dict[str, str] = {}  # "refdes-pin_num" -> net_name
        self.component_pins: dict[str, list[tuple[str, str | None, str | None]]] = defaultdict(list)  # refdes -> [(pin_num, pin_name, net), ...]
        
        self._build_graph()
    
    def _build_graph(self) -> None:
        """Build internal graph structures from raw data."""
        # Index components by refdes
        for comp in self.data.get("components", []):
            refdes = comp.get("refdes")
            if refdes:
                self.components[refdes] = comp
        
        # Index nets and build connectivity maps
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
                    self.component_pins[refdes].append((pin_num, pin_name, net_name))
    
    def get_net_node_count(self, net_name: str) -> int:
        """Get the number of unique pins connected to a net."""
        return len(self.net_to_pins.get(net_name, []))
    
    def get_component(self, refdes: str) -> dict[str, Any] | None:
        """Get component data by refdes."""
        return self.components.get(refdes)
    
    def get_net_pins(self, net_name: str) -> list[tuple[str, str, str | None]]:
        """Get all pins connected to a net as (refdes, pin_num, pin_name)."""
        return self.net_to_pins.get(net_name, [])
    
    def get_nets_by_pattern(self, pattern: str, case_sensitive: bool = False) -> list[str]:
        """Find nets matching a regex pattern."""
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
        return [n for n in self.nets.keys() if regex.search(n)]
    
    def find_components_by_type(self, type_patterns: list[str]) -> list[str]:
        """Find component refdes matching type patterns in description or value."""
        matches = []
        for refdes, comp in self.components.items():
            value = str(comp.get("value", "")).upper()
            desc = str(comp.get("bom", {}).get("description", "")).upper()
            
            for pattern in type_patterns:
                pattern_upper = pattern.upper()
                if pattern_upper in value or pattern_upper in desc:
                    matches.append(refdes)
                    break
        return matches
    
    def find_resistors_on_net(self, net_name: str) -> list[tuple[str, str]]:
        """Find all resistors connected to a net, returning (refdes, value)."""
        resistors = []
        for refdes, pin_num, pin_name in self.net_to_pins.get(net_name, []):
            if refdes.upper().startswith("R"):
                comp = self.components.get(refdes, {})
                value = comp.get("value", "")
                resistors.append((refdes, value))
        return resistors
    
    def trace_through_resistor(self, resistor_refdes: str, from_net: str) -> str | None:
        """Find the other net connected to a resistor (opposite of from_net)."""
        for pin_num, pin_name, net_name in self.component_pins.get(resistor_refdes, []):
            if net_name and net_name != from_net:
                return net_name
        return None
    
    def is_power_or_ground_net(self, net_name: str) -> bool:
        """Check if a net is a power or ground reference."""
        name_upper = net_name.upper()
        power_patterns = [
            r'^V[CDS][CDS]', r'^GND', r'^GROUND', r'^VSS', r'^VEE', 
            r'^AGND', r'^DGND', r'^PGND', r'^SGND',
            r'^\+\d+V', r'^\-\d+V', r'^[0-9]+V[0-9]*$',
            r'^PWR', r'^POWER', r'^VIN', r'^VOUT', r'^VBUS',
            r'^3V3', r'^5V', r'^12V', r'^1V8', r'^2V5'
        ]
        for pattern in power_patterns:
            if re.search(pattern, name_upper):
                return True
        return False


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------

def find_single_pin_nets(graph: SchematicGraph) -> CheckResult:
    """SCH_NET_002: Find nets with exactly one pin connection.
    
    Excludes:
    - Test points (refdes starting with TP)
    - Net names containing TP_ or NC
    - Power/ground nets
    """
    violations = []
    notes = []
    
    for net_name, net_data in graph.nets.items():
        node_count = net_data.get("node_count", 0)
        pins = graph.net_to_pins.get(net_name, [])
        actual_count = len(pins)
        
        # Use actual pin count if node_count doesn't match
        count = actual_count if actual_count != node_count else node_count
        
        if count != 1:
            continue
        
        # Check if this is a valid single-pin net to flag
        net_upper = net_name.upper()
        
        # Skip NC (No Connect) nets
        if "NC" in net_upper or net_upper.startswith("NC_"):
            continue
        
        # Skip test point nets
        if "TP_" in net_upper:
            continue
        
        # Skip power/ground
        if graph.is_power_or_ground_net(net_name):
            continue
        
        # Check if the single pin is a test point component
        if pins:
            refdes, pin_num, pin_name = pins[0]
            if refdes.upper().startswith("TP"):
                continue
            
            comp = graph.get_component(refdes)
            comp_value = comp.get("value", "") if comp else ""
            
            violations.append(Violation(
                rule_id="SCH_NET_002",
                refdes=refdes,
                pin_number=pin_num,
                pin_name=pin_name,
                net_name=net_name,
                component_value=comp_value,
                issue=f"Single-pin net: only connected to {refdes}-{pin_num}",
                details={"connected_pin": f"{refdes}-{pin_num} ({pin_name or 'unnamed'})"}
            ))
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(status=status, violation_count=len(violations), violations=violations, notes=notes)


def check_uart_crossover(graph: SchematicGraph) -> CheckResult:
    """SCH_UART_001: Verify UART TX/RX crossover connections.
    
    Finds TX/RX signal pairs and validates proper crossover.
    Flags TX-to-TX or RX-to-RX connections.
    """
    violations = []
    notes = []
    
    # Find all TX and RX nets
    tx_nets = graph.get_nets_by_pattern(r'(TX|TXD)[0-9_]*$')
    rx_nets = graph.get_nets_by_pattern(r'(RX|RXD)[0-9_]*$')
    
    if not tx_nets and not rx_nets:
        return CheckResult(status="SKIPPED", notes=["No UART TX/RX nets detected"])
    
    # Also find TX/RX by pin names
    tx_pins_by_net: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    rx_pins_by_net: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    
    for net_name, pins in graph.net_to_pins.items():
        for refdes, pin_num, pin_name in pins:
            if not pin_name:
                continue
            pin_upper = pin_name.upper()
            if re.search(r'\bTX[D]?\b', pin_upper):
                tx_pins_by_net[net_name].append((refdes, pin_num, pin_name))
            elif re.search(r'\bRX[D]?\b', pin_upper):
                rx_pins_by_net[net_name].append((refdes, pin_num, pin_name))
    
    # Check for improper same-type connections
    for net_name, tx_pins in tx_pins_by_net.items():
        if len(tx_pins) >= 2:
            # Multiple TX pins on same net - potential issue
            refdes_list = [f"{r}-{p}" for r, p, _ in tx_pins]
            violations.append(Violation(
                rule_id="SCH_UART_001",
                net_name=net_name,
                issue=f"Multiple TX pins connected together without crossover",
                details={"tx_pins": refdes_list}
            ))
    
    for net_name, rx_pins in rx_pins_by_net.items():
        if len(rx_pins) >= 2:
            # Multiple RX pins on same net - potential issue (unless bus)
            refdes_list = [f"{r}-{p}" for r, p, _ in rx_pins]
            violations.append(Violation(
                rule_id="SCH_UART_001",
                net_name=net_name,
                issue=f"Multiple RX pins connected together without crossover",
                details={"rx_pins": refdes_list}
            ))
    
    # Report found UART interfaces for verification
    if tx_pins_by_net or rx_pins_by_net:
        notes.append(f"Found {len(tx_pins_by_net)} nets with TX pins, {len(rx_pins_by_net)} nets with RX pins")
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(status=status, violation_count=len(violations), violations=violations, notes=notes)


def verify_fet_gate_termination(graph: SchematicGraph) -> CheckResult:
    """SCH_FET_001: Verify FET gates have defined state at startup.
    
    MOSFET gates must have a resistor to a defined rail (pull-up or pull-down)
    to prevent floating gate during startup or high-Z driver states.
    """
    violations = []
    notes = []
    
    # Find FET/MOSFET components
    fet_types = ["FET", "MOSFET", "BSS138", "BSS84", "SI2301", "SI2302", "AO3400", "AO3401", "FDS", "IRF", "2N7002"]
    fets = graph.find_components_by_type(fet_types)
    
    # Also find Q-prefixed components that might be FETs
    for refdes in graph.components:
        if refdes.upper().startswith("Q") and refdes not in fets:
            comp = graph.components[refdes]
            desc = str(comp.get("bom", {}).get("description", "")).upper()
            if "MOSFET" in desc or "FET" in desc:
                fets.append(refdes)
    
    if not fets:
        return CheckResult(status="SKIPPED", notes=["No FET/MOSFET components detected"])
    
    notes.append(f"Analyzing {len(fets)} FET components: {', '.join(fets[:10])}")
    
    for refdes in fets:
        comp = graph.components.get(refdes, {})
        pins = graph.component_pins.get(refdes, [])
        
        # Find gate pin (usually pin 1, or named G/GATE)
        gate_net = None
        gate_pin = None
        for pin_num, pin_name, net_name in pins:
            pin_name_upper = (pin_name or "").upper()
            if pin_name_upper in ["G", "GATE"] or (pin_num == "1" and not gate_net):
                gate_net = net_name
                gate_pin = pin_num
        
        if not gate_net:
            notes.append(f"Could not identify gate pin for {refdes}")
            continue
        
        # Check if gate net has a resistor path to power/ground
        resistors = graph.find_resistors_on_net(gate_net)
        
        has_termination = False
        for res_refdes, res_value in resistors:
            # Check if resistor goes to power/ground
            other_net = graph.trace_through_resistor(res_refdes, gate_net)
            if other_net and graph.is_power_or_ground_net(other_net):
                has_termination = True
                break
        
        if not has_termination:
            comp_value = comp.get("value", "")
            violations.append(Violation(
                rule_id="SCH_FET_001",
                refdes=refdes,
                pin_number=gate_pin,
                pin_name="GATE",
                net_name=gate_net,
                component_value=comp_value,
                issue="No pull-up or pull-down resistor detected on high-impedance gate net",
                details={
                    "gate_pin": f"{refdes}-{gate_pin}",
                    "resistors_on_net": [r[0] for r in resistors]
                }
            ))
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(status=status, violation_count=len(violations), violations=violations, notes=notes)


def find_floating_inputs(graph: SchematicGraph) -> CheckResult:
    """SCH_FLOAT_001: Detect floating digital/ADC inputs.
    
    Identifies IC input pins that are connected to:
    - Single-pin nets (no driver)
    - Nets with no output/bidirectional pins and no pull-up/down
    """
    violations = []
    notes = []
    
    # Input pin patterns
    input_patterns = [
        r'^EN$', r'^ENABLE$', r'^RST$', r'^RESET$', r'^nRST$', r'^nRESET$',
        r'^SEL[0-9]*$', r'^SELECT', r'^IN[0-9]*$', r'^INPUT',
        r'^A[0-9]+$',  # Address pins
        r'^D[0-9]+$',  # Data pins (could be bidirectional)
        r'^GPIO', r'^ADC', r'^AIN'
    ]
    
    # Find ICs (U-prefix components)
    ics = [r for r in graph.components if r.upper().startswith("U")]
    
    if not ics:
        return CheckResult(status="SKIPPED", notes=["No IC components (U-prefix) detected"])
    
    for ic_refdes in ics:
        pins = graph.component_pins.get(ic_refdes, [])
        
        for pin_num, pin_name, net_name in pins:
            if not pin_name or not net_name:
                continue
            
            # Check if this looks like an input pin
            is_input = False
            for pattern in input_patterns:
                if re.match(pattern, pin_name.upper()):
                    is_input = True
                    break
            
            if not is_input:
                continue
            
            # Skip power/ground pins
            if graph.is_power_or_ground_net(net_name):
                continue
            
            # Check if net has only this pin (single-pin net)
            net_pins = graph.get_net_pins(net_name)
            if len(net_pins) == 1:
                violations.append(Violation(
                    rule_id="SCH_FLOAT_001",
                    refdes=ic_refdes,
                    pin_number=pin_num,
                    pin_name=pin_name,
                    net_name=net_name,
                    issue="Input pin connected to single-pin net (no driver)",
                    details={"net_node_count": 1}
                ))
                continue
            
            # Check if net has any resistors to power/ground (pull-up/down)
            resistors = graph.find_resistors_on_net(net_name)
            has_pullup_down = False
            for res_refdes, res_value in resistors:
                other_net = graph.trace_through_resistor(res_refdes, net_name)
                if other_net and graph.is_power_or_ground_net(other_net):
                    has_pullup_down = True
                    break
            
            # Check if any non-IC, non-resistor component drives this net
            has_driver = False
            for other_refdes, other_pin, other_pin_name in net_pins:
                if other_refdes == ic_refdes:
                    continue
                # Connectors and headers can be drivers (external source)
                if other_refdes.upper().startswith(("J", "P", "CON")):
                    has_driver = True
                    break
            
            if not has_pullup_down and not has_driver and len(net_pins) <= 2:
                violations.append(Violation(
                    rule_id="SCH_FLOAT_001",
                    refdes=ic_refdes,
                    pin_number=pin_num,
                    pin_name=pin_name,
                    net_name=net_name,
                    issue="Input pin may be floating (no pull-up/down or driver detected)",
                    details={
                        "net_node_count": len(net_pins),
                        "resistors_found": [r[0] for r in resistors]
                    }
                ))
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(status=status, violation_count=len(violations), violations=violations, notes=notes)


def validate_i2c_buses(graph: SchematicGraph) -> dict[str, Any]:
    """MS_I2C_001 / SCH_I2C_002: Validate I2C bus pull-ups and address conflicts.
    
    Groups SDA/SCL net pairs, verifies pull-ups exist, checks for address conflicts.
    """
    buses: list[I2CBusAnalysis] = []
    overall_status = "PASS"
    
    # Find SDA and SCL nets
    sda_nets = graph.get_nets_by_pattern(r'SDA')
    scl_nets = graph.get_nets_by_pattern(r'SCL')
    
    if not sda_nets and not scl_nets:
        return {
            "status": "SKIPPED",
            "buses": [],
            "notes": ["No I2C nets (SDA/SCL) detected"]
        }
    
    # Try to pair SDA/SCL nets
    paired_buses: list[tuple[str | None, str | None]] = []
    
    # Simple pairing: match by suffix/prefix
    sda_remaining = set(sda_nets)
    scl_remaining = set(scl_nets)
    
    for sda in list(sda_remaining):
        # Try to find matching SCL
        sda_base = re.sub(r'SDA', '', sda, flags=re.IGNORECASE)
        for scl in list(scl_remaining):
            scl_base = re.sub(r'SCL', '', scl, flags=re.IGNORECASE)
            if sda_base.upper() == scl_base.upper():
                paired_buses.append((sda, scl))
                sda_remaining.discard(sda)
                scl_remaining.discard(scl)
                break
    
    # Add unpaired nets
    for sda in sda_remaining:
        paired_buses.append((sda, None))
    for scl in scl_remaining:
        paired_buses.append((None, scl))
    
    # Analyze each bus
    for idx, (sda_net, scl_net) in enumerate(paired_buses):
        bus = I2CBusAnalysis(
            bus_id=f"I2C_BUS_{idx}",
            sda_net=sda_net,
            scl_net=scl_net
        )
        
        # Check pull-ups for each line
        for net_name, key in [(sda_net, "SDA"), (scl_net, "SCL")]:
            if not net_name:
                continue
            
            resistors = graph.find_resistors_on_net(net_name)
            has_pullup = False
            
            for res_refdes, res_value in resistors:
                other_net = graph.trace_through_resistor(res_refdes, net_name)
                if other_net and graph.is_power_or_ground_net(other_net):
                    # Check if it's a pull-up (to power, not ground)
                    other_upper = other_net.upper()
                    if not any(g in other_upper for g in ["GND", "GROUND", "VSS"]):
                        has_pullup = True
                        break
            
            bus.pullups_detected[net_name] = has_pullup
            
            if not has_pullup:
                bus.rule_violations.append("MS_I2C_001")
                overall_status = "FAIL"
        
        # Find all components on the bus
        components_on_bus: set[str] = set()
        for net_name in [sda_net, scl_net]:
            if not net_name:
                continue
            for refdes, pin_num, pin_name in graph.get_net_pins(net_name):
                if refdes.upper().startswith(("U", "IC")):
                    components_on_bus.add(refdes)
        
        bus.components_on_bus = list(components_on_bus)
        
        # Check for address conflicts (requires address attribute in BOM/component)
        # This is a limitation - addresses are often not in schematic JSON
        addresses: dict[str, list[str]] = defaultdict(list)  # address -> [components]
        for refdes in components_on_bus:
            comp = graph.get_component(refdes)
            if comp:
                # Try to find address in BOM or component attributes
                bom = comp.get("bom", {})
                for attr_key in ["address", "i2c_address", "slave_address"]:
                    addr = bom.get(attr_key) or comp.get(attr_key)
                    if addr:
                        addresses[str(addr)].append(refdes)
                        break
        
        for addr, comps in addresses.items():
            if len(comps) > 1:
                bus.address_conflicts.append({
                    "address": addr,
                    "conflicting_components": comps
                })
                if "SCH_I2C_002" not in bus.rule_violations:
                    bus.rule_violations.append("SCH_I2C_002")
                    overall_status = "FAIL"
        
        buses.append(bus)
    
    return {
        "status": overall_status,
        "buses": [asdict(b) for b in buses],
        "notes": [f"Analyzed {len(buses)} I2C buses"]
    }


def check_unused_opamps(graph: SchematicGraph) -> CheckResult:
    """AN_OPAMP_002 / SCH_PULLUP_001: Detect unused op-amp/comparator channels.
    
    Multi-channel op-amp packages should have unused channels tied off properly.
    """
    violations = []
    notes = []
    
    # Op-amp/comparator patterns
    opamp_patterns = [
        "OPAMP", "OP-AMP", "LM358", "LM324", "TLV", "OPA", "MCP60", "AD820",
        "LM339", "LM393", "COMPARATOR", "TL07", "TL08", "NE5532"
    ]
    
    opamps = graph.find_components_by_type(opamp_patterns)
    
    if not opamps:
        return CheckResult(status="SKIPPED", notes=["No op-amp/comparator components detected"])
    
    notes.append(f"Analyzing {len(opamps)} op-amp/comparator components")
    
    for refdes in opamps:
        pins = graph.component_pins.get(refdes, [])
        comp = graph.get_component(refdes)
        
        # Group pins by channel (heuristic: look for +IN, -IN, OUT patterns)
        # This is complex because different packages have different pinouts
        
        # Check for pins on single-pin nets (potentially unused)
        for pin_num, pin_name, net_name in pins:
            if not net_name:
                continue
            
            # Skip power pins
            if pin_name and pin_name.upper() in ["VCC", "VDD", "VEE", "VSS", "V+", "V-", "GND"]:
                continue
            
            # Check if this looks like an input/output pin
            if not pin_name:
                continue
            
            pin_upper = pin_name.upper()
            is_io_pin = any(p in pin_upper for p in ["IN", "OUT", "+", "-"])
            
            if is_io_pin:
                net_pins = graph.get_net_pins(net_name)
                if len(net_pins) == 1:
                    # This pin is on a single-pin net - potentially floating
                    violations.append(Violation(
                        rule_id="SCH_PULLUP_001",
                        refdes=refdes,
                        pin_number=pin_num,
                        pin_name=pin_name,
                        net_name=net_name,
                        component_value=comp.get("value", "") if comp else "",
                        issue=f"Op-amp/comparator pin potentially floating (single-pin net)",
                        details={"pin_type": "input/output"}
                    ))
    
    status = "FAIL" if violations else "PASS"
    return CheckResult(status=status, violation_count=len(violations), violations=violations, notes=notes)


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

def violation_to_dict(v: Violation) -> dict[str, Any]:
    """Convert Violation to JSON-serializable dict."""
    d = {
        "rule_id": v.rule_id,
        "issue": v.issue,
    }
    if v.refdes:
        d["refdes"] = v.refdes
    if v.pin_number:
        d["pin_number"] = v.pin_number
    if v.pin_name:
        d["pin_name"] = v.pin_name
    if v.net_name:
        d["net_name"] = v.net_name
    if v.component_value:
        d["component_value"] = v.component_value
    if v.details:
        d["details"] = v.details
    return d


def check_result_to_dict(cr: CheckResult) -> dict[str, Any]:
    """Convert CheckResult to JSON-serializable dict."""
    return {
        "status": cr.status,
        "violation_count": cr.violation_count,
        "violations": [violation_to_dict(v) for v in cr.violations],
        "notes": cr.notes
    }


def format_output(output: AnalysisOutput, json_mode: bool) -> str:
    """Format output as JSON or human-readable text."""
    result: dict[str, Any] = {
        "status": output.status,
        "schematic_file": output.schematic_file,
    }
    
    if output.conversion_limitations:
        result["conversion_limitations"] = output.conversion_limitations
    
    if output.single_pin_nets:
        result["single_pin_nets"] = check_result_to_dict(output.single_pin_nets)
    
    if output.uart_crossover:
        result["uart_crossover"] = check_result_to_dict(output.uart_crossover)
    
    if output.fet_gate_terminations:
        result["fet_gate_terminations"] = check_result_to_dict(output.fet_gate_terminations)
    
    if output.floating_inputs:
        result["floating_inputs"] = check_result_to_dict(output.floating_inputs)
    
    if output.i2c_bus_analysis:
        result["i2c_bus_analysis"] = output.i2c_bus_analysis
    
    if output.opamp_tieoff:
        result["opamp_tieoff"] = check_result_to_dict(output.opamp_tieoff)
    
    if json_mode:
        return json.dumps(result, indent=2)
    
    # Human-readable format
    lines = []
    lines.append(f"=== Schematic Analysis: {output.schematic_file} ===")
    lines.append(f"Status: {output.status}")
    lines.append("")
    
    if output.conversion_limitations:
        lines.append("Conversion Limitations:")
        for lim in output.conversion_limitations:
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
            for v in cr.violations[:10]:  # Limit display
                lines.append(f"    [{v.rule_id}] {v.issue}")
                if v.refdes:
                    lines.append(f"      Component: {v.refdes}")
                if v.net_name:
                    lines.append(f"      Net: {v.net_name}")
            if len(cr.violations) > 10:
                lines.append(f"    ... and {len(cr.violations) - 10} more")
        lines.append("")
    
    format_check("Single-Pin Nets (SCH_NET_002)", output.single_pin_nets)
    format_check("UART Crossover (SCH_UART_001)", output.uart_crossover)
    format_check("FET Gate Termination (SCH_FET_001)", output.fet_gate_terminations)
    format_check("Floating Inputs (SCH_FLOAT_001)", output.floating_inputs)
    format_check("Op-Amp Tie-Off (SCH_PULLUP_001)", output.opamp_tieoff)
    
    if output.i2c_bus_analysis:
        i2c = output.i2c_bus_analysis
        lines.append(f"--- I2C Bus Analysis [{i2c.get('status', 'UNKNOWN')}] ---")
        for note in i2c.get("notes", []):
            lines.append(f"  Note: {note}")
        for bus in i2c.get("buses", []):
            lines.append(f"  Bus: {bus['bus_id']}")
            lines.append(f"    SDA: {bus.get('sda_net', 'N/A')}, SCL: {bus.get('scl_net', 'N/A')}")
            lines.append(f"    Pull-ups: {bus.get('pullups_detected', {})}")
            if bus.get("address_conflicts"):
                lines.append(f"    Address Conflicts: {bus['address_conflicts']}")
            if bus.get("rule_violations"):
                lines.append(f"    Rule Violations: {bus['rule_violations']}")
        lines.append("")
    
    # Append JSON block for easy parsing
    lines.append("=== JSON Output ===")
    lines.append(json.dumps(result, indent=2))
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ThomsonLint Schematic Analysis Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python schematic_helpers.py exports/project-thomson-export-sch.json --analyze-all --json
  python schematic_helpers.py exports/project-thomson-export-sch.json --single-pins --i2c-check
        """
    )
    
    parser.add_argument("schematic_json", help="Path to schematic JSON export file")
    parser.add_argument("--analyze-all", action="store_true", help="Run all checks")
    parser.add_argument("--single-pins", action="store_true", help="Single-pin net detection (SCH_NET_002)")
    parser.add_argument("--uart-check", action="store_true", help="UART crossover validation (SCH_UART_001)")
    parser.add_argument("--fet-check", action="store_true", help="FET gate termination check (SCH_FET_001)")
    parser.add_argument("--floating-check", action="store_true", help="Floating input detection (SCH_FLOAT_001)")
    parser.add_argument("--i2c-check", action="store_true", help="I2C bus analysis (MS_I2C_001, SCH_I2C_002)")
    parser.add_argument("--opamp-check", action="store_true", help="Op-amp tie-off check (SCH_PULLUP_001)")
    parser.add_argument("--json", action="store_true", help="Output pure JSON (no human-readable text)")
    
    args = parser.parse_args()
    
    # Validate input file
    schematic_path = Path(args.schematic_json)
    if not schematic_path.exists():
        error = {
            "status": "ERROR",
            "error": f"Schematic file not found: {args.schematic_json}",
            "schematic_file": str(schematic_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Load JSON
    try:
        with open(schematic_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        error = {
            "status": "ERROR",
            "error": f"Invalid JSON: {e}",
            "schematic_file": str(schematic_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error = {
            "status": "ERROR",
            "error": f"Failed to read file: {e}",
            "schematic_file": str(schematic_path)
        }
        print(json.dumps(error, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Build graph
    output = AnalysisOutput(schematic_file=str(schematic_path))
    
    try:
        graph = SchematicGraph(data)
    except Exception as e:
        output.status = "ERROR"
        output.conversion_limitations.append(f"Failed to build schematic graph: {e}")
        print(format_output(output, args.json))
        sys.exit(1)
    
    # Check for schema limitations
    if not data.get("components"):
        output.conversion_limitations.append("No 'components' array found in schematic JSON")
    if not data.get("nets"):
        output.conversion_limitations.append("No 'nets' array found in schematic JSON")
    
    # Determine which checks to run
    run_all = args.analyze_all
    run_single_pins = args.single_pins or run_all
    run_uart = args.uart_check or run_all
    run_fet = args.fet_check or run_all
    run_floating = args.floating_check or run_all
    run_i2c = args.i2c_check or run_all
    run_opamp = args.opamp_check or run_all
    
    # If no specific check requested and not --analyze-all, default to all
    if not any([args.single_pins, args.uart_check, args.fet_check, 
                args.floating_check, args.i2c_check, args.opamp_check, args.analyze_all]):
        run_single_pins = run_uart = run_fet = run_floating = run_i2c = run_opamp = True
    
    # Run analyses
    has_failures = False
    
    if run_single_pins:
        output.single_pin_nets = find_single_pin_nets(graph)
        if output.single_pin_nets.status == "FAIL":
            has_failures = True
    
    if run_uart:
        output.uart_crossover = check_uart_crossover(graph)
        if output.uart_crossover.status == "FAIL":
            has_failures = True
    
    if run_fet:
        output.fet_gate_terminations = verify_fet_gate_termination(graph)
        if output.fet_gate_terminations.status == "FAIL":
            has_failures = True
    
    if run_floating:
        output.floating_inputs = find_floating_inputs(graph)
        if output.floating_inputs.status == "FAIL":
            has_failures = True
    
    if run_i2c:
        output.i2c_bus_analysis = validate_i2c_buses(graph)
        if output.i2c_bus_analysis.get("status") == "FAIL":
            has_failures = True
    
    if run_opamp:
        output.opamp_tieoff = check_unused_opamps(graph)
        if output.opamp_tieoff.status == "FAIL":
            has_failures = True
    
    output.status = "FAIL" if has_failures else "PASS"
    
    print(format_output(output, args.json))
    sys.exit(0)  # Exit 0 even with violations - reserve non-zero for errors


if __name__ == "__main__":
    main()
