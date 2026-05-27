#!/usr/bin/env python3
"""ThomsonLint Geometry Analysis Engine

High-performance mathematical functions for analyzing board JSON geometry data.
These helpers operate on the enriched JSON produced by thomson_bundle_converter.py.

Key capabilities:
- Trace width analysis by net
- Net-to-net clearance calculations
- Differential pair coupling analysis
- NPTH (Non-Plated Through Hole) safety zone verification

All distances/coordinates follow the units specified in the board JSON (typically MM or INCH).
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A trace segment with endpoints and width."""
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str
    net: str | None = None
    segment_id: str | None = None

    @property
    def length(self) -> float:
        """Euclidean length of the segment."""
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def midpoint(self) -> tuple[float, float]:
        """Midpoint coordinates."""
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


@dataclass
class NetSegmentStats:
    """Statistics for all segments belonging to a net."""
    net_name: str
    segments: list[Segment] = field(default_factory=list)
    total_length: float = 0.0
    min_width: float | None = None
    max_width: float | None = None
    avg_width: float | None = None
    nominal_width: float | None = None  # Most common width
    layers: set[str] = field(default_factory=set)
    width_histogram: dict[float, int] = field(default_factory=dict)


@dataclass
class ClearanceResult:
    """Result of a clearance calculation between two nets."""
    net_a: str
    net_b: str
    min_clearance: float | None
    clearance_location: tuple[float, float] | None = None
    clearance_layer: str | None = None
    segment_a_id: str | None = None
    segment_b_id: str | None = None
    calculation_method: str = "point_to_segment"
    segments_compared: int = 0


@dataclass
class DifferentialPairAnalysis:
    """Analysis results for a differential pair."""
    net_positive: str
    net_negative: str
    avg_coupling_distance: float | None = None
    min_coupling_distance: float | None = None
    max_coupling_distance: float | None = None
    total_length_positive: float = 0.0
    total_length_negative: float = 0.0
    length_mismatch: float = 0.0
    length_mismatch_percent: float = 0.0
    coupled_sections: list[dict[str, Any]] = field(default_factory=list)
    uncoupled_sections: list[dict[str, Any]] = field(default_factory=list)
    uncoupled_length: float = 0.0
    coupling_quality: str = "unknown"  # good, marginal, poor


@dataclass
class NPTHClearanceViolation:
    """A copper feature violating NPTH keepout zone."""
    hole_id: str
    hole_x: float
    hole_y: float
    hole_diameter: float
    feature_type: str  # pad, route, polygon
    feature_id: str | None
    feature_net: str | None
    feature_layer: str
    distance_to_hole: float
    keepout_radius: float
    violation_severity: str  # critical, warning


@dataclass
class NPTHClearanceResult:
    """Full NPTH clearance analysis results."""
    npth_count: int
    analyzed_count: int
    keepout_radius: float
    keepout_units: str
    violations: list[NPTHClearanceViolation] = field(default_factory=list)
    clean_holes: list[str] = field(default_factory=list)
    pass_status: bool = True


# ---------------------------------------------------------------------------
# Core Geometry Functions
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> float | None:
    """Safely convert to float."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _distance_point_to_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Compute minimum distance from point (px, py) to line segment (x1, y1)-(x2, y2)."""
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _segment_to_segment_distance(s1: Segment, s2: Segment) -> tuple[float, tuple[float, float]]:
    """Compute exact minimum distance between two line segments.
    
    Returns (distance, closest_point_on_s1).
    Uses exact geometric intersection check followed by endpoint-to-segment distances.
    """
    p1x, p1y, p2x, p2y = s1.x1, s1.y1, s1.x2, s1.y2
    p3x, p3y, p4x, p4y = s2.x1, s2.y1, s2.x2, s2.y2

    # Helper: counter-clockwise orientation test
    def ccw(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> bool:
        return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax)
    
    # Check for exact intersection using orientation tests
    def segments_intersect(ax: float, ay: float, bx: float, by: float, 
                           cx: float, cy: float, dx: float, dy: float) -> bool:
        return (ccw(ax, ay, cx, cy, dx, dy) != ccw(bx, by, cx, cy, dx, dy) and
                ccw(ax, ay, bx, by, cx, cy) != ccw(ax, ay, bx, by, dx, dy))
    
    # If segments intersect, distance is 0 (short circuit condition!)
    if segments_intersect(p1x, p1y, p2x, p2y, p3x, p3y, p4x, p4y):
        # Find intersection point for reporting
        # Using parametric line intersection
        dx1, dy1 = p2x - p1x, p2y - p1y
        dx2, dy2 = p4x - p3x, p4y - p3y
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) > 1e-12:
            t = ((p3x - p1x) * dy2 - (p3y - p1y) * dx2) / denom
            ix = p1x + t * dx1
            iy = p1y + t * dy1
            return 0.0, (ix, iy)
        return 0.0, (p1x, p1y)

    # No intersection: compute minimum distance from endpoints to segments
    d1 = _distance_point_to_segment(p1x, p1y, p3x, p3y, p4x, p4y)
    d2 = _distance_point_to_segment(p2x, p2y, p3x, p3y, p4x, p4y)
    d3 = _distance_point_to_segment(p3x, p3y, p1x, p1y, p2x, p2y)
    d4 = _distance_point_to_segment(p4x, p4y, p1x, p1y, p2x, p2y)

    min_dist = min(d1, d2, d3, d4)
    
    # Determine which endpoint pair gave the minimum and compute closest point on s1
    if min_dist == d1:
        closest_pt = (p1x, p1y)
    elif min_dist == d2:
        closest_pt = (p2x, p2y)
    elif min_dist == d3:
        # p3 is closest to s1, find projection on s1
        dx, dy = p2x - p1x, p2y - p1y
        len_sq = dx * dx + dy * dy
        if len_sq > 0:
            t = max(0.0, min(1.0, ((p3x - p1x) * dx + (p3y - p1y) * dy) / len_sq))
            closest_pt = (p1x + t * dx, p1y + t * dy)
        else:
            closest_pt = (p1x, p1y)
    else:  # d4
        # p4 is closest to s1, find projection on s1
        dx, dy = p2x - p1x, p2y - p1y
        len_sq = dx * dx + dy * dy
        if len_sq > 0:
            t = max(0.0, min(1.0, ((p4x - p1x) * dx + (p4y - p1y) * dy) / len_sq))
            closest_pt = (p1x + t * dx, p1y + t * dy)
        else:
            closest_pt = (p1x, p1y)

    return min_dist, closest_pt


def _bbox_from_segments(segments: list[Segment]) -> dict[str, float] | None:
    """Compute bounding box for a list of segments."""
    if not segments:
        return None
    xs = []
    ys = []
    for s in segments:
        xs.extend([s.x1, s.x2])
        ys.extend([s.y1, s.y2])
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


def _bboxes_overlap(a: dict[str, float], b: dict[str, float], margin: float = 0.0) -> bool:
    """Check if two bounding boxes overlap (with optional margin)."""
    return not (
        a["max_x"] + margin < b["min_x"] - margin or
        b["max_x"] + margin < a["min_x"] - margin or
        a["max_y"] + margin < b["min_y"] - margin or
        b["max_y"] + margin < a["min_y"] - margin
    )


# ---------------------------------------------------------------------------
# Board JSON Loading
# ---------------------------------------------------------------------------


def load_board_json(path: Path | str) -> dict[str, Any]:
    """Load and return the board JSON file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Board JSON not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_routes_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract routes array from board JSON.
    
    The converter may store routes in different locations:
    - board["routes"] - top-level array (primary location)
    - board["routing_geometry"]["copper_routes"] - nested in routing_geometry
    - board["routing_geometry"]["routes"] - alternate nested location
    """
    # Try top-level routes first (post build_board_export)
    routes = board.get("routes", [])
    if routes:
        return routes
    
    # Try routing_geometry nested structure
    routing_geom = board.get("routing_geometry", {})
    if isinstance(routing_geom, dict):
        # Try copper_routes (filtered to copper domain)
        copper_routes = routing_geom.get("copper_routes", [])
        if copper_routes:
            return copper_routes
        
        # Try routes (all routes including non-copper)
        all_routes = routing_geom.get("routes", [])
        if all_routes:
            return all_routes
    
    # Fallback: empty list
    return []


def _extract_nets_from_board(board: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract nets dictionary from board JSON.
    
    Builds a net dictionary from routes, since the board JSON stores connectivity
    as routes with 'net' fields rather than a separate nets array.
    """
    # First try the old format (if nets array exists)
    nets_list = board.get("nets", [])
    if nets_list and isinstance(nets_list, list) and len(nets_list) > 0:
        if isinstance(nets_list[0], dict) and "name" in nets_list[0]:
            return {n.get("name"): n for n in nets_list if n.get("name")}
    
    # Otherwise, build nets from routes
    routes = _extract_routes_from_board(board)
    nets_dict = {}
    
    for route in routes:
        net_name = route.get("net")
        if not net_name:
            continue
        
        if net_name not in nets_dict:
            nets_dict[net_name] = {
                "name": net_name,
                "routes": []
            }
        nets_dict[net_name]["routes"].append(route)
    
    return nets_dict


def _extract_holes_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract holes array from board JSON."""
    return board.get("holes", [])


def _extract_pads_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract pads array from board JSON."""
    # Try top-level first
    pads = board.get("pads", [])
    if pads:
        return pads
    
    # Try routing_geometry nested structure
    routing_geom = board.get("routing_geometry", {})
    if isinstance(routing_geom, dict):
        copper_pads = routing_geom.get("copper_pads", [])
        if copper_pads:
            return copper_pads
        pads_alt = routing_geom.get("pads", [])
        if pads_alt:
            return pads_alt
    
    return []


def _extract_polygons_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract polygons array from board JSON."""
    # Try top-level first
    polygons = board.get("polygons", [])
    if polygons:
        return polygons
    
    # Try routing_geometry nested structure
    routing_geom = board.get("routing_geometry", {})
    if isinstance(routing_geom, dict):
        copper_polygons = routing_geom.get("copper_polygons", [])
        if copper_polygons:
            return copper_polygons
        polygons_alt = routing_geom.get("polygons", [])
        if polygons_alt:
            return polygons_alt
    
    return []


def _get_units(board: dict[str, Any]) -> str:
    """Get the units from board JSON metadata."""
    return board.get("units") or board.get("metadata", {}).get("units") or "MM"


# ---------------------------------------------------------------------------
# API: Trace Width Analysis
# ---------------------------------------------------------------------------


def get_net_segments(board: dict[str, Any], net_name: str) -> NetSegmentStats:
    """Extract all segments for a specific net with width statistics.
    
    Args:
        board: Loaded board JSON dictionary
        net_name: Name of the net to analyze
        
    Returns:
        NetSegmentStats with segment list and width metrics
    """
    routes = _extract_routes_from_board(board)
    stats = NetSegmentStats(net_name=net_name)
    width_counts: dict[float, int] = {}

    for route in routes:
        route_net = route.get("net")
        if route_net and route_net.upper() == net_name.upper():
            points = route.get("points", [])
            # Try multiple possible field names for width
            width = _to_float(
                route.get("line_width") or 
                route.get("width") or 
                route.get("linewidth") or
                route.get("lineWidth")
            )
            layer = route.get("layer") or "unknown"
            route_id = route.get("id")

            # Build segments from consecutive points even without width
            # (width will be None for some routes, which is still useful info)
            prev_pt = None
            for idx, pt in enumerate(points):
                x = _to_float(pt.get("x"))
                y = _to_float(pt.get("y"))
                if x is None or y is None:
                    prev_pt = None
                    continue
                if prev_pt is not None:
                    seg = Segment(
                        x1=prev_pt[0], y1=prev_pt[1],
                        x2=x, y2=y,
                        width=width if width is not None else 0.0,
                        layer=layer,
                        net=net_name,
                        segment_id=f"{route_id}_seg{idx}" if route_id else None
                    )
                    stats.segments.append(seg)
                    stats.total_length += seg.length
                    stats.layers.add(layer)
                    
                    # Track width histogram (only if width is known)
                    if width is not None:
                        w_rounded = round(width, 4)
                        width_counts[w_rounded] = width_counts.get(w_rounded, 0) + 1
                    
                prev_pt = (x, y)

    # Compute statistics
    if stats.segments:
        widths = [s.width for s in stats.segments if s.width > 0]
        if widths:
            stats.min_width = min(widths)
            stats.max_width = max(widths)
            stats.avg_width = sum(widths) / len(widths)
        stats.width_histogram = width_counts
        # Nominal = most common width
        if width_counts:
            stats.nominal_width = max(width_counts, key=width_counts.get)

    return stats


def get_all_net_segments(board: dict[str, Any]) -> dict[str, NetSegmentStats]:
    """Extract segment statistics for all nets in the board.
    
    Args:
        board: Loaded board JSON dictionary
        
    Returns:
        Dictionary mapping net names to their NetSegmentStats
    """
    routes = _extract_routes_from_board(board)
    net_names = set()
    
    for route in routes:
        net = route.get("net")
        if net:
            net_names.add(net)
    
    return {net: get_net_segments(board, net) for net in net_names}


# ---------------------------------------------------------------------------
# API: Clearance Calculation
# ---------------------------------------------------------------------------


def calculate_min_clearance(board: dict[str, Any], net_a: str, net_b: str) -> ClearanceResult:
    """Calculate minimum clearance between two nets using bbox filtering + segment math.
    
    Uses a two-phase approach:
    1. Bounding box check for quick elimination
    2. Point-to-segment distance for precise measurement
    
    Args:
        board: Loaded board JSON dictionary
        net_a: First net name
        net_b: Second net name
        
    Returns:
        ClearanceResult with minimum clearance and location
    """
    stats_a = get_net_segments(board, net_a)
    stats_b = get_net_segments(board, net_b)

    result = ClearanceResult(net_a=net_a, net_b=net_b, min_clearance=None)

    if not stats_a.segments or not stats_b.segments:
        result.calculation_method = "insufficient_data"
        return result

    # Build bboxes per layer for efficient filtering
    layers_a: dict[str, list[Segment]] = {}
    layers_b: dict[str, list[Segment]] = {}

    for seg in stats_a.segments:
        layers_a.setdefault(seg.layer, []).append(seg)
    for seg in stats_b.segments:
        layers_b.setdefault(seg.layer, []).append(seg)

    min_clearance = float("inf")
    closest_location: tuple[float, float] | None = None
    closest_layer: str | None = None
    seg_a_id: str | None = None
    seg_b_id: str | None = None
    total_comparisons = 0

    # Only compare segments on the same layer
    common_layers = set(layers_a.keys()) & set(layers_b.keys())

    for layer in common_layers:
        segs_a = layers_a[layer]
        segs_b = layers_b[layer]

        bbox_a = _bbox_from_segments(segs_a)
        bbox_b = _bbox_from_segments(segs_b)

        if bbox_a is None or bbox_b is None:
            continue

        # Skip if bboxes don't overlap with generous margin
        max_margin = 50.0  # units - generous initial check
        if not _bboxes_overlap(bbox_a, bbox_b, margin=max_margin):
            continue

        # Detailed segment-to-segment comparison
        for sa in segs_a:
            for sb in segs_b:
                total_comparisons += 1
                dist, closest = _segment_to_segment_distance(sa, sb)
                
                # Adjust for trace widths (edge-to-edge clearance clamped to 0.0 on overlap)
                edge_clearance = max(0.0, dist - (sa.width / 2.0) - (sb.width / 2.0))
                
                if edge_clearance < min_clearance:
                    min_clearance = edge_clearance
                    closest_location = closest
                    closest_layer = layer
                    seg_a_id = sa.segment_id
                    seg_b_id = sb.segment_id

    if min_clearance != float("inf"):
        result.min_clearance = round(min_clearance, 6)
        result.clearance_location = closest_location
        result.clearance_layer = closest_layer
        result.segment_a_id = seg_a_id
        result.segment_b_id = seg_b_id
    
    result.segments_compared = total_comparisons
    return result


def calculate_clearances_for_net(board: dict[str, Any], target_net: str, 
                                  critical_nets: list[str] | None = None) -> list[ClearanceResult]:
    """Calculate clearances between a target net and other nets.
    
    Args:
        board: Loaded board JSON dictionary
        target_net: Net to analyze clearances for
        critical_nets: Optional list of specific nets to check against.
                      If None, checks against all nets.
                      
    Returns:
        List of ClearanceResult for each net pair
    """
    all_stats = get_all_net_segments(board)
    results = []

    nets_to_check = critical_nets if critical_nets else list(all_stats.keys())

    for other_net in nets_to_check:
        if other_net.upper() == target_net.upper():
            continue
        result = calculate_min_clearance(board, target_net, other_net)
        results.append(result)

    # Sort by clearance, putting None values at the end
    return sorted(results, key=lambda r: r.min_clearance if r.min_clearance is not None else float("inf"))


# ---------------------------------------------------------------------------
# API: Differential Pair Analysis
# ---------------------------------------------------------------------------


def _detect_differential_pairs(board: dict[str, Any]) -> list[tuple[str, str]]:
    """Auto-detect differential pair candidates based on naming conventions.
    
    Only true differential pairs: _P/_N, +/-, D+/D-, _DP/_DN
    Excludes: _POS/_NEG (single-ended clocks, not differential)
    """
    nets = _extract_nets_from_board(board)
    net_names = list(nets.keys())
    pairs: list[tuple[str, str]] = []
    matched = set()

    patterns = [
        (r"(.+)_P$", r"\1_N"),
        (r"(.+)_N$", r"\1_P"),
        (r"(.+)\+$", r"\1-"),
        (r"(.+)-$", r"\1+"),
        (r"(.+)D\+$", r"\1D-"),
        (r"(.+)D-$", r"\1D+"),
        (r"(.+)_DP$", r"\1_DN"),
        (r"(.+)_DN$", r"\1_DP"),
    ]

    for net in net_names:
        if net in matched:
            continue
        for pattern, complement_pattern in patterns:
            m = re.match(pattern, net, re.IGNORECASE)
            if m:
                base = m.group(1)
                complement = re.sub(pattern, complement_pattern, net)
                # Find matching complement (case-insensitive)
                for other in net_names:
                    if other.upper() == complement.upper() and other not in matched:
                        # Determine P/N ordering
                        if "_P" in net.upper() or "+" in net or "DP" in net.upper():
                            pairs.append((net, other))
                        else:
                            pairs.append((other, net))
                        matched.add(net)
                        matched.add(other)
                        break
                break

    return pairs


def analyze_differential_pair(board: dict[str, Any], net_positive: str, net_negative: str,
                               coupling_threshold: float | None = None) -> DifferentialPairAnalysis:
    """Analyze coupling characteristics of a differential pair.
    
    Calculates edge-to-edge coupling distance and identifies uncoupled sections.
    
    Args:
        board: Loaded board JSON dictionary
        net_positive: Positive net name (e.g., "CLK_P")
        net_negative: Negative net name (e.g., "CLK_N")
        coupling_threshold: Maximum edge-to-edge distance (in board units) 
                           to consider "coupled". Default None (auto-detect from units).
                           
    Returns:
        DifferentialPairAnalysis with coupling metrics
    """
    # Determine the unit-aware threshold
    board_units = _get_units(board).upper()
    if coupling_threshold is None:
        if board_units == "INCH":
            coupling_threshold = 0.5 / 25.4
        else:
            coupling_threshold = 0.5
    
    stats_p = get_net_segments(board, net_positive)
    stats_n = get_net_segments(board, net_negative)

    analysis = DifferentialPairAnalysis(
        net_positive=net_positive,
        net_negative=net_negative,
        total_length_positive=stats_p.total_length,
        total_length_negative=stats_n.total_length
    )

    # Length mismatch
    if stats_p.total_length > 0 and stats_n.total_length > 0:
        analysis.length_mismatch = abs(stats_p.total_length - stats_n.total_length)
        avg_length = (stats_p.total_length + stats_n.total_length) / 2.0
        analysis.length_mismatch_percent = (analysis.length_mismatch / avg_length) * 100.0 if avg_length > 0 else 0.0

    if not stats_p.segments or not stats_n.segments:
        analysis.coupling_quality = "insufficient_data"
        return analysis

    # Group segments by layer
    layers_p: dict[str, list[Segment]] = {}
    layers_n: dict[str, list[Segment]] = {}

    for seg in stats_p.segments:
        layers_p.setdefault(seg.layer, []).append(seg)
    for seg in stats_n.segments:
        layers_n.setdefault(seg.layer, []).append(seg)

    coupling_distances: list[float] = []
    coupled_distances: list[float] = []
    coupled_length = 0.0
    uncoupled_length = 0.0

    common_layers = set(layers_p.keys()) & set(layers_n.keys())

    for layer in common_layers:
        segs_p = layers_p[layer]
        segs_n = layers_n[layer]

        # For each P segment, find nearest N segment
        for sp in segs_p:
            min_dist = float("inf")
            best_sn = None

            for sn in segs_n:
                dist, _ = _segment_to_segment_distance(sp, sn)
                # Edge-to-edge distance
                edge_dist = dist - (sp.width / 2.0) - (sn.width / 2.0)
                if edge_dist < min_dist:
                    min_dist = edge_dist
                    best_sn = sn

            if min_dist != float("inf"):
                coupling_distances.append(min_dist)
                
                if min_dist <= coupling_threshold:
                    coupled_distances.append(min_dist)
                    coupled_length += sp.length
                    analysis.coupled_sections.append({
                        "layer": layer,
                        "segment_p": sp.segment_id,
                        "segment_n": best_sn.segment_id if best_sn else None,
                        "coupling_distance": round(min_dist, 4),
                        "length": round(sp.length, 4)
                    })
                else:
                    uncoupled_length += sp.length
                    analysis.uncoupled_sections.append({
                        "layer": layer,
                        "segment_p": sp.segment_id,
                        "nearest_n": best_sn.segment_id if best_sn else None,
                        "distance": round(min_dist, 4),
                        "length": round(sp.length, 4),
                        "reason": "exceeds_coupling_threshold"
                    })

    analysis.uncoupled_length = uncoupled_length

    # Use length-weighted average to prevent breakout transitions from skewing coupling distance
    if analysis.coupled_sections:
        total_coupled_len = sum(sec["length"] for sec in analysis.coupled_sections)
        if total_coupled_len > 0:
            weighted_sum = sum(sec["coupling_distance"] * sec["length"] for sec in analysis.coupled_sections)
            analysis.avg_coupling_distance = weighted_sum / total_coupled_len
        else:
            # Fallback to simple average if lengths are zero
            analysis.avg_coupling_distance = sum(coupled_distances) / len(coupled_distances) if coupled_distances else None
    else:
        analysis.avg_coupling_distance = None

    if coupling_distances:
        analysis.min_coupling_distance = min(coupling_distances)
        analysis.max_coupling_distance = max(coupling_distances)

        # Quality assessment
        total = coupled_length + uncoupled_length
        if total > 0:
            coupled_pct = (coupled_length / total) * 100.0
            if coupled_pct >= 90:
                analysis.coupling_quality = "good"
            elif coupled_pct >= 70:
                analysis.coupling_quality = "marginal"
            else:
                analysis.coupling_quality = "poor"

    return analysis


def analyze_all_differential_pairs(board: dict[str, Any], 
                                    coupling_threshold: float | None = None) -> list[DifferentialPairAnalysis]:
    """Auto-detect and analyze all differential pairs in the board.
    
    Args:
        board: Loaded board JSON dictionary
        coupling_threshold: Maximum coupled distance in board units (None = auto-detect)
        
    Returns:
        List of DifferentialPairAnalysis for each detected pair
    """
    pairs = _detect_differential_pairs(board)
    return [analyze_differential_pair(board, p, n, coupling_threshold) for p, n in pairs]


# ---------------------------------------------------------------------------
# API: NPTH Clearance Analysis
# ---------------------------------------------------------------------------


def check_npth_clearance(board: dict[str, Any], 
                          keepout_radius: float = 4.0) -> NPTHClearanceResult:
    """Check copper clearance around Non-Plated Through Holes.
    
    Per Appendix K.6: 4mm copper keepout around NPTH mounting holes
    prevents uncontrolled chassis ground paths.
    
    Args:
        board: Loaded board JSON dictionary
        keepout_radius: Required clearance radius in mm (default 4.0mm)
        
    Returns:
        NPTHClearanceResult with violations and pass status
    """
    holes = _extract_holes_from_board(board)
    pads = _extract_pads_from_board(board)
    routes = _extract_routes_from_board(board)
    polygons = _extract_polygons_from_board(board)
    units = _get_units(board)

    # Convert threshold to board units
    threshold = keepout_radius
    if units.upper() == "INCH":
        threshold = keepout_radius / 25.4  # Convert mm to inches
    
    # Filter to non-plated holes
    npth_holes = [
        h for h in holes 
        if (h.get("plating_status") or "").upper() == "NONPLATED" or
           h.get("hole_type") == "nonplated_hole"
    ]

    result = NPTHClearanceResult(
        npth_count=len(npth_holes),
        analyzed_count=0,
        keepout_radius=keepout_radius,
        keepout_units=units
    )

    for hole in npth_holes:
        hx = _to_float(hole.get("x"))
        hy = _to_float(hole.get("y"))
        hd = _to_float(hole.get("diameter")) or 0.0
        hole_id = hole.get("id") or f"npth_{hx}_{hy}"

        if hx is None or hy is None:
            continue

        result.analyzed_count += 1
        hole_has_violation = False

        # Check pads within keepout zone
        for pad in pads:
            # Only copper domain
            if pad.get("feature_domain") not in (None, "copper"):
                continue
            px = _to_float(pad.get("x"))
            py = _to_float(pad.get("y"))
            if px is None or py is None:
                continue
            pad_w = _to_float(pad.get("width")) or _to_float(pad.get("diameter")) or 0.0
            pad_h = _to_float(pad.get("height")) or pad_w
            # Approximate bounding radius of the pad
            pad_radius = max(pad_w, pad_h) / 2.0 
            
            dist_center = math.hypot(px - hx, py - hy)
            edge_dist = max(0.0, dist_center - pad_radius)
            
            if edge_dist < threshold:
                hole_has_violation = True
                severity = "critical" if edge_dist < threshold / 2 else "warning"
                result.violations.append(NPTHClearanceViolation(
                    hole_id=hole_id,
                    hole_x=hx,
                    hole_y=hy,
                    hole_diameter=hd,
                    feature_type="pad",
                    feature_id=pad.get("id"),
                    feature_net=pad.get("net"),
                    feature_layer=pad.get("layer") or "unknown",
                    distance_to_hole=round(edge_dist, 4),
                    keepout_radius=keepout_radius,
                    violation_severity=severity
                ))

        # Check route segments within keepout zone
        for route in routes:
            if route.get("feature_domain") not in (None, "copper"):
                continue
            
            points = route.get("points", [])
            route_width = _to_float(route.get("line_width") or route.get("width") or 0.0)
            route_violation_found = False
            prev_pt = None
            
            for pt in points:
                rx = _to_float(pt.get("x"))
                ry = _to_float(pt.get("y"))
                if rx is None or ry is None:
                    prev_pt = None
                    continue
                
                if prev_pt is not None:
                    px1, py1 = prev_pt
                    px2, py2 = rx, ry
                    
                    # Compute shortest distance from NPTH center to the trace segment
                    dist = _distance_point_to_segment(hx, hy, px1, py1, px2, py2)
                    edge_dist = dist - (route_width / 2.0)
                    
                    if edge_dist < threshold:
                        hole_has_violation = True
                        route_violation_found = True
                        severity = "critical" if edge_dist < threshold / 2 else "warning"
                        result.violations.append(NPTHClearanceViolation(
                            hole_id=hole_id,
                            hole_x=hx,
                            hole_y=hy,
                            hole_diameter=hd,
                            feature_type="route",
                            feature_id=route.get("id"),
                            feature_net=route.get("net"),
                            feature_layer=route.get("layer") or "unknown",
                            distance_to_hole=round(edge_dist, 4),
                            keepout_radius=keepout_radius,
                            violation_severity=severity
                        ))
                        break  # One violation per route is enough
                prev_pt = (rx, ry)
                if route_violation_found:
                    break

        # Check polygon edges (all of them) against the keepout zone
        for poly in polygons:
            if poly.get("feature_domain") not in (None, "copper"):
                continue
            
            # Quick bbox check first for efficiency
            bbox = poly.get("bbox")
            if bbox:
                if not (bbox.get("min_x", 0) - keepout_radius <= hx <= bbox.get("max_x", 0) + keepout_radius and
                        bbox.get("min_y", 0) - keepout_radius <= hy <= bbox.get("max_y", 0) + keepout_radius):
                    continue
            
            # Check all polygon edge segments for proximity to NPTH hole
            points = poly.get("points", [])
            poly_violation_found = False
            for i in range(len(points)):
                pt1 = points[i]
                pt2 = points[(i + 1) % len(points)]  # Wrap to close polygon
                px1, py1 = _to_float(pt1.get("x")), _to_float(pt1.get("y"))
                px2, py2 = _to_float(pt2.get("x")), _to_float(pt2.get("y"))
                if px1 is None or py1 is None or px2 is None or py2 is None:
                    continue
                
                # Distance from hole center to polygon edge segment
                dist = _distance_point_to_segment(hx, hy, px1, py1, px2, py2)
                if dist < threshold:
                    hole_has_violation = True
                    poly_violation_found = True
                    severity = "critical" if dist < threshold / 2 else "warning"
                    result.violations.append(NPTHClearanceViolation(
                        hole_id=hole_id,
                        hole_x=hx,
                        hole_y=hy,
                        hole_diameter=hd,
                        feature_type="polygon",
                        feature_id=poly.get("id"),
                        feature_net=poly.get("net"),
                        feature_layer=poly.get("layer") or "unknown",
                        distance_to_hole=round(dist, 4),
                        keepout_radius=keepout_radius,
                        violation_severity=severity
                    ))
                    break  # One violation per polygon is enough
            
            if poly_violation_found:
                break  # One polygon violation per hole is enough for reporting

        if not hole_has_violation:
            result.clean_holes.append(hole_id)

    result.pass_status = len(result.violations) == 0
    return result


# ---------------------------------------------------------------------------
# API: Ampacity / Current Capacity Helper
# ---------------------------------------------------------------------------


def calculate_trace_ampacity(width_mm: float, thickness_oz: float = 1.0, 
                              temp_rise_c: float = 10.0, is_internal: bool = False) -> float:
    """Calculate trace current capacity using IPC-2221 simplified formula.
    
    This is a simplified approximation. For critical designs, use proper
    IPC-2152 calculations or thermal simulation.
    
    Args:
        width_mm: Trace width in millimeters
        thickness_oz: Copper thickness in oz/ft² (1 oz ≈ 35 µm)
        temp_rise_c: Allowable temperature rise in °C
        is_internal: True for internal layers (derated)
        
    Returns:
        Estimated current capacity in Amperes
    """
    # Convert width to mils (IPC-2221 uses mils)
    width_mils = width_mm * 39.3701
    # Copper thickness in mils (1 oz ≈ 1.37 mils)
    thickness_mils = thickness_oz * 1.37
    # Cross-sectional area in mil²
    area = width_mils * thickness_mils

    # IPC-2221 simplified formula: I = k * (dT^b) * (A^c)
    # External: k=0.048, b=0.44, c=0.725
    # Internal: k=0.024, b=0.44, c=0.725
    k = 0.024 if is_internal else 0.048
    b = 0.44
    c = 0.725

    current = k * (temp_rise_c ** b) * (area ** c)
    return round(current, 2)


def verify_trace_ampacity(board: dict[str, Any], net_name: str, 
                           required_current_a: float,
                           copper_oz: float = 1.0,
                           temp_rise_c: float = 10.0) -> dict[str, Any]:
    """Verify that a net's traces can carry the required current.
    
    Args:
        board: Loaded board JSON dictionary
        net_name: Net to verify
        required_current_a: Required current in Amperes
        copper_oz: Copper thickness in oz
        temp_rise_c: Allowable temperature rise
        
    Returns:
        Dict with verification results and any violations
    """
    stats = get_net_segments(board, net_name)
    
    if not stats.segments:
        return {
            "net": net_name,
            "pass": False,
            "reason": "no_segments_found",
            "required_current_a": required_current_a
        }

    violations = []
    min_capacity = float("inf")

    for seg in stats.segments:
        # Determine if internal (simple heuristic based on layer name)
        is_internal = seg.layer.upper() not in ("TOP", "BOTTOM", "L1", "L2")
        capacity = calculate_trace_ampacity(seg.width, copper_oz, temp_rise_c, is_internal)
        min_capacity = min(min_capacity, capacity)
        
        if capacity < required_current_a:
            violations.append({
                "segment_id": seg.segment_id,
                "layer": seg.layer,
                "width_mm": seg.width,
                "capacity_a": capacity,
                "required_a": required_current_a,
                "deficit_a": round(required_current_a - capacity, 2)
            })

    return {
        "net": net_name,
        "pass": len(violations) == 0,
        "required_current_a": required_current_a,
        "min_capacity_a": round(min_capacity, 2) if min_capacity != float("inf") else None,
        "violation_count": len(violations),
        "violations": violations,
        "copper_oz": copper_oz,
        "temp_rise_c": temp_rise_c
    }


# ---------------------------------------------------------------------------
# API: Via Annular Ring Analysis (DFM_VIA_001, DFM_VIA_003, DFM_VIA_004)
# ---------------------------------------------------------------------------


@dataclass
class AnnularRingViolation:
    """A via with insufficient annular ring."""
    via_id: str
    x: float
    y: float
    pad_diameter: float
    drill_diameter: float
    annular_ring: float
    layer: str
    severity: str  # critical, warning


@dataclass
class AnnularRingResult:
    """Results of annular ring analysis."""
    via_count: int
    analyzed_count: int
    threshold_mm: float
    units: str
    violations: list[AnnularRingViolation] = field(default_factory=list)
    pass_status: bool = True


def _extract_vias_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract vias array from board JSON."""
    # Try top-level vias
    vias = board.get("vias", [])
    if vias:
        return vias
    
    # Try routing_geometry nested structure
    routing_geom = board.get("routing_geometry", {})
    if isinstance(routing_geom, dict):
        return routing_geom.get("vias", [])
    
    return []


def check_via_annular_rings(board: dict[str, Any], 
                            min_ring_mm: float = 0.127) -> AnnularRingResult:
    """Check that all vias have sufficient annular ring.
    
    Annular Ring = (Pad Diameter - Drill Diameter) / 2
    
    Per DFM_VIA_001, DFM_VIA_003, DFM_VIA_004: minimum 5 mils (0.127mm)
    annular ring is required for reliable plating and connection.
    
    Args:
        board: Loaded board JSON dictionary
        min_ring_mm: Minimum annular ring threshold in mm (default: 0.127mm = 5 mils)
        
    Returns:
        AnnularRingResult with violations and pass status
    """
    vias = _extract_vias_from_board(board)
    pads = _extract_pads_from_board(board)
    units = _get_units(board)
    
    # Convert threshold if board uses inches
    threshold = min_ring_mm
    if units.upper() == "INCH":
        threshold = min_ring_mm / 25.4  # Convert mm to inches
    
    result = AnnularRingResult(
        via_count=len(vias),
        analyzed_count=0,
        threshold_mm=min_ring_mm,
        units=units
    )
    
    # Check vias array by cross-referencing pads at same coordinates
    for via in vias:
        vx = _to_float(via.get("x"))
        vy = _to_float(via.get("y"))
        drill = _to_float(via.get("drill") or via.get("drill_diameter") or via.get("hole_diameter"))
        
        if vx is None or vy is None or drill is None:
            continue
        
        # Via object doesn't contain pad diameter - look it up in pads array
        # Find pads at this via's coordinates (within 0.001 tolerance)
        matching_pads = [
            p for p in pads 
            if abs(_to_float(p.get("x", 0)) - vx) < 0.001 
            and abs(_to_float(p.get("y", 0)) - vy) < 0.001
        ]
        
        if not matching_pads:
            continue  # No pad data for this via
        
        # Use the first matching pad (they should all have same diameter for a via)
        pad = matching_pads[0]
        pad_dia = _to_float(
            pad.get("resolved_diameter") or 
            pad.get("diameter") or 
            pad.get("pad_diameter") or 
            pad.get("width")
        )
        
        if pad_dia is None:
            continue
        
        result.analyzed_count += 1
        ring = (pad_dia - drill) / 2.0
        
        if ring < threshold:
            severity = "critical" if ring < (threshold * 0.5) else "warning"
            result.violations.append(AnnularRingViolation(
                via_id=via.get("name") or via.get("id") or f"via_{vx:.4f}_{vy:.4f}",
                x=vx,
                y=vy,
                pad_diameter=pad_dia,
                drill_diameter=drill,
                annular_ring=round(ring, 5),
                layer="all",  # Vias span all layers
                severity=severity
            ))
    
    # Also check PTH pads with drill holes
    for pad in pads:
        drill = _to_float(pad.get("drill") or pad.get("drill_diameter") or pad.get("hole_diameter"))
        if drill is None or drill <= 0:
            continue  # Not a through-hole pad
        
        px = _to_float(pad.get("x"))
        py = _to_float(pad.get("y"))
        pad_dia = _to_float(pad.get("diameter") or pad.get("width"))
        
        if px is None or py is None or pad_dia is None:
            continue
        
        result.via_count += 1
        result.analyzed_count += 1
        ring = (pad_dia - drill) / 2.0
        
        if ring < threshold:
            severity = "critical" if ring < (threshold * 0.5) else "warning"
            result.violations.append(AnnularRingViolation(
                via_id=pad.get("id") or f"pad_{px:.4f}_{py:.4f}",
                x=px,
                y=py,
                pad_diameter=pad_dia,
                drill_diameter=drill,
                annular_ring=round(ring, 5),
                layer=pad.get("layer") or "all",
                severity=severity
            ))
    
    result.pass_status = len(result.violations) == 0
    return result


# ---------------------------------------------------------------------------
# API: Acid Trap Detection (DFM_ACID_001)
# ---------------------------------------------------------------------------


@dataclass
class AcidTrap:
    """An acute angle trace bend that may trap etchant."""
    route_id: str
    net: str
    layer: str
    vertex_x: float
    vertex_y: float
    angle_deg: float
    severity: str


@dataclass
class AcidTrapResult:
    """Results of acid trap detection."""
    routes_analyzed: int
    vertices_analyzed: int
    angle_threshold_deg: float
    traps: list[AcidTrap] = field(default_factory=list)
    pass_status: bool = True


def detect_acid_traps(board: dict[str, Any], 
                      angle_threshold_deg: float = 70.0) -> AcidTrapResult:
    """Detect acute trace bends that form potential acid/etchant traps.
    
    Per DFM_ACID_001: Acute angles (< 70°) in trace routing can trap
    etchant during PCB manufacturing, causing under-etching or over-etching.
    
    Args:
        board: Loaded board JSON dictionary
        angle_threshold_deg: Angle threshold in degrees (default: 70°)
        
    Returns:
        AcidTrapResult with detected traps and pass status
    """
    routes = _extract_routes_from_board(board)
    
    result = AcidTrapResult(
        routes_analyzed=len(routes),
        vertices_analyzed=0,
        angle_threshold_deg=angle_threshold_deg
    )
    
    for route in routes:
        points = route.get("points", [])
        if len(points) < 3:
            continue
        
        net = route.get("net") or "unnamed"
        layer = route.get("layer") or "unknown"
        route_id = route.get("id") or "unknown"
        
        for i in range(len(points) - 2):
            p1, p2, p3 = points[i], points[i+1], points[i+2]
            x1, y1 = _to_float(p1.get("x")), _to_float(p1.get("y"))
            x2, y2 = _to_float(p2.get("x")), _to_float(p2.get("y"))
            x3, y3 = _to_float(p3.get("x")), _to_float(p3.get("y"))
            
            if None in (x1, y1, x2, y2, x3, y3):
                continue
            
            result.vertices_analyzed += 1
            
            # Vectors from middle vertex to adjacent vertices
            v1x, v1y = x1 - x2, y1 - y2
            v2x, v2y = x3 - x2, y3 - y2
            
            # Calculate angle using dot product
            dot = v1x * v2x + v1y * v2y
            mag1 = math.hypot(v1x, v1y)
            mag2 = math.hypot(v2x, v2y)
            
            if mag1 == 0 or mag2 == 0:
                continue
            
            cos_theta = max(-1.0, min(1.0, dot / (mag1 * mag2)))
            angle_rad = math.acos(cos_theta)
            angle_deg = math.degrees(angle_rad)
            
            if angle_deg <= angle_threshold_deg:
                severity = "critical" if angle_deg <= 45.0 else "warning"
                result.traps.append(AcidTrap(
                    route_id=route_id,
                    net=net,
                    layer=layer,
                    vertex_x=x2,
                    vertex_y=y2,
                    angle_deg=round(angle_deg, 2),
                    severity=severity
                ))
    
    result.pass_status = len(result.traps) == 0
    return result


# ---------------------------------------------------------------------------
# API: Board Edge Clearance (DFM_EDGE_001, DFM_PANEL_001)
# ---------------------------------------------------------------------------


@dataclass
class EdgeClearanceViolation:
    """A copper feature too close to the board edge."""
    feature_type: str  # pad, route, polygon
    feature_id: str | None
    feature_net: str | None
    feature_layer: str
    feature_x: float
    feature_y: float
    distance_to_edge: float
    severity: str


@dataclass
class EdgeClearanceResult:
    """Results of board edge clearance analysis."""
    outline_found: bool
    outline_segment_count: int
    threshold_mm: float
    units: str
    violations: list[EdgeClearanceViolation] = field(default_factory=list)
    pass_status: bool = True


def _extract_outline_from_board(board: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract board outline segments from board JSON."""
    # Try top-level outline
    outline = board.get("outline", [])
    if outline:
        return outline
    
    # Try board_outline key
    board_outline = board.get("board_outline", [])
    if board_outline:
        return board_outline
    
    # Try routing_geometry nested structure
    routing_geom = board.get("routing_geometry", {})
    if isinstance(routing_geom, dict):
        outline_alt = routing_geom.get("outline", [])
        if outline_alt:
            return outline_alt
    
    return []


def _outline_to_segments(outline: list[dict[str, Any]]) -> list[tuple[float, float, float, float]]:
    """Convert outline data to list of line segments (x1, y1, x2, y2)."""
    segments = []
    
    # Format 0: Flat list of points [{"x": "1.0", "y": "2.0"}, ...] - most common from converter
    if outline and all("x" in item and "y" in item for item in outline if isinstance(item, dict)):
        # Check if it's a flat point list (not segments with x1/y1/x2/y2)
        if not any("x1" in item or "x2" in item or "start" in item or "points" in item for item in outline):
            # Convert point list to segments
            for i in range(len(outline)):
                pt1 = outline[i]
                pt2 = outline[(i + 1) % len(outline)]
                x1 = _to_float(pt1.get("x"))
                y1 = _to_float(pt1.get("y"))
                x2 = _to_float(pt2.get("x"))
                y2 = _to_float(pt2.get("y"))
                if None not in (x1, y1, x2, y2):
                    segments.append((x1, y1, x2, y2))
            return segments
    
    # Handle different outline formats
    for item in outline:
        # Format 1: {"x1", "y1", "x2", "y2"} - direct segment
        x1, y1 = _to_float(item.get("x1")), _to_float(item.get("y1"))
        x2, y2 = _to_float(item.get("x2")), _to_float(item.get("y2"))
        if None not in (x1, y1, x2, y2):
            segments.append((x1, y1, x2, y2))
            continue
        
        # Format 2: {"start": {"x", "y"}, "end": {"x", "y"}}
        start = item.get("start", {})
        end = item.get("end", {})
        x1 = _to_float(start.get("x"))
        y1 = _to_float(start.get("y"))
        x2 = _to_float(end.get("x"))
        y2 = _to_float(end.get("y"))
        if None not in (x1, y1, x2, y2):
            segments.append((x1, y1, x2, y2))
            continue
        
        # Format 3: {"points": [{"x", "y"}, ...]} - polygon points
        points = item.get("points", [])
        if points:
            for i in range(len(points)):
                pt1 = points[i]
                pt2 = points[(i + 1) % len(points)]
                x1 = _to_float(pt1.get("x"))
                y1 = _to_float(pt1.get("y"))
                x2 = _to_float(pt2.get("x"))
                y2 = _to_float(pt2.get("y"))
                if None not in (x1, y1, x2, y2):
                    segments.append((x1, y1, x2, y2))
    
    return segments


def check_board_edge_clearance(board: dict[str, Any], 
                                min_clearance_mm: float = 0.635,
                                ground_clearance_mm: float = 0.635,
                                power_clearance_mm: float = 1.27,
                                signal_clearance_mm: float = 1.27) -> EdgeClearanceResult:
    """Check copper features maintain minimum clearance from board edge.
    
    Per DFM_EDGE_001, HS_DIFF_005: Copper features must maintain adequate
    clearance from board edges. Industry standards:
    - Ground planes: 25 mils (0.635mm)
    - Power planes/signals: 50 mils (1.27mm)
    - High-speed traces: 10-15 mils (0.25-0.38mm)
    
    Uses schematic analysis data (board["analysis"]["power_nets"], etc.) when
    available for accurate net classification.
    
    Args:
        board: Loaded board JSON dictionary
        min_clearance_mm: Default minimum clearance (default: 0.635mm = 25 mils)
        ground_clearance_mm: Clearance for ground nets (default: 0.635mm = 25 mils)
        power_clearance_mm: Clearance for power nets (default: 1.27mm = 50 mils)
        signal_clearance_mm: Clearance for signal nets (default: 1.27mm = 50 mils)
        
    Returns:
        EdgeClearanceResult with violations and pass status
    """
    outline = _extract_outline_from_board(board)
    outline_segments = _outline_to_segments(outline)
    pads = _extract_pads_from_board(board)
    routes = _extract_routes_from_board(board)
    units = _get_units(board)
    
    # Extract schematic analysis data
    analysis = board.get("analysis", {})
    power_nets = set(analysis.get("power_nets", []))
    ground_nets = set(analysis.get("ground_nets", []))
    clock_nets = set(analysis.get("clock_nets", []))
    
    # Helper to determine net type and required clearance
    def get_required_clearance(net_name: str | None) -> float:
        """Return required clearance in mm based on net type."""
        if not net_name:
            return min_clearance_mm
        
        # Use schematic analysis first (most accurate)
        if net_name in ground_nets:
            return ground_clearance_mm
        if net_name in power_nets:
            return power_clearance_mm
        
        # Fallback to regex patterns if not in schematic analysis
        net_upper = net_name.upper()
        
        # Ground nets (fallback)
        if any(pattern in net_upper for pattern in ["GND", "GROUND", "AGND", "DGND", "VSS"]):
            return ground_clearance_mm
        
        # Power nets (fallback - same regex as verify_trace_temperature)
        power_patterns = [
            r"VCC", r"VDD", r"VBUS", r"VSYS", r"VBAT", r"VPP", r"VREF",
            r"AVDD", r"DVDD", r"\bV\d+P\d+", r"\b\d+V\d*\b", r"\b\+?\d+(\.\d+)?V\b",
            r"\bV\d+[P\._]\d+V\b"
        ]
        import re
        if any(re.search(pattern, net_upper) for pattern in power_patterns):
            return power_clearance_mm
        
        # All other signals
        return signal_clearance_mm
    
    # Convert thresholds to board units
    def to_board_units(mm: float) -> float:
        return mm / 25.4 if units.upper() == "INCH" else mm
    
    result = EdgeClearanceResult(
        outline_found=len(outline_segments) > 0,
        outline_segment_count=len(outline_segments),
        threshold_mm=min_clearance_mm,
        units=units
    )
    
    if not outline_segments:
        result.pass_status = True  # Cannot check without outline
        return result
    
    def min_distance_to_outline(px: float, py: float) -> float:
        """Calculate minimum distance from point to any outline segment."""
        min_dist = float("inf")
        for (x1, y1, x2, y2) in outline_segments:
            dist = _distance_point_to_segment(px, py, x1, y1, x2, y2)
            min_dist = min(min_dist, dist)
        return min_dist
    
    # Check pads
    for pad in pads:
        if pad.get("feature_domain") not in (None, "copper"):
            continue
        px = _to_float(pad.get("x"))
        py = _to_float(pad.get("y"))
        if px is None or py is None:
            continue
        
        net_name = pad.get("net")
        required_clearance_mm = get_required_clearance(net_name)
        threshold = to_board_units(required_clearance_mm)
        
        dist = min_distance_to_outline(px, py)
        if dist < threshold:
            severity = "critical" if dist < threshold * 0.5 else "warning"
            result.violations.append(EdgeClearanceViolation(
                feature_type="pad",
                feature_id=pad.get("id"),
                feature_net=net_name,
                feature_layer=pad.get("layer") or "unknown",
                feature_x=px,
                feature_y=py,
                distance_to_edge=round(dist, 5),
                severity=severity
            ))
    
    # Check route vertices
    for route in routes:
        net = route.get("net")
        layer = route.get("layer") or "unknown"
        route_id = route.get("id")
        
        required_clearance_mm = get_required_clearance(net)
        threshold = to_board_units(required_clearance_mm)
        
        for pt in route.get("points", []):
            rx = _to_float(pt.get("x"))
            ry = _to_float(pt.get("y"))
            if rx is None or ry is None:
                continue
            
            dist = min_distance_to_outline(rx, ry)
            if dist < threshold:
                severity = "critical" if dist < threshold * 0.5 else "warning"
                result.violations.append(EdgeClearanceViolation(
                    feature_type="route",
                    feature_id=route_id,
                    feature_net=net,
                    feature_layer=layer,
                    feature_x=rx,
                    feature_y=ry,
                    distance_to_edge=round(dist, 5),
                    severity=severity
                ))
                break  # One violation per route segment
    
    result.pass_status = len(result.violations) == 0
    return result


# ---------------------------------------------------------------------------
# API: Copper Balance Estimation (DFM_COPPER_001)
# ---------------------------------------------------------------------------


@dataclass
class LayerCopperArea:
    """Estimated copper area for a single layer."""
    layer_name: str
    route_area: float
    pad_area: float
    polygon_area: float
    total_area: float


@dataclass
class CopperBalanceWarning:
    """A symmetric layer pair with imbalanced copper."""
    layer_a: str
    layer_b: str
    area_a: float
    area_b: float
    imbalance_percent: float


@dataclass
class CopperBalanceResult:
    """Results of copper balance estimation."""
    layer_areas: list[LayerCopperArea] = field(default_factory=list)
    layer_pairs_checked: int = 0
    imbalance_threshold_pct: float = 25.0
    warnings: list[CopperBalanceWarning] = field(default_factory=list)
    pass_status: bool = True
    units: str = "unknown"


def estimate_copper_balance(board: dict[str, Any], 
                            imbalance_threshold_pct: float = 25.0) -> CopperBalanceResult:
    """Estimate copper area per layer and check for imbalance.
    
    Per DFM_COPPER_001: Symmetric copper distribution across layer pairs
    prevents board warping during thermal cycles (reflow, operation).
    
    Args:
        board: Loaded board JSON dictionary
        imbalance_threshold_pct: Maximum allowed imbalance percentage (default: 25%)
        
    Returns:
        CopperBalanceResult with layer areas and imbalance warnings
    """
    routes = _extract_routes_from_board(board)
    pads = _extract_pads_from_board(board)
    polygons = _extract_polygons_from_board(board)
    units = _get_units(board)
    
    result = CopperBalanceResult(
        imbalance_threshold_pct=imbalance_threshold_pct,
        units=units
    )
    
    layer_route_area: dict[str, float] = {}
    layer_pad_area: dict[str, float] = {}
    layer_polygon_area: dict[str, float] = {}
    
    # Calculate route segment areas (length * width)
    for route in routes:
        layer = route.get("layer") or "unknown"
        width = _to_float(route.get("line_width") or route.get("width") or route.get("linewidth"))
        if width is None:
            width = 0.0
        
        points = route.get("points", [])
        prev_pt = None
        segment_area = 0.0
        
        for pt in points:
            rx = _to_float(pt.get("x"))
            ry = _to_float(pt.get("y"))
            if rx is None or ry is None:
                continue
            
            if prev_pt is not None:
                length = math.hypot(rx - prev_pt[0], ry - prev_pt[1])
                segment_area += length * width
            prev_pt = (rx, ry)
        
        layer_route_area[layer] = layer_route_area.get(layer, 0.0) + segment_area
    
    # Calculate pad areas (approximate as circles/rectangles)
    for pad in pads:
        if pad.get("feature_domain") not in (None, "copper"):
            continue
        
        layer = pad.get("layer") or "unknown"
        shape = pad.get("shape", "").lower()
        
        diameter = _to_float(pad.get("diameter"))
        width = _to_float(pad.get("width"))
        height = _to_float(pad.get("height"))
        
        pad_area = 0.0
        if diameter:
            pad_area = math.pi * (diameter / 2.0) ** 2
        elif width and height:
            pad_area = width * height
        elif width:
            pad_area = width * width  # Assume square
        
        layer_pad_area[layer] = layer_pad_area.get(layer, 0.0) + pad_area
    
    # Calculate polygon areas (using simple bounding box approximation)
    for poly in polygons:
        if poly.get("feature_domain") not in (None, "copper"):
            continue
        
        layer = poly.get("layer") or "unknown"
        points = poly.get("points", [])
        
        if len(points) < 3:
            continue
        
        # Use bounding box approximation (could use shoelace formula for exact area)
        xs = [_to_float(p.get("x")) for p in points if _to_float(p.get("x")) is not None]
        ys = [_to_float(p.get("y")) for p in points if _to_float(p.get("y")) is not None]
        
        if xs and ys:
            bbox_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            # Approximate polygon as 70% of bounding box
            layer_polygon_area[layer] = layer_polygon_area.get(layer, 0.0) + bbox_area * 0.7
    
    # Build per-layer totals
    all_layers = set(layer_route_area.keys()) | set(layer_pad_area.keys()) | set(layer_polygon_area.keys())
    
    for layer in sorted(all_layers):
        route_a = layer_route_area.get(layer, 0.0)
        pad_a = layer_pad_area.get(layer, 0.0)
        poly_a = layer_polygon_area.get(layer, 0.0)
        total = route_a + pad_a + poly_a
        
        result.layer_areas.append(LayerCopperArea(
            layer_name=layer,
            route_area=round(route_a, 6),
            pad_area=round(pad_a, 6),
            polygon_area=round(poly_a, 6),
            total_area=round(total, 6)
        ))
    
    # Check symmetric layer pairs
    # Common naming: TOP/BOTTOM, L1/L4, L2/L3, etc.
    layer_totals = {la.layer_name: la.total_area for la in result.layer_areas}
    
    # Define common symmetric pairs to check
    symmetric_pairs = [
        ("TOP", "BOTTOM"),
        ("L1", "L6"),
        ("L1", "L4"),
        ("L2", "L5"),
        ("L2", "L3"),
        ("LAYER2", "LAYER5"),
        ("LAYER3", "LAYER4"),
    ]
    
    for layer_a, layer_b in symmetric_pairs:
        area_a = layer_totals.get(layer_a)
        area_b = layer_totals.get(layer_b)
        
        if area_a is not None and area_b is not None and (area_a + area_b) > 0:
            result.layer_pairs_checked += 1
            avg_area = (area_a + area_b) / 2.0
            imbalance = abs(area_a - area_b) / avg_area * 100.0 if avg_area > 0 else 0.0
            
            if imbalance > imbalance_threshold_pct:
                result.warnings.append(CopperBalanceWarning(
                    layer_a=layer_a,
                    layer_b=layer_b,
                    area_a=round(area_a, 6),
                    area_b=round(area_b, 6),
                    imbalance_percent=round(imbalance, 2)
                ))
    
    result.pass_status = len(result.warnings) == 0
    return result


# ---------------------------------------------------------------------------
# Physical-Math Verification (Saturn Engine Integration)
# ---------------------------------------------------------------------------

try:
    from saturn_engine import (
        calculate_microstrip_impedance,
        calculate_stripline_impedance,
        calculate_differential_impedance,
        calculate_temp_rise,
        calculate_max_current,
        get_required_clearance,
        calculate_via_parasitics
    )
    SATURN_ENGINE_AVAILABLE = True
except ImportError:
    SATURN_ENGINE_AVAILABLE = False


@dataclass
class StackupLayer:
    """Parsed stackup layer data."""
    name: str
    function: str
    side: str
    copper_thickness_mm: float | None
    dielectric_thickness_mm: float | None
    dielectric_constant: float | None
    is_signal: bool
    is_plane: bool


@dataclass
class ImpedanceVerificationResult:
    """Result of impedance verification for nets."""
    status: str
    stackup_available: bool
    nets_analyzed: int
    target_impedance: float
    tolerance_percent: float
    violations: list[dict[str, Any]]
    pass_status: bool
    error_message: str | None = None


@dataclass
class ThermalVerificationResult:
    """Result of thermal/current verification."""
    status: str
    stackup_available: bool
    nets_analyzed: int
    max_temp_rise_c: float
    violations: list[dict[str, Any]]
    pass_status: bool
    error_message: str | None = None


@dataclass
class VoltageSpacingResult:
    """Result of IPC-2221B voltage spacing verification."""
    status: str
    net_pairs_analyzed: int
    violations: list[dict[str, Any]]
    pass_status: bool
    error_message: str | None = None


def load_stackup_json(stackup_path: str) -> dict[str, StackupLayer]:
    """
    Load and parse stackup JSON file into layer lookup dictionary.
    
    Args:
        stackup_path: Path to stackup JSON file
    
    Returns:
        Dictionary mapping layer name to StackupLayer
    """
    with open(stackup_path, "r", encoding="utf-8") as f:
        stackup_data = json.load(f)
    
    layers = {}
    layer_list = stackup_data.get("layer_stack") or stackup_data.get("layers", [])
    
    # Get units from stackup JSON (default to INCH for IPC2581)
    units = stackup_data.get("units", "INCH").upper()
    
    # Conversion factor to mm
    if units == "INCH":
        to_mm = 25.4
    elif units == "MIL":
        to_mm = 0.0254
    elif units == "MM":
        to_mm = 1.0
    else:
        to_mm = 25.4  # Default assume inches
    
    for layer in layer_list:
        name = layer.get("name", "")
        function = layer.get("function", "")
        side = layer.get("side", "")
        
        # Parse thickness and material properties
        copper_thickness = layer.get("copper_thickness")
        dielectric_thickness = layer.get("thickness")
        dielectric_constant = layer.get("dielectric_constant")
        
        # Convert to mm using stackup units
        if copper_thickness is not None and copper_thickness > 0:
            copper_thickness_mm = copper_thickness * to_mm
        else:
            copper_thickness_mm = None
        
        # Dielectric thickness handling
        if dielectric_thickness is not None and dielectric_thickness > 0:
            dielectric_thickness_mm = dielectric_thickness * to_mm
        else:
            dielectric_thickness_mm = None
        
        is_signal = function in ("CONDUCTOR", "SIGNAL")
        is_plane = function in ("PLANE", "POWER", "GROUND")
        
        layers[name] = StackupLayer(
            name=name,
            function=function,
            side=side,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_thickness_mm=dielectric_thickness_mm,
            dielectric_constant=dielectric_constant,
            is_signal=is_signal,
            is_plane=is_plane
        )
    
    return layers


def verify_impedance(
    board: dict[str, Any],
    stackup_path: str | None,
    target_ohms: float = 100.0,  # 100Ω for differential pairs
    tolerance_percent: float = 10.0
) -> ImpedanceVerificationResult:
    """
    Verify controlled impedance for differential pairs.
    
    Uses Wheeler/Wadell transmission line equations from Saturn engine.
    Calculates differential impedance (Zdiff ≈ 2×Z0 with coupling factor).
    
    Args:
        board: Board JSON data
        stackup_path: Path to stackup JSON file (optional)
        target_ohms: Target differential impedance in ohms (default: 100Ω)
        tolerance_percent: Tolerance as percentage (default: 10%)
    
    Returns:
        ImpedanceVerificationResult
    """
    if not SATURN_ENGINE_AVAILABLE:
        return ImpedanceVerificationResult(
            status="ERROR",
            stackup_available=False,
            nets_analyzed=0,
            target_impedance=target_ohms,
            tolerance_percent=tolerance_percent,
            violations=[],
            pass_status=False,
            error_message="Saturn engine not available (import failed)"
        )
    
    if not stackup_path:
        return ImpedanceVerificationResult(
            status="STACKUP_DATA_REQUIRED",
            stackup_available=False,
            nets_analyzed=0,
            target_impedance=target_ohms,
            tolerance_percent=tolerance_percent,
            violations=[],
            pass_status=False,
            error_message="Stackup data required for impedance verification"
        )
    
    try:
        stackup_layers = load_stackup_json(stackup_path)
    except Exception as e:
        return ImpedanceVerificationResult(
            status="ERROR",
            stackup_available=False,
            nets_analyzed=0,
            target_impedance=target_ohms,
            tolerance_percent=tolerance_percent,
            violations=[],
            pass_status=False,
            error_message=f"Failed to load stackup: {e}"
        )
    
    # Check if stackup has material data
    has_material_data = any(
        layer.copper_thickness_mm is not None and 
        layer.dielectric_constant is not None
        for layer in stackup_layers.values()
    )
    
    if not has_material_data:
        return ImpedanceVerificationResult(
            status="STACKUP_DATA_REQUIRED",
            stackup_available=False,
            nets_analyzed=0,
            target_impedance=target_ohms,
            tolerance_percent=tolerance_percent,
            violations=[],
            pass_status=False,
            error_message="Stackup JSON lacks material/thickness data"
        )
    
    violations = []
    nets_analyzed = 0
    
    # Analyze differential pairs
    diff_pairs = analyze_all_differential_pairs(board)
    
    # Extract routes for analysis
    routes = _extract_routes_from_board(board)
    
    # Build map of net → routes
    net_routes = {}
    for route in routes:
        net_name = route.get("net")
        if net_name:
            if net_name not in net_routes:
                net_routes[net_name] = []
            net_routes[net_name].append(route)
    
    for pair in diff_pairs:
        if pair.net_positive not in net_routes:
            continue
        
        # Get trace geometry from first route of positive net
        pair_routes = net_routes[pair.net_positive]
        if not pair_routes:
            continue
        
        first_route = pair_routes[0]
        width_mm = first_route.get("line_width") or first_route.get("width") or 0
        layer_name = first_route.get("layer", "")
        
        # Convert units if needed (IPC2581 often uses INCH)
        width_units = first_route.get("line_width_units", "").upper()
        if width_units == "INCH" and width_mm > 0:
            width_mm = width_mm * 25.4  # Convert to mm
        
        if width_mm <= 0 or layer_name not in stackup_layers:
            continue
        
        layer = stackup_layers[layer_name]
        
        if layer.copper_thickness_mm is None:
            continue
        
        # Dynamically find the adjacent dielectric layer in the stackup
        layers_list = list(stackup_layers.values())
        idx = -1
        for idx_l, l in enumerate(layers_list):
            if l.name == layer_name:
                idx = idx_l
                break
        
        dielectric_height_mm = None
        dielectric_constant = None
        
        if idx != -1:
            # Look below the signal layer first
            for j in range(idx + 1, len(layers_list)):
                if layers_list[j].function == "DIELECTRIC":
                    dielectric_height_mm = layers_list[j].dielectric_thickness_mm
                    dielectric_constant = layers_list[j].dielectric_constant
                    break
            # Look above the signal layer as a fallback
            if dielectric_height_mm is None:
                for j in range(idx - 1, -1, -1):
                    if layers_list[j].function == "DIELECTRIC":
                        dielectric_height_mm = layers_list[j].dielectric_thickness_mm
                        dielectric_constant = layers_list[j].dielectric_constant
                        break
        
        # Fallback to robust defaults if not found
        if dielectric_height_mm is None:
            dielectric_height_mm = 0.2
        if dielectric_constant is None:
            dielectric_constant = 4.5
        
        # Calculate single-ended impedance first
        if layer.side in ("TOP", "BOTTOM"):
            # Microstrip (external layer)
            se_result = calculate_microstrip_impedance(
                w=width_mm,
                t=layer.copper_thickness_mm,
                h=dielectric_height_mm,
                dk=dielectric_constant,
                unit="mm"
            )
        else:
            # Stripline (internal layer)
            # b = total ground plane spacing (estimate as 2x dielectric height)
            se_result = calculate_stripline_impedance(
                w=width_mm,
                t=layer.copper_thickness_mm,
                b=dielectric_height_mm * 4.5,
                dk=dielectric_constant,
                unit="mm"
            )
        
        if not se_result.valid:
            continue
        
        z0_single = se_result.z0_ohms
        
        # Calculate differential impedance
        # Use the actual calculated geometric coupling distance if available
        if pair.avg_coupling_distance is not None:
            raw_spacing = pair.avg_coupling_distance
            board_units = _get_units(board).upper()
            if board_units == "INCH":
                pair_spacing_mm = raw_spacing * 25.4
            else:
                pair_spacing_mm = raw_spacing
        else:
            # Fallback to width if uncoupled
            pair_spacing_mm = width_mm
        
        calculated_zdiff = calculate_differential_impedance(
            z0_single=z0_single,
            s=pair_spacing_mm,
            h=se_result.dielectric_height_mm,
            topology=se_result.topology
        )
        
        nets_analyzed += 1
        deviation = abs(calculated_zdiff - target_ohms) / target_ohms * 100
        
        if deviation > tolerance_percent:
            violations.append({
                "net": pair.net_positive,
                "differential_pair": f"{pair.net_positive}/{pair.net_negative}",
                "layer": layer_name,
                "topology": f"differential_{se_result.topology}",
                "trace_width_mm": width_mm,
                "pair_spacing_mm": pair_spacing_mm,
                "calculated_z0_single_ohms": z0_single,
                "calculated_zdiff_ohms": calculated_zdiff,
                "target_zdiff_ohms": target_ohms,
                "deviation_percent": round(deviation, 2),
                "severity": "critical" if deviation > tolerance_percent * 2 else "warning",
                "rule_id": "HS_MAT_001"
            })
    
    return ImpedanceVerificationResult(
        status="PASS" if len(violations) == 0 else "FAIL",
        stackup_available=True,
        nets_analyzed=nets_analyzed,
        target_impedance=target_ohms,
        tolerance_percent=tolerance_percent,
        violations=violations,
        pass_status=len(violations) == 0
    )


def verify_trace_temperature(
    board: dict[str, Any],
    stackup_path: str | None,
    current_a: float = 1.0,
    max_temp_rise_c: float = 10.0
) -> ThermalVerificationResult:
    """
    Verify trace current capacity and temperature rise using IPC-2152.
    
    Args:
        board: Board JSON data
        stackup_path: Path to stackup JSON file
        current_a: Current in amperes
        max_temp_rise_c: Maximum allowable temperature rise (°C)
    
    Returns:
        ThermalVerificationResult
    """
    if not SATURN_ENGINE_AVAILABLE:
        return ThermalVerificationResult(
            status="ERROR",
            stackup_available=False,
            nets_analyzed=0,
            max_temp_rise_c=max_temp_rise_c,
            violations=[],
            pass_status=False,
            error_message="Saturn engine not available"
        )
    
    if not stackup_path:
        return ThermalVerificationResult(
            status="STACKUP_DATA_REQUIRED",
            stackup_available=False,
            nets_analyzed=0,
            max_temp_rise_c=max_temp_rise_c,
            violations=[],
            pass_status=False,
            error_message="Stackup data required for thermal verification"
        )
    
    try:
        stackup_layers = load_stackup_json(stackup_path)
    except Exception as e:
        return ThermalVerificationResult(
            status="ERROR",
            stackup_available=False,
            nets_analyzed=0,
            max_temp_rise_c=max_temp_rise_c,
            violations=[],
            pass_status=False,
            error_message=f"Failed to load stackup: {e}"
        )
    
    violations = []
    nets_analyzed = 0
    
    # Extract routes from board
    routes = _extract_routes_from_board(board)
    
    # Extract schematic analysis data for accurate power net identification
    analysis = board.get("analysis", {})
    power_nets_from_schematic = set(analysis.get("power_nets", []))
    
    # Analyze power nets
    # Use schematic analysis first, fallback to regex for boards without analysis
    power_net_patterns = re.compile(
        r"(VCC|VDD|VBUS|VSYS|VBAT|VPP|VREF|AVDD|DVDD|"
        r"\b\d+V\d*\b|\b\d+[P\._]\d+V\b|"
        r"\bV\d+[P\._]\d+\b|"
        r"\b\+?\d+(\.\d+)?V\b)",
        re.IGNORECASE
    )
    
    def is_power_net(net_name: str) -> bool:
        """Check if net is a power net using schematic analysis or regex fallback."""
        if not net_name:
            return False
        # Use schematic analysis first (most accurate)
        if net_name in power_nets_from_schematic:
            return True
        # Fallback to regex
        return bool(power_net_patterns.search(net_name))
    
    # Group routes by net name
    nets_seen = set()
    
    for route in routes:
        net_name = route.get("net")
        if not is_power_net(net_name):
            continue
        
        # Track unique nets for counting
        if net_name not in nets_seen:
            nets_seen.add(net_name)
            nets_analyzed += 1
        
        width_mm = route.get("line_width") or route.get("width") or 0
        layer_name = route.get("layer", "")
        
        # Convert units if needed (IPC2581 often uses INCH)
        width_units = route.get("line_width_units", "").upper()
        if width_units == "INCH" and width_mm > 0:
            width_mm = width_mm * 25.4  # Convert to mm
        
        if width_mm <= 0 or layer_name not in stackup_layers:
            continue
        
        layer = stackup_layers[layer_name]
        
        if layer.copper_thickness_mm is None:
            continue
        
        copper_thickness_um = layer.copper_thickness_mm * 1000  # mm to um
        is_internal = layer.side == "INTERNAL"
        
        # Intelligent current estimation based on trace width
        # 20 mils = 0.508mm - threshold between power plane and device trace
        POWER_PLANE_WIDTH_MM = 0.508  # 20 mils
        if width_mm > POWER_PLANE_WIDTH_MM:
            # Wide trace - power distribution, assume 1A
            estimated_current = 1.0
        else:
            # Narrow trace - device connection, assume 100mA
            estimated_current = 0.1
        
        # Use estimated current if no explicit current provided, otherwise use passed value
        actual_current = estimated_current if current_a == 1.0 else current_a
        
        # Calculate temperature rise
        thermal_result = calculate_temp_rise(
            width_mm=width_mm,
            thickness_um=copper_thickness_um,
            current_a=actual_current,
            is_internal=is_internal
        )
        
        if not thermal_result.valid:
            continue
        
        if thermal_result.temp_rise_c > max_temp_rise_c:
            violations.append({
                "net": net_name,
                "layer": layer_name,
                "trace_width_mm": width_mm,
                "copper_thickness_um": copper_thickness_um,
                "current_a": actual_current,
                "calculated_temp_rise_c": thermal_result.temp_rise_c,
                "max_allowed_temp_rise_c": max_temp_rise_c,
                "is_internal": is_internal,
                "current_estimation": "power_plane" if width_mm > POWER_PLANE_WIDTH_MM else "device_trace",
                "severity": "critical" if thermal_result.temp_rise_c > max_temp_rise_c * 2 else "warning",
                "rule_id": "PWR_TRACE_002"
            })
    
    return ThermalVerificationResult(
        status="PASS" if len(violations) == 0 else "FAIL",
        stackup_available=True,
        nets_analyzed=nets_analyzed,
        max_temp_rise_c=max_temp_rise_c,
        violations=violations,
        pass_status=len(violations) == 0
    )


def check_voltage_clearance(
    board: dict[str, Any],
    schematic_path: str | None = None,
    default_category: str = "B2"
) -> VoltageSpacingResult:
    """
    Verify electrical clearances per IPC-2221B Table 6-1.
    
    Uses schematic analysis.power_nets to identify voltage rails and verifies
    spacing between high-voltage nets.
    
    Args:
        board: Board JSON data
        schematic_path: Path to schematic JSON (required for voltage extraction)
        default_category: IPC category (B1, B2, B4)
    
    Returns:
        VoltageSpacingResult
    """
    if not SATURN_ENGINE_AVAILABLE:
        return VoltageSpacingResult(
            status="ERROR",
            net_pairs_analyzed=0,
            violations=[],
            pass_status=False,
            error_message="Saturn engine not available"
        )
    
    # Load schematic to get power nets
    if not schematic_path:
        return VoltageSpacingResult(
            status="NO_SCHEMATIC",
            net_pairs_analyzed=0,
            violations=[],
            pass_status=True,
            error_message="Schematic path required for voltage net identification"
        )
    
    try:
        with open(schematic_path, 'r', encoding='utf-8') as f:
            schematic = json.load(f)
    except Exception as e:
        return VoltageSpacingResult(
            status="ERROR",
            net_pairs_analyzed=0,
            violations=[],
            pass_status=False,
            error_message=f"Failed to load schematic: {e}"
        )
    
    # Get power nets from schematic analysis
    power_nets = schematic.get("analysis", {}).get("power_nets", [])
    if not power_nets:
        return VoltageSpacingResult(
            status="NO_VOLTAGE_NETS",
            net_pairs_analyzed=0,
            violations=[],
            pass_status=True,
            error_message="No power nets found in schematic analysis"
        )
    
    violations = []
    net_pairs_analyzed = 0
    
    # Extract routes from board
    routes = _extract_routes_from_board(board)
    
    # Parse voltage from power net names
    # Common patterns: V24P0 -> 24.0V, V3P3 -> 3.3V, V5P0 -> 5.0V
    voltage_pattern = re.compile(r"V(\d+)P(\d+)|V(\d+)_(\d+)|(\d+)V(\d*)", re.IGNORECASE)
    net_voltages = {}
    
    for net_name in power_nets:
        match = voltage_pattern.search(net_name)
        if match:
            if match.group(1):  # V24P0 format
                voltage = float(match.group(1)) + float(match.group(2)) / 10.0
            elif match.group(3):  # V12_5 format
                voltage = float(match.group(3))
                if match.group(4):
                    voltage += float(f"0.{match.group(4)}")
            elif match.group(5):  # 12V format
                voltage = float(match.group(5))
                if match.group(6):
                    voltage += float(f"0.{match.group(6)}")
            else:
                continue
            net_voltages[net_name] = voltage
    
    if len(net_voltages) < 2:
        return VoltageSpacingResult(
            status="INSUFFICIENT_DATA",
            net_pairs_analyzed=0,
            violations=[],
            pass_status=True,
            error_message=f"Found {len(net_voltages)} voltage nets with parseable voltages (need 2+ for clearance check)"
        )
    
    # Check clearance between high-voltage net pairs
    net_names = list(net_voltages.keys())
    
    for i, net_a in enumerate(net_names):
        for net_b in net_names[i+1:]:
            voltage_a = net_voltages[net_a]
            voltage_b = net_voltages[net_b]
            
            # Calculate required clearance based on voltage difference
            voltage_diff = abs(voltage_a - voltage_b)
            
            if voltage_diff < 10:  # Skip low-voltage differences
                continue
            
            spacing_result = get_required_clearance(voltage_diff, default_category)
            
            if not spacing_result.valid:
                continue
            
            # Calculate actual clearance
            clearance_result = calculate_min_clearance(board, net_a, net_b)
            
            if clearance_result.min_clearance is None:
                continue
            
            net_pairs_analyzed += 1
            
            if clearance_result.min_clearance < spacing_result.required_clearance_mm:
                violations.append({
                    "net_a": net_a,
                    "net_b": net_b,
                    "voltage_a": voltage_a,
                    "voltage_b": voltage_b,
                    "voltage_difference": voltage_diff,
                    "actual_clearance_mm": clearance_result.min_clearance,
                    "required_clearance_mm": spacing_result.required_clearance_mm,
                    "ipc_category": default_category,
                    "shortfall_mm": round(spacing_result.required_clearance_mm - clearance_result.min_clearance, 3),
                    "severity": "critical",
                    "rule_id": "DFM_TRACE_004"
                })
    
    return VoltageSpacingResult(
        status="PASS" if len(violations) == 0 else "FAIL",
        net_pairs_analyzed=net_pairs_analyzed,
        violations=violations,
        pass_status=len(violations) == 0
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    """CLI interface for geometry helpers."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="ThomsonLint Geometry Analysis Helpers")
    parser.add_argument("board_json", help="Path to board JSON file")
    parser.add_argument("--net", help="Analyze specific net")
    parser.add_argument("--clearance", nargs=2, metavar=("NET_A", "NET_B"), 
                        help="Calculate clearance between two nets")
    parser.add_argument("--diff-pairs", action="store_true", 
                        help="Analyze all differential pairs")
    parser.add_argument("--npth", action="store_true",
                        help="Check NPTH copper clearance")
    parser.add_argument("--npth-radius", type=float, default=4.0,
                        help="NPTH keepout radius (default: 4.0)")
    parser.add_argument("--ampacity", nargs=2, metavar=("NET", "CURRENT_A"),
                        help="Verify trace ampacity for net")
    # Advanced DFM checks
    parser.add_argument("--check-annular-ring", action="store_true",
                        help="Check via annular ring (DFM_VIA_001, DFM_VIA_003, DFM_VIA_004)")
    parser.add_argument("--annular-ring-min", type=float, default=0.127,
                        help="Minimum annular ring in mm (default: 0.127mm = 5 mils)")
    parser.add_argument("--detect-acid-traps", action="store_true",
                        help="Detect acute angle trace bends (DFM_ACID_001)")
    parser.add_argument("--acid-trap-angle", type=float, default=70.0,
                        help="Angle threshold in degrees (default: 70)")
    parser.add_argument("--board-edge-clearance", action="store_true",
                        help="Check copper to board edge clearance (DFM_EDGE_001, DFM_PANEL_001)")
    parser.add_argument("--edge-clearance-min", type=float, default=0.5,
                        help="Minimum edge clearance in mm (default: 0.5mm = 20 mils)")
    parser.add_argument("--copper-balance", action="store_true",
                        help="Estimate copper balance across layers (DFM_COPPER_001)")
    parser.add_argument("--copper-imbalance-threshold", type=float, default=25.0,
                        help="Maximum allowed copper imbalance percentage (default: 25)")
    # Physical-math verification (Saturn engine integration)
    parser.add_argument("--stackup", type=str,
                        help="Path to stackup JSON file (for physical-math verification)")
    parser.add_argument("--verify-impedance", action="store_true",
                        help="Verify controlled impedance (HS_MAT_001) - requires stackup")
    parser.add_argument("--target-ohms", type=float, default=50.0,
                        help="Target impedance in ohms (default: 50)")
    parser.add_argument("--impedance-tolerance", type=float, default=10.0,
                        help="Impedance tolerance percentage (default: 10)")
    parser.add_argument("--verify-trace-temp", action="store_true",
                        help="Verify trace temperature rise (PWR_TRACE_002) - requires stackup")
    parser.add_argument("--current-a", type=float, default=1.0,
                        help="Current in amperes for thermal verification (default: 1.0)")
    parser.add_argument("--max-temp-rise", type=float, default=10.0,
                        help="Maximum temperature rise in Celsius (default: 10)")
    parser.add_argument("--check-voltage-clearance", action="store_true",
                        help="Check IPC-2221B voltage spacing (DFM_TRACE_004)")
    parser.add_argument("--schematic", type=str,
                        help="Path to schematic JSON (required for voltage clearance check)")
    parser.add_argument("--ipc-category", type=str, default="B2", choices=["B1", "B2", "B4"],
                        help="IPC-2221B category (default: B2 external uncoated)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")

    args = parser.parse_args()

    try:
        board = load_board_json(args.board_json)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    results = {}

    if args.net:
        stats = get_net_segments(board, args.net)
        results["net_segments"] = {
            "net": stats.net_name,
            "segment_count": len(stats.segments),
            "total_length": round(stats.total_length, 4),
            "min_width": stats.min_width,
            "max_width": stats.max_width,
            "avg_width": round(stats.avg_width, 4) if stats.avg_width else None,
            "nominal_width": stats.nominal_width,
            "layers": list(stats.layers)
        }

    if args.clearance:
        net_a, net_b = args.clearance
        result = calculate_min_clearance(board, net_a, net_b)
        results["clearance"] = {
            "net_a": result.net_a,
            "net_b": result.net_b,
            "min_clearance": result.min_clearance,
            "location": result.clearance_location,
            "layer": result.clearance_layer,
            "segments_compared": result.segments_compared
        }

    if args.diff_pairs:
        analyses = analyze_all_differential_pairs(board)
        results["differential_pairs"] = [
            {
                "positive": a.net_positive,
                "negative": a.net_negative,
                "avg_coupling": round(a.avg_coupling_distance, 4) if a.avg_coupling_distance else None,
                "length_mismatch_mm": round(a.length_mismatch, 4),
                "length_mismatch_pct": round(a.length_mismatch_percent, 2),
                "uncoupled_length": round(a.uncoupled_length, 4),
                "uncoupled_sections": len(a.uncoupled_sections),
                "quality": a.coupling_quality
            }
            for a in analyses
        ]

    if args.npth:
        result = check_npth_clearance(board, keepout_radius=args.npth_radius)
        results["npth_clearance"] = {
            "npth_count": result.npth_count,
            "analyzed": result.analyzed_count,
            "keepout_radius": result.keepout_radius,
            "units": result.keepout_units,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "violations": [
                {
                    "hole_id": v.hole_id,
                    "feature_type": v.feature_type,
                    "feature_net": v.feature_net,
                    "layer": v.feature_layer,
                    "distance": v.distance_to_hole,
                    "severity": v.violation_severity
                }
                for v in result.violations[:20]
            ]
        }

    if args.ampacity:
        net, current = args.ampacity
        result = verify_trace_ampacity(board, net, float(current))
        results["ampacity"] = result

    # Advanced DFM checks
    if args.check_annular_ring:
        result = check_via_annular_rings(board, min_ring_mm=args.annular_ring_min)
        results["annular_ring"] = {
            "rule_ids": ["DFM_VIA_001", "DFM_VIA_003", "DFM_VIA_004"],
            "via_count": result.via_count,
            "analyzed": result.analyzed_count,
            "threshold_mm": result.threshold_mm,
            "units": result.units,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "violations": [
                {
                    "via_id": v.via_id,
                    "x": v.x,
                    "y": v.y,
                    "pad_diameter": v.pad_diameter,
                    "drill_diameter": v.drill_diameter,
                    "annular_ring": v.annular_ring,
                    "layer": v.layer,
                    "severity": v.severity
                }
                for v in result.violations[:30]
            ]
        }

    if args.detect_acid_traps:
        result = detect_acid_traps(board, angle_threshold_deg=args.acid_trap_angle)
        results["acid_traps"] = {
            "rule_id": "DFM_ACID_001",
            "routes_analyzed": result.routes_analyzed,
            "vertices_analyzed": result.vertices_analyzed,
            "angle_threshold_deg": result.angle_threshold_deg,
            "trap_count": len(result.traps),
            "pass": result.pass_status,
            "traps": [
                {
                    "route_id": t.route_id,
                    "net": t.net,
                    "layer": t.layer,
                    "vertex": [t.vertex_x, t.vertex_y],
                    "angle_deg": t.angle_deg,
                    "severity": t.severity
                }
                for t in result.traps[:30]
            ]
        }

    if args.board_edge_clearance:
        result = check_board_edge_clearance(board, min_clearance_mm=args.edge_clearance_min)
        results["board_edge_clearance"] = {
            "rule_ids": ["DFM_EDGE_001", "DFM_PANEL_001"],
            "outline_found": result.outline_found,
            "outline_segments": result.outline_segment_count,
            "threshold_mm": result.threshold_mm,
            "units": result.units,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "violations": [
                {
                    "feature_type": v.feature_type,
                    "feature_id": v.feature_id,
                    "feature_net": v.feature_net,
                    "layer": v.feature_layer,
                    "location": [v.feature_x, v.feature_y],
                    "distance_to_edge": v.distance_to_edge,
                    "severity": v.severity
                }
                for v in result.violations[:30]
            ]
        }

    if args.copper_balance:
        result = estimate_copper_balance(board, imbalance_threshold_pct=args.copper_imbalance_threshold)
        results["copper_balance"] = {
            "rule_id": "DFM_COPPER_001",
            "units": result.units,
            "layer_pairs_checked": result.layer_pairs_checked,
            "imbalance_threshold_pct": result.imbalance_threshold_pct,
            "warning_count": len(result.warnings),
            "pass": result.pass_status,
            "layer_areas": [
                {
                    "layer": la.layer_name,
                    "route_area": la.route_area,
                    "pad_area": la.pad_area,
                    "polygon_area": la.polygon_area,
                    "total_area": la.total_area
                }
                for la in result.layer_areas
            ],
            "warnings": [
                {
                    "layer_a": w.layer_a,
                    "layer_b": w.layer_b,
                    "area_a": w.area_a,
                    "area_b": w.area_b,
                    "imbalance_pct": w.imbalance_percent
                }
                for w in result.warnings
            ]
        }

    # Physical-Math Verification (Saturn Engine)
    if args.verify_impedance:
        # Auto-detect stackup path if not provided
        stackup_path = args.stackup
        if not stackup_path:
            board_path = Path(args.board_json)
            project_dir = board_path.parent
            stackup_candidates = [
                project_dir / f"{board_path.stem.replace('-thomson-export-brd', '')}-thomson-export-stack.json",
                project_dir / "stackup.json",
                project_dir.parent / "input" / "stackup.json"
            ]
            for candidate in stackup_candidates:
                if candidate.exists():
                    stackup_path = str(candidate)
                    break
        
        result = verify_impedance(
            board, 
            stackup_path, 
            target_ohms=args.target_ohms,
            tolerance_percent=args.impedance_tolerance
        )
        results["impedance_verification"] = {
            "rule_id": "HS_MAT_001",
            "status": result.status,
            "stackup_available": result.stackup_available,
            "nets_analyzed": result.nets_analyzed,
            "target_impedance_ohms": result.target_impedance,
            "tolerance_percent": result.tolerance_percent,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "error_message": result.error_message,
            "violations": result.violations[:20]
        }

    if args.verify_trace_temp:
        stackup_path = args.stackup
        if not stackup_path:
            board_path = Path(args.board_json)
            project_dir = board_path.parent
            stackup_candidates = [
                project_dir / f"{board_path.stem.replace('-thomson-export-brd', '')}-thomson-export-stack.json",
                project_dir / "stackup.json",
                project_dir.parent / "input" / "stackup.json"
            ]
            for candidate in stackup_candidates:
                if candidate.exists():
                    stackup_path = str(candidate)
                    break
        
        result = verify_trace_temperature(
            board,
            stackup_path,
            current_a=args.current_a,
            max_temp_rise_c=args.max_temp_rise
        )
        results["thermal_verification"] = {
            "rule_id": "PWR_TRACE_002",
            "status": result.status,
            "stackup_available": result.stackup_available,
            "nets_analyzed": result.nets_analyzed,
            "max_temp_rise_c": result.max_temp_rise_c,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "error_message": result.error_message,
            "violations": result.violations[:20]
        }

    if args.check_voltage_clearance:
        schematic_path = args.schematic
        if not schematic_path:
            # Try to auto-discover schematic JSON
            board_path = Path(args.board_json)
            project_dir = board_path.parent
            schematic_candidates = [
                project_dir / f"{board_path.stem.replace('-thomson-export-brd', '')}-thomson-export-sch.json",
                project_dir / "schematic.json",
                project_dir.parent / "input" / "schematic.json"
            ]
            for candidate in schematic_candidates:
                if candidate.exists():
                    schematic_path = str(candidate)
                    break
        
        result = check_voltage_clearance(
            board,
            schematic_path=schematic_path,
            default_category=args.ipc_category
        )
        results["voltage_spacing"] = {
            "rule_id": "DFM_TRACE_004",
            "status": result.status,
            "ipc_category": args.ipc_category,
            "net_pairs_analyzed": result.net_pairs_analyzed,
            "violation_count": len(result.violations),
            "pass": result.pass_status,
            "error_message": result.error_message,
            "violations": result.violations[:20]
        }

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for key, value in results.items():
            print(f"\n=== {key.upper()} ===")
            if isinstance(value, dict):
                for k, v in value.items():
                    print(f"  {k}: {v}")
            elif isinstance(value, list):
                for item in value:
                    print(f"  - {item}")


if __name__ == "__main__":
    main()
