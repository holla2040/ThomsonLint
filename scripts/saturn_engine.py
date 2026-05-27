#!/usr/bin/env python3
"""
saturn_engine.py

Mathematical verification engine for PCB electrical and thermal calculations.
Implements industry-standard formulas from IPC-2152, IPC-2221B, and Wheeler/Wadell
transmission line models.

This is a stateless mathematical calculator that accepts raw numerical dimensions,
materials, and voltages, and returns calculated physical metrics. It does not parse
JSON directly.

Architecture:
    1. Conductor Impedance Module (Wheeler/Wadell equations)
    2. IPC-2152 Thermal & Current Capacity
    3. IPC-2221B Voltage Spacing Lookup
    4. Via Parasitics (Resistance/Inductance)
"""

import math
from typing import Dict, Optional, Literal
from dataclasses import dataclass


# ============================================================================
# Module 1: Conductor Impedance Calculations
# ============================================================================

@dataclass
class ImpedanceResult:
    """Result of impedance calculation."""
    z0_ohms: float
    topology: str  # "microstrip" or "stripline"
    width_mm: float
    thickness_mm: float
    dielectric_height_mm: float
    dielectric_constant: float
    valid: bool
    error_message: Optional[str] = None


def calculate_microstrip_impedance(
    w: float,
    t: float,
    h: float,
    dk: float,
    unit: Literal["mm", "mil"] = "mm"
) -> ImpedanceResult:
    """
    Calculates characteristic impedance of a surface microstrip using Wheeler's
    closed-form approximation.
    
    Args:
        w: Trace width
        t: Trace thickness (copper weight)
        h: Dielectric height (distance to reference plane)
        dk: Dielectric constant (Er)
        unit: Units for w, t, h ("mm" or "mil")
    
    Returns:
        ImpedanceResult with calculated impedance in ohms
    
    Reference:
        Wheeler, H.A. "Transmission-Line Properties of Parallel Strips Separated
        by a Dielectric Sheet," IEEE Trans. Microwave Theory Tech., 1965.
    """
    if h <= 0 or w <= 0 or dk <= 0:
        return ImpedanceResult(
            z0_ohms=0.0,
            topology="microstrip",
            width_mm=w if unit == "mm" else w * 0.0254,
            thickness_mm=t if unit == "mm" else t * 0.0254,
            dielectric_height_mm=h if unit == "mm" else h * 0.0254,
            dielectric_constant=dk,
            valid=False,
            error_message="Invalid dimensions: w, h, and dk must be positive"
        )
    
    # Wheeler closed-form approximation
    # Z0 = (87 / sqrt(dk + 1.41)) * ln(5.98*h / (0.8*w + t))
    term1 = 5.98 * h / (0.8 * w + t)
    if term1 <= 0:
        return ImpedanceResult(
            z0_ohms=0.0,
            topology="microstrip",
            width_mm=w if unit == "mm" else w * 0.0254,
            thickness_mm=t if unit == "mm" else t * 0.0254,
            dielectric_height_mm=h if unit == "mm" else h * 0.0254,
            dielectric_constant=dk,
            valid=False,
            error_message="Invalid geometry: trace width too large relative to height"
        )
    
    z0 = (87.0 / math.sqrt(dk + 1.41)) * math.log(term1)
    
    return ImpedanceResult(
        z0_ohms=round(z0, 2),
        topology="microstrip",
        width_mm=w if unit == "mm" else w * 0.0254,
        thickness_mm=t if unit == "mm" else t * 0.0254,
        dielectric_height_mm=h if unit == "mm" else h * 0.0254,
        dielectric_constant=dk,
        valid=True
    )


def calculate_stripline_impedance(
    w: float,
    t: float,
    b: float,
    dk: float,
    unit: Literal["mm", "mil"] = "mm"
) -> ImpedanceResult:
    """
    Calculates characteristic impedance of a symmetric stripline (centered between
    two ground planes).
    
    Args:
        w: Trace width
        t: Trace thickness
        b: Total spacing between ground planes (dielectric thickness)
        dk: Dielectric constant
        unit: Units for w, t, b ("mm" or "mil")
    
    Returns:
        ImpedanceResult with calculated impedance in ohms
    
    Reference:
        Wadell, B.C. "Transmission Line Design Handbook," Artech House, 1991.
    """
    if b <= 0 or w <= 0 or b <= (2 * t) or dk <= 0:
        return ImpedanceResult(
            z0_ohms=0.0,
            topology="stripline",
            width_mm=w if unit == "mm" else w * 0.0254,
            thickness_mm=t if unit == "mm" else t * 0.0254,
            dielectric_height_mm=b if unit == "mm" else b * 0.0254,
            dielectric_constant=dk,
            valid=False,
            error_message="Invalid dimensions: check b > 2*t and all values positive"
        )
    
    # Z0 = (60 / sqrt(dk)) * ln(1.9*b / (0.8*w + t))
    term = 1.9 * b / (0.8 * w + t)
    if term <= 0:
        return ImpedanceResult(
            z0_ohms=0.0,
            topology="stripline",
            width_mm=w if unit == "mm" else w * 0.0254,
            thickness_mm=t if unit == "mm" else t * 0.0254,
            dielectric_height_mm=b if unit == "mm" else b * 0.0254,
            dielectric_constant=dk,
            valid=False,
            error_message="Invalid geometry: trace width too large"
        )
    
    z0 = (60.0 / math.sqrt(dk)) * math.log(term)
    
    return ImpedanceResult(
        z0_ohms=round(z0, 2),
        topology="stripline",
        width_mm=w if unit == "mm" else w * 0.0254,
        thickness_mm=t if unit == "mm" else t * 0.0254,
        dielectric_height_mm=b if unit == "mm" else b * 0.0254,
        dielectric_constant=dk,
        valid=True
    )


def calculate_differential_impedance(
    z0_single: float,
    s: float,
    h: float,
    topology: str = "microstrip"
) -> float:
    """
    Calculates differential impedance from single-ended impedance and spacing.
    Supports microstrip and stripline coupling factor formulas.
    
    Args:
        z0_single: Single-ended impedance (ohms)
        s: Spacing between traces (same units as h)
        h: Height to reference plane (same units as s)
        topology: "microstrip" or "stripline"
    
    Returns:
        Differential impedance in ohms
    
    Note:
        Microstrip: Zdiff ≈ 2 * Z0 * (1 - 0.48 * exp(-0.96 * s/h))
        Stripline: Zdiff ≈ 2 * Z0 * (1 - 0.374 * exp(-2.9 * s/h))
    """
    if h <= 0 or s < 0:
        return 0.0
    
    topology_normalized = topology.lower().strip()
    if topology_normalized == "stripline":
        coupling_factor = 1.0 - 0.374 * math.exp(-2.9 * s / h)
    else:  # Default/microstrip
        coupling_factor = 1.0 - 0.48 * math.exp(-0.96 * s / h)
        
    zdiff = 2.0 * z0_single * coupling_factor
    return round(zdiff, 2)


# ============================================================================
# Module 2: IPC-2152 Thermal & Current Capacity
# ============================================================================

@dataclass
class ThermalResult:
    """Result of thermal/current capacity calculation."""
    temp_rise_c: Optional[float]
    max_current_a: Optional[float]
    width_mm: float
    thickness_um: float
    area_sq_mils: float
    is_internal: bool
    valid: bool
    error_message: Optional[str] = None


def calculate_temp_rise(
    width_mm: float,
    thickness_um: float,
    current_a: float,
    is_internal: bool
) -> ThermalResult:
    """
    Calculates trace temperature rise in Celsius using the IPC-2152 empirical formula.
    
    Args:
        width_mm: Trace width in millimeters
        thickness_um: Copper thickness in micrometers (typically 17.5um for 0.5oz, 35um for 1oz)
        current_a: Current in amperes
        is_internal: True for internal layers, False for external layers
    
    Returns:
        ThermalResult with temperature rise in Celsius
    
    Formula:
        I = k * (ΔT^0.44) * (A^0.725)
        Where k = 0.024 (internal) or 0.048 (external)
        
    Rearranged:
        ΔT = (I / (k * A^0.725))^(1/0.44)
    
    Reference:
        IPC-2152 "Standard for Determining Current Carrying Capacity in Printed Board Design"
    """
    if width_mm <= 0 or thickness_um <= 0 or current_a <= 0:
        return ThermalResult(
            temp_rise_c=None,
            max_current_a=None,
            width_mm=width_mm,
            thickness_um=thickness_um,
            area_sq_mils=0.0,
            is_internal=is_internal,
            valid=False,
            error_message="Invalid inputs: width, thickness, and current must be positive"
        )
    
    # Convert cross-sectional area to square mils
    width_mils = width_mm * 39.37  # 1mm = 39.37 mils
    thickness_mils = thickness_um * 0.03937  # 1um = 0.03937 mils
    area_sq_mils = width_mils * thickness_mils
    
    if area_sq_mils <= 0:
        return ThermalResult(
            temp_rise_c=None,
            max_current_a=None,
            width_mm=width_mm,
            thickness_um=thickness_um,
            area_sq_mils=0.0,
            is_internal=is_internal,
            valid=False,
            error_message="Invalid area calculation"
        )
    
    # IPC-2152 empirical constants
    k = 0.024 if is_internal else 0.048
    
    # Calculate temperature rise
    term = current_a / (k * math.pow(area_sq_mils, 0.725))
    temp_rise = math.pow(term, 1.0 / 0.44)
    
    return ThermalResult(
        temp_rise_c=round(temp_rise, 2),
        max_current_a=None,
        width_mm=width_mm,
        thickness_um=thickness_um,
        area_sq_mils=round(area_sq_mils, 4),
        is_internal=is_internal,
        valid=True
    )


def calculate_max_current(
    width_mm: float,
    thickness_um: float,
    max_temp_rise_c: float,
    is_internal: bool
) -> ThermalResult:
    """
    Calculates maximum allowable current for a specified temperature rise limit.
    
    Args:
        width_mm: Trace width in millimeters
        thickness_um: Copper thickness in micrometers
        max_temp_rise_c: Maximum allowable temperature rise in Celsius (typically 10°C or 20°C)
        is_internal: True for internal layers, False for external layers
    
    Returns:
        ThermalResult with maximum current in amperes
    
    Formula:
        I = k * (ΔT^0.44) * (A^0.725)
    """
    if width_mm <= 0 or thickness_um <= 0 or max_temp_rise_c <= 0:
        return ThermalResult(
            temp_rise_c=None,
            max_current_a=None,
            width_mm=width_mm,
            thickness_um=thickness_um,
            area_sq_mils=0.0,
            is_internal=is_internal,
            valid=False,
            error_message="Invalid inputs: all parameters must be positive"
        )
    
    # Convert cross-sectional area to square mils
    width_mils = width_mm * 39.37
    thickness_mils = thickness_um * 0.03937
    area_sq_mils = width_mils * thickness_mils
    
    if area_sq_mils <= 0:
        return ThermalResult(
            temp_rise_c=None,
            max_current_a=None,
            width_mm=width_mm,
            thickness_um=thickness_um,
            area_sq_mils=0.0,
            is_internal=is_internal,
            valid=False,
            error_message="Invalid area calculation"
        )
    
    # IPC-2152 empirical constants
    k = 0.024 if is_internal else 0.048
    
    # Calculate maximum current
    max_current = k * math.pow(max_temp_rise_c, 0.44) * math.pow(area_sq_mils, 0.725)
    
    return ThermalResult(
        temp_rise_c=max_temp_rise_c,
        max_current_a=round(max_current, 3),
        width_mm=width_mm,
        thickness_um=thickness_um,
        area_sq_mils=round(area_sq_mils, 4),
        is_internal=is_internal,
        valid=True
    )


# ============================================================================
# Module 3: IPC-2221B Voltage Spacing Requirements
# ============================================================================

# Spacing requirements in mm based on voltage peak and domain category
# Category B1: Internal conductors
# Category B2: External conductors, uncoated, sea level to 3050m
# Category B4: External conductors, coated (conformally coated)
IPC_2221_SPACING_TABLE: Dict[tuple[float, str], float] = {
    # (Max Voltage limit, Category) -> Minimum Clearance in mm
    (15, "B1"): 0.05,  (15, "B2"): 0.1,   (15, "B4"): 0.13,
    (30, "B1"): 0.1,   (30, "B2"): 0.1,   (30, "B4"): 0.13,
    (50, "B1"): 0.1,   (50, "B2"): 0.6,   (50, "B4"): 0.13,
    (100, "B1"): 0.1,  (100, "B2"): 0.6,  (100, "B4"): 0.13,
    (150, "B1"): 0.1,  (150, "B2"): 0.6,  (150, "B4"): 0.4,
    (300, "B1"): 0.2,  (300, "B2"): 1.25, (300, "B4"): 0.4,
    (500, "B1"): 0.25, (500, "B2"): 2.5,  (500, "B4"): 0.8,
}


@dataclass
class SpacingResult:
    """Result of voltage spacing calculation."""
    required_clearance_mm: float
    voltage_v: float
    category: str
    valid: bool
    error_message: Optional[str] = None


def get_required_clearance(
    voltage_v: float,
    category: str = "B2"
) -> SpacingResult:
    """
    Returns the required electrical clearance in mm per IPC-2221B Table 6-1.
    
    Args:
        voltage_v: Peak working voltage (not RMS) in volts
        category: IPC category ("B1", "B2", or "B4")
            B1: Internal conductors
            B2: External uncoated, sea level to 3050m
            B4: External conformally coated
    
    Returns:
        SpacingResult with required clearance in millimeters
    
    Reference:
        IPC-2221B Generic Standard on Printed Board Design, Table 6-1
    """
    category = category.upper()
    
    if category not in ("B1", "B2", "B4"):
        return SpacingResult(
            required_clearance_mm=0.0,
            voltage_v=voltage_v,
            category=category,
            valid=False,
            error_message=f"Invalid category '{category}'. Must be B1, B2, or B4"
        )
    
    if voltage_v < 0:
        return SpacingResult(
            required_clearance_mm=0.0,
            voltage_v=voltage_v,
            category=category,
            valid=False,
            error_message="Voltage must be non-negative"
        )
    
    # Find the matching voltage step
    sorted_steps = sorted([v for v, cat in IPC_2221_SPACING_TABLE.keys() if cat == category])
    
    for step in sorted_steps:
        if voltage_v <= step:
            clearance = IPC_2221_SPACING_TABLE[(step, category)]
            return SpacingResult(
                required_clearance_mm=clearance,
                voltage_v=voltage_v,
                category=category,
                valid=True
            )
    
    # For voltages > 500V, use linear scaling formula:
    # Add 0.0025 mm per volt above 500V baseline
    if category == "B1":
        clearance = 0.25 + (voltage_v - 500.0) * 0.001
    elif category == "B2":
        clearance = 2.5 + (voltage_v - 500.0) * 0.005
    else:  # B4
        clearance = 0.8 + (voltage_v - 500.0) * 0.0025
    
    return SpacingResult(
        required_clearance_mm=round(clearance, 3),
        voltage_v=voltage_v,
        category=category,
        valid=True
    )


# ============================================================================
# Module 4: Via Parasitics & Thermal Resistance
# ============================================================================

@dataclass
class ViaParasiticsResult:
    """Result of via parasitics calculation."""
    via_resistance_ohms: float
    via_inductance_nh: float
    thermal_resistance_c_per_w: float
    drill_dia_mm: float
    plating_thickness_um: float
    length_mm: float
    valid: bool
    error_message: Optional[str] = None


def calculate_via_parasitics(
    drill_dia_mm: float,
    plating_thickness_um: float,
    length_mm: float
) -> ViaParasiticsResult:
    """
    Calculates via electrical and thermal properties.
    
    Args:
        drill_dia_mm: Via drill diameter in millimeters
        plating_thickness_um: Copper plating thickness in micrometers (typically 25um / 1 mil)
        length_mm: Via length (board thickness) in millimeters
    
    Returns:
        ViaParasiticsResult with resistance (ohms), inductance (nH), and thermal resistance (°C/W)
    
    Notes:
        - Copper resistivity at 20°C: 1.72e-8 Ω·m
        - Via inductance approximation assumes cylindrical conductor
        - Thermal resistance uses parallel thermal conductivity of copper plating
    """
    if drill_dia_mm <= 0 or plating_thickness_um <= 0 or length_mm <= 0:
        return ViaParasiticsResult(
            via_resistance_ohms=0.0,
            via_inductance_nh=0.0,
            thermal_resistance_c_per_w=0.0,
            drill_dia_mm=drill_dia_mm,
            plating_thickness_um=plating_thickness_um,
            length_mm=length_mm,
            valid=False,
            error_message="Invalid inputs: all dimensions must be positive"
        )
    
    # Copper resistivity at 20°C in Ohm-meters
    rho_copper = 1.72e-8
    
    # Convert to meters
    r_outer = (drill_dia_mm / 2.0) / 1000.0  # Outer radius in meters
    plating_m = plating_thickness_um / 1e6  # Plating thickness in meters
    r_inner = r_outer - plating_m  # Inner radius
    
    if r_inner < 0:
        return ViaParasiticsResult(
            via_resistance_ohms=0.0,
            via_inductance_nh=0.0,
            thermal_resistance_c_per_w=0.0,
            drill_dia_mm=drill_dia_mm,
            plating_thickness_um=plating_thickness_um,
            length_mm=length_mm,
            valid=False,
            error_message="Plating thickness exceeds drill radius"
        )
    
    # Calculate cross-sectional area of plating (annular ring)
    area_m2 = math.pi * (r_outer**2 - r_inner**2)
    length_m = length_mm / 1000.0
    
    # DC resistance: R = ρ * L / A
    if area_m2 > 0:
        resistance = rho_copper * (length_m / area_m2)
    else:
        resistance = 0.0
    
    # Approximate self-inductance of a cylindrical conductor (Neumann formula approximation)
    # L ≈ 0.2 * l * (ln(4*l/d) - 0.75) in nH, where l and d are in mm
    if drill_dia_mm > 0 and length_mm > 0:
        inductance = 0.2 * length_mm * (math.log(4.0 * length_mm / drill_dia_mm) - 0.75)
    else:
        inductance = 0.0
    
    # Thermal resistance: R_th = L / (k * A)
    # Copper thermal conductivity: k ≈ 400 W/(m·K)
    k_copper = 400.0  # W/(m·K)
    if area_m2 > 0:
        thermal_resistance = length_m / (k_copper * area_m2)
    else:
        thermal_resistance = 0.0
    
    return ViaParasiticsResult(
        via_resistance_ohms=round(resistance, 6),
        via_inductance_nh=round(max(0.0, inductance), 4),
        thermal_resistance_c_per_w=round(thermal_resistance, 2),
        drill_dia_mm=drill_dia_mm,
        plating_thickness_um=plating_thickness_um,
        length_mm=length_mm,
        valid=True
    )


def calculate_thermal_via_array_resistance(
    num_vias: int,
    single_via_r_th: float
) -> float:
    """
    Calculates the effective thermal resistance of a parallel via array.
    
    Args:
        num_vias: Number of vias in the thermal array
        single_via_r_th: Thermal resistance of a single via (°C/W)
    
    Returns:
        Effective thermal resistance in °C/W
    
    Note:
        For N vias in parallel: R_eff = R_single / N
    """
    if num_vias <= 0 or single_via_r_th <= 0:
        return 0.0
    
    return round(single_via_r_th / num_vias, 3)


# ============================================================================
# CLI Interface (for standalone testing)
# ============================================================================

if __name__ == "__main__":
    import json
    import sys
    
    print("Saturn PCB Mathematical Verification Engine")
    print("=" * 60)
    
    # Example calculations
    print("\n1. Microstrip Impedance (50Ω target)")
    result = calculate_microstrip_impedance(
        w=0.254,  # 10 mil trace
        t=0.035,  # 1oz copper
        h=0.2,    # 8 mil dielectric
        dk=4.5
    )
    print(json.dumps(result.__dict__, indent=2))
    
    print("\n2. IPC-2152 Trace Temperature Rise")
    result = calculate_temp_rise(
        width_mm=0.5,
        thickness_um=35,  # 1oz
        current_a=1.0,
        is_internal=False
    )
    print(json.dumps(result.__dict__, indent=2))
    
    print("\n3. IPC-2221B Voltage Spacing (12V external)")
    result = get_required_clearance(voltage_v=12.0, category="B2")
    print(json.dumps(result.__dict__, indent=2))
    
    print("\n4. Via Parasitics")
    result = calculate_via_parasitics(
        drill_dia_mm=0.3,
        plating_thickness_um=25,
        length_mm=1.6
    )
    print(json.dumps(result.__dict__, indent=2))
