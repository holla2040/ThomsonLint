# Fusion Electronics ULP Integration Guide

## Overview

This document analyzes the feasibility of integrating ThomsonLint with Fusion Electronics using ULP (User Language Program) scripts, with a focus on layer image analysis and registration for accurate multi-layer design review.

## What ULP Can Export from Fusion Electronics

ULP scripts can typically export:
- **Gerber files** (individual layer images in vector format)
- **Drill files** (via/hole locations)
- **BOM** (component data)
- **Netlist** (electrical connectivity)
- **Layer screenshots** (rasterized PNG/JPEG of each layer)
- **PDF documentation** (combined views)

## Can AI Agents Analyze Layer Images?

**Yes, with caveats:**

### ✅ What Works Well

- **Component identification** - Vision models can recognize ICs, passives, connectors
- **Visual defects** - Trace spacing violations, silkscreen legibility, pour coverage
- **Qualitative assessment** - "This looks cramped," "Poor thermal relief pattern"
- **Single-layer analysis** - Trace widths, clearances visible on one layer

### ⚠️ What's Challenging

- **Precise measurements** - Need scale/DPI metadata with images
- **Multi-layer correlation** - The critical issue for accurate design review

## The Layer Registration Problem

This is the **biggest technical hurdle** for image-based multi-layer analysis.

### Why Registration is Critical

Many design rules in the ThomsonLint ontology require **cross-layer understanding**:

- **Return path continuity** (See `docs/AI_Hardware_Design_Review_KnowledgeBase.md` Appendix D.2) - Signal on Layer 1 needs ground via near signal via
- **Via transitions** - Understanding signal flow through layers
- **Impedance control** - Requires knowing trace-to-plane spacing (stackup)
- **Plane splits** - Signal crossing a split on a reference layer (Rule `HS_DIFF_001`, `HS_SER_002`)

### Technical Requirements for Registration

**1. Spatial Alignment:**
```
Top layer image:    [Component at X=100, Y=200]
Ground plane image: [Plane split at X=???, Y=???]
                     ↑ Need coordinate mapping
```

**2. What's Needed:**
- **Fiducial marks** or board outline in each layer image
- **Consistent scale/resolution** across all layers
- **Metadata** indicating physical dimensions (board size, DPI)
- **Layer stackup definition** (which layers are signal/power/ground)

**3. ULP Export Considerations:**

If ULP exports:
- ✅ **Gerber files** → Can be rendered with known scale, fiducials preserved
- ✅ **Standardized screenshots** → If taken with consistent zoom/position
- ❌ **Ad-hoc screenshots** → Different zoom levels = impossible to align

## Recommended Integration Approaches

### Option 1: Gerber-Based (Most Reliable)

```
ULP exports → Gerber files → Render to PNG with metadata → AI analysis
             ↓
          Include: - Scale (mils/pixel)
                  - Fiducial coordinates
                  - Layer stackup JSON
```

**Pros:** Precise alignment possible, industry-standard format
**Cons:** Requires Gerber rendering tools in pipeline

### Option 2: Hybrid Approach (Pragmatic)

```
ULP exports → {
  - Structured data (netlist, BOM, drill) → For precise checks
  - Layer images                          → For visual inspection
  - Stackup metadata                      → For context
}
```

The AI agents could:
1. **Use structured data** for multi-layer electrical analysis (vias, return paths, impedance)
2. **Use images** for single-layer visual checks (clearances, silkscreen, component orientation)
3. **Cross-reference** but not rely purely on image registration

**Pros:** Leverages strengths of both data types, practical for current AI capabilities
**Cons:** May miss some visual-only issues that span layers

### Option 3: Automated Registration Algorithm

Implement pre-processing:
```python
def register_layers(layer_images, fiducials):
    # 1. Detect fiducial marks in each image
    # 2. Compute affine transform to align
    # 3. Return aligned image stack + coordinate mapping
```

**Feasibility:** Modern computer vision can detect fiducials, but requires:
- Standardized fiducial placement
- Consistent image export settings from ULP
- Pre-processing pipeline before AI review

**Pros:** Enables precise image-based multi-layer analysis
**Cons:** Complex implementation, requires robust CV algorithms

## Recommended Implementation Path

**For practical near-term implementation:**

1. **Use images for visual/qualitative checks** - As anticipated in `docs/Multi_Agent_Reasoning_Spec.md:79-83` and `gen_context.sh:70-85`
2. **Use netlist + drill data for precise electrical analysis** - For rules requiring exact measurements
3. **Accept limitations** - Some rules (like `HS_SER_002` for return path vias) require structured data, not just images

**The framework already anticipates this approach** - see the file correlation requirements in `gen_context.sh:70-85`, which call for cross-referencing images with source files.

## Required ULP Export Metadata

To enable effective AI-based review, ULP scripts should export:

### Minimum Required
- **Layer images** (PNG/JPEG, consistent resolution)
- **Board outline dimensions** (in same coordinate system as images)
- **Netlist** (electrical connectivity)
- **BOM** (component types, values, ratings)
- **Drill file** (via locations and sizes)

### Highly Recommended
- **Stackup definition** (JSON format):
  ```json
  {
    "layers": [
      {"name": "Top", "type": "signal", "thickness_um": 35},
      {"name": "GND", "type": "plane", "thickness_um": 35},
      {"name": "Signal", "type": "signal", "thickness_um": 35},
      {"name": "Bottom", "type": "signal", "thickness_um": 35}
    ],
    "dielectric_heights_mils": [5, 40, 5],
    "dielectric_er": [4.3, 4.3, 4.3]
  }
  ```
- **Image metadata** (JSON format):
  ```json
  {
    "layer": "Top",
    "resolution_dpi": 600,
    "board_size_mils": {"width": 4000, "height": 3000},
    "origin": "bottom-left",
    "fiducials": [
      {"x_mils": 100, "y_mils": 100},
      {"x_mils": 3900, "y_mils": 2900}
    ]
  }
  ```

### Optional (Enhances Analysis)
- **Gerber files** (for precise rendering if needed)
- **Component placement data** (coordinates, rotation, layer)
- **Design rule settings** (from EDA tool)

## Multi-Agent Review with ULP Data

Based on `docs/Multi_Agent_Reasoning_Spec.md`, different agents need different data:

| Agent | Required ULP Exports |
|-------|---------------------|
| Power/SMPS Agent | Netlist, BOM, layer images (hot loop visualization), thermal data |
| High-Speed SI Agent | Netlist, layer images, stackup, drill file (via count/placement) |
| Analog Agent | Netlist, layer images (component placement near noise sources) |
| EMC/ESD Agent | Netlist, layer images (connector placement, ground stitching) |
| Thermal/Mechanical Agent | BOM (power ratings), layer images (copper pour), 3D data if available |

## Ontology Rules Requiring Multi-Layer Data

The following rules from `ontology/ontology.json` specifically require cross-layer analysis:

- **HS_DIFF_001** - Differential pairs crossing plane splits (needs layer stack understanding)
- **HS_SER_002** - Return path vias near signal vias (needs drill + layer correlation)
- **HS_DDR_002** - DDR power integrity (needs power plane visualization)
- **EMC_GND_001** - Ground stitching (needs via placement across layers)
- **EMC_RET_001** - Return paths for high di/dt currents (needs multi-layer current flow understanding)

These rules are **difficult to verify from images alone** without registration or structured data.

## Next Steps for Implementation

1. **Create example ULP export scripts** showing ideal data structure
2. **Define standard metadata schemas** (JSON) for layer images and stackup
3. **Test hybrid approach** with real Fusion Electronics designs
4. **Evaluate CV-based fiducial detection** for automated registration
5. **Document limitations** clearly for users (which rules work with images vs. structured data)

## Conclusion

**Image-based layer analysis is feasible for many design checks, but accurate multi-layer correlation requires either:**
- Structured data (Gerber, netlist, drill files) with coordinate systems
- Automated registration with fiducials and metadata

**The recommended approach is hybrid:** Use images for visual inspection and structured data for precise electrical analysis. This aligns with ThomsonLint's existing framework design and is practical for current AI capabilities.

The framework is well-positioned for Fusion Electronics ULP integration—it just needs careful specification of the export format and metadata to bridge the gap between image analysis and electrical verification.
