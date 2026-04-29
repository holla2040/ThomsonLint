# AI Hardware Design Review Knowledge Base (KB)

**Purpose:** This document is the **human-readable counterpart** to `ontology/ontology.json`. It provides the *why* behind the rules, offering deeper engineering context for both human designers and AI agents.

When an AI agent identifies a potential issue using an ontology rule, it should reference the corresponding section in this KB to provide a detailed, helpful explanation.

---

## Part 1: Schematic Review Philosophy & Guidelines

A schematic review is not just about finding errors; it's about ensuring the design is **robust, manufacturable, and meets its intended goals**. An AI agent should categorize its findings based on severity and provide actionable recommendations.

### 1.1 Multi-Pass Review Framework

An effective review emulates how a senior engineer works, examining the design from different perspectives.

1.  **System-Level Pass:** Does the architecture make sense? Are the major components (MCU, power, connectors) logically sound?
2.  **Power & Grounding Pass:** How is power distributed? Is it adequately decoupled and filtered? Is the grounding strategy solid?
3.  **Critical Signal Pass:** How are high-speed (USB, MIPI), sensitive analog, and critical clock signals handled?
4.  **Component-Level Pass:** Are individual components used correctly according to their datasheets (e.g., pin configurations, pull-ups/pull-downs, logic levels)?
5.  **Protection & Reliability Pass:** Is the design protected from real-world events like ESD, over-current, and reverse polarity?
6.  **DFT/DFM Pass (Design for Test/Manufacturability):** Can this board be reliably manufactured, assembled, and tested?

### 1.2 JSON Output Schema for Issues

When the AI finds an issue, it should structure its output in a clear, machine-readable format. This allows for consistent reporting and integration with other tools.

```json
{
  "issues": [
    {
      "rule_id": "PWR_DECPL_001",
      "severity": "Critical",
      "domain": "Power",
      "component_id": ["U5"],
      "net_id": ["+3V3_MCU"],
      "summary": "Missing decoupling capacitor on MCU power pin.",
      "description": "The VDD_CORE pin of MCU U5 is missing a local 100nF decoupling capacitor, which is required to ensure a stable power supply during fast switching operations.",
      "recommended_actions": [
        "Place a 100nF ceramic capacitor (X7R or similar) as close as possible to pin 7 (VDD_CORE) of U5.",
        "Ensure the capacitor's return path to the ground pin is short and direct."
      ],
      "kb_references": ["Section 1.3"]
    }
  ]
}
```

---

## Part 2: Core Engineering Concepts & Rules

This section details common hardware design domains and the key principles to check for.

### 2.1 Power Systems

- **Regulator Choice:** LDOs are simple but inefficient for large voltage drops. Buck/boost converters are efficient but require careful layout.
- **Decoupling:** *Every* IC needs local decoupling. 100nF is standard for high-frequency noise. Bulk caps (10uF+) handle lower-frequency load changes. (See rule `PWR_DECPL_001`).
- **Filtering:** Use ferrite beads or pi filters to isolate noisy sections (like motors or SMPS) from sensitive sections (like analog sensors or RF).
- **Inrush & Polarity:** Protect against hot-plugging and reverse-voltage events with PTC fuses and protection diodes/MOSFETs.

### 2.2 Signal Integrity (SI) & High-Speed Design

- **Impedance Control:** High-speed traces are transmission lines. Their impedance must be controlled (typically 50Ω single-ended, 90-100Ω differential) to prevent reflections.
- **Reference Planes:** High-speed signals need a continuous, solid ground or power plane directly beneath them to provide a low-inductance return path. **Never route over a split plane.** (See rule `HS_DIFF_001`).
- **Length Matching:** For parallel buses like DDR or MIPI, traces must be length-matched to ensure simultaneous arrival. (See rule `HS_DDR_001`).
- **Termination:** High-speed lines need termination resistors (series, parallel, or Thevenin) to absorb signal energy and prevent reflections.

### 2.3 Analog & Mixed-Signal

- **Grounding:** Separate analog and digital grounds are an anti-pattern in most mixed-signal PCBs. Use a single, solid ground plane and partition the layout to keep digital return currents away from the analog section.
- **Op-Amps:** Watch for input common-mode range violations and ensure feedback networks don't create instability. (See rule `AN_OPAMP_001`).
- **ADCs:** Protect ADC inputs from over-voltage and include an anti-aliasing filter to remove frequencies above Nyquist. (See rule `AN_ADC_001`).

### 2.4 EMC, ESD & EMI

- **Connectors are Portals:** Every external connector is a potential entry/exit point for ESD and EMI. Protect them with TVS diodes, ferrite beads, and common-mode chokes. (See rule `EMC_ESD_001`).
- **Minimize Loop Area:** Fast-switching currents (like in a buck converter's "hot loop") create magnetic fields (EMI). Minimize the physical loop area of these paths through careful component placement.
- **Shielding & Stitching:** Use ground pours on outer layers and "stitch" them frequently to the main ground plane with vias, especially along board edges.

### 2.5 DFT & DFM

- **Test Points:** Every power rail and critical signal should be accessible for probing. (See rule `DFT_TP_001`).
- **Silkscreen:** Labels should be clear and unambiguous. Mark pin 1, polarity, and component designators.
- **Fiducials:** At least two (preferably three) fiducial markers are required for automated pick-and-place assembly.
- **Acid Traps:** Avoid acute angles in copper traces where etchant can get trapped, over-etching the trace. Use 45° or rounded corners.

---
## Appendix A — High-Speed Signal Integrity

This appendix provides a deeper, more intuitive look into the physics of high-speed digital signals. At speeds above a few hundred MHz, or with signal rise times faster than ~1 ns, traces on a PCB stop behaving like simple "wires" and must be treated as **transmission lines**.

### A.1 Transmission Line Basics
A trace on a PCB has intrinsic inductance and capacitance per unit length. At high frequencies, the signal "sees" this distributed LC network as a characteristic impedance. When a signal traveling down the trace encounters a change in impedance (e.g., a connector, a via, or a stub), a portion of the signal energy is **reflected** back towards the source, corrupting the original signal.

**Key takeaway:** The goal of high-speed design is to maintain a **constant impedance** from the driver chip to the receiver chip.

### A.2 Characteristic Impedance (`Z0`)
This is the single most important parameter in high-speed design. It's determined by the physical geometry of the trace and the PCB stackup:
- **Trace width** (wider = lower impedance)
- **Dielectric height** (distance to the reference plane, thicker = higher impedance)
- **Dielectric constant** of the PCB material (`Er`, typically ~4.2 for FR-4)

For most single-ended signals (like clocks or address lines), a **50Ω** characteristic impedance is the industry standard. For differential pairs (like USB or PCIe), a **90Ω or 100Ω** differential impedance is common.

An AI reviewer should check for consistency. If a design mentions "high-speed USB," it should verify that the layout notes or manufacturing files specify a controlled impedance build. This directly relates to ontology rules like `HS_SER_001`.

### A.3 Crosstalk
Crosstalk is the unwanted coupling of energy between two adjacent traces (aggressor and victim). When a signal travels down the aggressor trace, its electromagnetic field can induce a voltage on the victim trace, creating noise.

**Mitigation:**
1.  **Spacing:** Increase the space between traces. A common rule of thumb is the "3W rule," where the center-to-center spacing is at least 3 times the trace width.
2.  **Reference Plane:** A solid ground plane beneath the traces provides a strong return path, containing the fields and reducing crosstalk. Routing over a split plane (`HS_DIFF_001`) dramatically increases crosstalk.
3.  **Guard Traces:** In some cases, a grounded "guard trace" can be run between two signals, but it must be heavily stitched to the ground plane with vias to be effective.

### A.4 Eye Diagrams & Jitter
An eye diagram is a visualization used to assess the quality of a high-speed signal. It is formed by overlaying multiple signal transitions on an oscilloscope.
- **"Open" Eye:** A large, clean opening in the center of the diagram indicates a high-quality signal with low noise and low jitter.
- **"Closed" Eye:** A small or fuzzy opening indicates poor signal integrity, often due to reflections, crosstalk, or impedance mismatches. The receiver may struggle to distinguish between a '1' and a '0'.

**Jitter** is the timing variation of a signal's edges from their ideal positions. Excessive jitter shrinks the eye opening horizontally, reducing timing margin and increasing the bit error rate (BER). It is a primary failure mode addressed by rules like `HS_SER_002` which limit impedance discontinuities from vias and plane crossings.

---
## Appendix B — Analog Design & Op-Amp Stability

This appendix explores key considerations for robust analog circuit design, with a particular focus on operational amplifiers (op-amps) and data converters. Analog circuits are highly susceptible to noise, parasitic effects, and stability issues, demanding careful design and layout.

### B.1 Op-Amp Stability
Op-amps are fundamental building blocks, but they can oscillate if not properly stabilized.

-   **Large Capacitive Loads (`AN_OPAMP_002`):** Driving a large capacitive load (e.g., a long cable, a large decoupling capacitor) directly with an op-amp's output can create a pole in the feedback loop, leading to instability. An isolation resistor (series resistor) is often needed between the op-amp output and the capacitive load.
-   **Feedback Network Topology (`AN_OPAMP_003`):** The choice of feedback resistors and capacitors significantly impacts an op-amp's frequency response and stability. Incorrect component values or topologies can lead to unexpected gain, oscillations, or poor transient response.
-   **Phase Margin and Gain Margin:** These are key metrics from control theory used to predict stability.
    -   **Phase Margin:** The difference between the phase shift at unity gain frequency and -180°. A phase margin of 45-60° is generally desirable.
    -   **Gain Margin:** How much the gain can be increased before oscillation occurs.

### B.2 ADC Driver Requirements
Driving an Analog-to-Digital Converter (ADC) properly is crucial for achieving its specified performance.

-   **Bandwidth vs. Sampling Rate (`AN_ADC_002`):** The amplifier driving an ADC must have sufficient bandwidth to accurately capture the input signal at the ADC's sampling rate. Insufficient bandwidth can lead to signal attenuation, distortion, and increased settling time errors.
-   **RC Anti-Alias Filters (`AN_ADC_003`):** An RC low-pass filter at the ADC input is essential to prevent aliasing. Aliasing occurs when input frequencies above half the sampling rate (Nyquist frequency) are incorrectly interpreted as lower frequencies, corrupting the digital data. The filter's cutoff frequency must be carefully chosen.

### B.3 Sensor Front-End Design
Sensor interfaces often deal with very small, high-impedance signals, making them highly vulnerable to noise.

-   **High-Impedance Nodes Isolation (`AN_SENSOR_001`):** Traces connected to high-impedance inputs (e.g., pH sensors, photodiodes, electret microphones) are extremely sensitive to parasitic capacitance and noise pickup.
    -   **Guard Rings:** Routing a guard ring (a trace connected to a low-impedance reference, often the input buffer's non-inverting input or ground) around the high-impedance trace can absorb leakage currents and shield the signal from noise.
    -   **Shielding:** Keep noisy digital lines and power traces far away from sensitive analog front-ends. Use solid ground planes as shields.
    -   **Minimize Trace Length:** Keep high-impedance traces as short as possible.

---

## Appendix C — SMPS & Power Electronics

This appendix delves into the critical aspects of Switch-Mode Power Supply (SMPS) design and layout, which are often sources of significant noise and instability if not handled correctly.

### C.1 Simplified Buck/Boost Operation
SMPS circuits (like Buck or Boost converters) operate by rapidly switching an inductor, storing energy in its magnetic field and then releasing it to the load. This switching action allows for efficient voltage conversion, but also generates high-frequency current pulses.

-   **Buck Converter (Step-Down):** Switches the input voltage to produce a lower output voltage. Key components include the switching MOSFET(s), inductor, input capacitor (Cin), and output capacitor (Cout).
-   **Boost Converter (Step-Up):** Switches the output current to produce a higher output voltage.

### C.2 Layout "Dos and Don'ts"
Proper layout is paramount for SMPS to achieve stable operation, low noise, and good thermal performance.

#### **Dos:**
-   **Minimize Hot Loops (`PWR_BUCK_001`):** The path of high dI/dt (rate of change of current) needs to be as short and wide as possible. For a buck converter, this is the loop formed by the input capacitor, switching FET(s), and the output diode (if asynchronous) or lower FET (if synchronous). Place these components very close together.
-   **Capacitor Placement (`PWR_BUCK_002`):** Input and output capacitors must be placed directly adjacent to the switching IC's VIN/VOUT and GND pins, with minimal trace inductance. Use multiple small ceramic capacitors in parallel for lower ESL/ESR.
-   **Kelvin Sensing:** For accurate feedback, route the feedback trace from the output capacitor's positive terminal to the feedback pin, avoiding current paths.
-   **Thermal Management:** For components like MOSFETs, diodes, and inductors, provide ample copper pour and thermal vias underneath their pads to dissipate heat. (Related to `PWR_RATING_001`, `PWR_RATING_002` for component limits).

#### **Don'ts:**
-   **Long High-Current Traces:** Avoid long, thin traces in the switching paths, especially the hot loop.
-   **Sensitive Traces Near Switching Nodes:** Route feedback traces and other sensitive signals away from noisy switching nodes (SW node) and inductors.
-   **Ground Plane Interruptions:** Avoid cutting the ground plane beneath critical SMPS components, especially the hot loop, as this disrupts return currents and increases EMI.

### C.3 Compensation and Ringing
An SMPS is a closed-loop system, and like all such systems, it requires a compensation network to maintain stability and ensure good transient response.

-   **Compensation Network (`PWR_COMP_001`):** This is typically an RC network connected to the feedback pin, designed to shape the loop gain and phase response. Without proper compensation, the converter can oscillate or have poor load regulation.
-   **Ringing:** This is oscillatory behavior in voltage or current, often seen at switching nodes. It can be caused by parasitic inductance and capacitance, poor layout, or improper compensation. Excessive ringing can lead to increased EMI, efficiency loss, and even component damage (e.g., exceeding FET Vds ratings). Careful layout and snubber circuits (if needed) can mitigate ringing.

---
## Appendix D: Advanced High-Speed Design

This appendix expands on the high-speed design concepts introduced earlier, providing more detailed guidelines for practical implementation.

### D.1 Differential Pair Routing
Differential pairs are used for high-speed signals because they are resilient to common-mode noise.
- **Symmetry is Key:** Route differential pairs symmetrically. The two traces must be kept parallel and at a constant distance from each other.
- **Length Matching:** The lengths of the two traces in a pair should be matched as closely as possible (typically within 2-5 mils) to minimize skew.
- **No Vias (if possible):** Avoid using vias on differential pairs. If a via is necessary, use a via on both traces of the pair to maintain symmetry. Place ground vias near the signal vias to provide a continuous return path.
- **AC Coupling Capacitors:** If AC coupling is required, place the capacitors symmetrically on both traces.

### D.2 Return Path Vias
When a high-speed signal changes layers, its return current also needs to change layers.
- **The Problem:** If there is no nearby via for the return current to follow, it will find the nearest available path, creating a large current loop. This loop acts as an antenna, radiating EMI and increasing crosstalk.
- **The Solution:** Whenever a high-speed signal transitions through a via, place a ground via immediately adjacent to it. This provides a low-inductance path for the return current to follow the signal, minimizing the loop area.

### D.3 Serpentine Routing
Serpentine routing is used to add length to a trace to match the length of other traces in a bus.
- **Geometry:** Use curved or 45° bends for the serpentine. Avoid sharp 90° corners.
- **Spacing:** The spacing between adjacent segments of the serpentine should be at least 4 times the trace width to minimize coupling between segments.
- **Placement:** Place serpentine routing as close to the source of the mismatch as possible.

### D.4 Material Selection
For very high-speed designs (multi-gigabit), the choice of PCB material becomes critical.
- **FR-4:** Standard FR-4 is lossy at high frequencies. The dielectric constant (Dk) and loss tangent (Df) of FR-4 can cause significant signal degradation.
- **Low-Loss Materials:** Materials like Rogers RO4350B or Isola I-Speed offer lower Dk and Df, resulting in better signal integrity for high-speed signals. These materials are more expensive than FR-4.

---
## Appendix E: Design for Testability (DFT)

Design for Testability (DFT) is the practice of designing a board to be easily and effectively tested during manufacturing. Good DFT reduces test costs and improves product quality.

### E.1 Test Points
- **What to Test:** Provide test points for all power rails, critical signals, and programming interfaces (e.g., JTAG, SWD).
- **Size and Shape:** Test points should be round or square pads with a diameter of at least 35 mils (0.9mm), with 50 mils (1.27mm) being a common and robust size. They can be exposed pads, vias, or through-hole pins.
- **Clearance:** Maintain a minimum of 100 mils (2.54mm) between test points to accommodate test probes. Keep test points at least 125 mils (3.175mm) from the board edge.
- **Distribution:** Distribute test points evenly across the board to avoid concentrating mechanical stress from a test fixture in one area.

### E.2 Test Fixtures and Tooling Holes
- **In-Circuit Test (ICT):** ICT uses a "bed-of-nails" fixture to contact test points on the bottom of the board. For ICT, all test points should be on one side of the board.
- **Flying Probe Test (FPT):** FPT uses robotic probes to contact test points. It is more flexible than ICT but slower.
- **Tooling Holes:** Include at least two, preferably three, non-plated tooling holes in the corners of the board. These are used to align the board in the test fixture. They should be asymmetrically placed to ensure correct orientation.

### E.3 JTAG/Boundary Scan
- **What it is:** JTAG (Joint Test Action Group) is a standardized interface for testing and debugging integrated circuits. It allows for "boundary scan" testing, which can verify connections between ICs without needing physical test points for every pin.
- **Implementation:** If using ICs that support JTAG, connect the JTAG signals (TDI, TDO, TCK, TMS, and optionally TRST) to a standard JTAG header. This allows for automated testing of pin-level connectivity.

---
## Appendix F: Advanced Analog and Mixed-Signal Design

This appendix builds on the mixed-signal concepts to provide more nuanced guidelines.

### F.1 The Grounding Dilemma: To Split or Not to Split?
- **The Modern Approach: Unified Ground Plane:** For most mixed-signal designs, a single, solid ground plane is the preferred approach. This provides the lowest impedance return path for all signals.
- **Partitioning, Not Splitting:** Instead of splitting the ground plane, partition the layout. Keep digital components and traces in one area of the board and analog components and traces in another. Digital return currents will naturally follow the digital traces, and analog return currents will follow the analog traces, minimizing interaction.
- **When to Consider a Split:** In some rare cases, such as very high-resolution data acquisition systems or when required by a specific component datasheet, a split ground plane may be necessary. If a split is used, the two ground planes should be connected at a single point (a "star ground"), typically near the ADC or DAC. Signals should never cross the split.

### F.2 Powering Mixed-Signal Devices
- **Separate Power Supplies:** Use separate power supplies for the analog and digital sections of the board. Even if they are the same voltage, this prevents digital switching noise from coupling into the analog power rails.
- **Filtering:** Use ferrite beads and capacitors to filter the power supplies for analog components. The ferrite bead should be placed between the digital and analog power sections.
- **Decoupling:** As with all ICs, provide local decoupling capacitors for the analog and digital power pins of mixed-signal devices like ADCs and DACs. Place them as close to the pins as possible.

### F.3 Routing in a Mixed-Signal Environment
- **Keep them Separated:** Do not route digital traces through the analog section of the board, and vice-versa.
- **Orthogonal Routing:** If digital and analog traces must cross, they should do so at a 90-degree angle to minimize capacitive coupling.
- **Guard Traces:** For very sensitive analog signals, consider using guard traces. A guard trace is a grounded trace routed alongside the sensitive signal trace to shield it from noise. The guard trace must be well-grounded with vias along its length.

---
## Appendix G: Design for Manufacturing (DFM)

Design for Manufacturing (DFM) encompasses all the design decisions that affect whether a PCB can be reliably and cost-effectively fabricated and assembled. Poor DFM can lead to 20-30% increases in scrap rates, 15% higher production costs, and weeks of schedule delays. This appendix covers the critical DFM rules that every designer should follow.

### G.1 Trace Width and Spacing

Trace geometry is fundamental to manufacturability. The PCB fabrication process involves etching copper, and the achievable resolution depends on the manufacturer's capabilities and the copper weight.

**Minimum Trace Width by Copper Weight:**
| Copper Weight | Minimum Trace/Space |
|---------------|---------------------|
| 1 oz (35µm)   | 3-4 mil (0.075-0.1mm) |
| 2 oz (70µm)   | 5 mil (0.125mm) |
| 3 oz (105µm)  | 9 mil (0.23mm) |
| 4 oz (140µm)  | 10 mil (0.25mm) |

**Recommendations:**
- Use 6 mil (0.15mm) trace/space as the standard minimum for cost-effective manufacturing.
- Traces below 4 mil require advanced processes and significantly increase cost.
- Apply the **3W Rule**: Center-to-center spacing of 3x trace width reduces crosstalk by ~70%.
- Apply the **10W Rule**: Center-to-center spacing of 10x trace width reduces crosstalk by ~95%.

### G.2 Via Design and Annular Ring

The annular ring is the copper pad area surrounding a drilled hole. Manufacturing tolerances in drilling mean that holes may not be perfectly centered, so adequate annular ring width is critical for reliable connections.

**Key Parameters:**
- **Annular Ring:** Minimum 10 mil (0.25mm) for mechanically drilled vias.
- **Via Pad Size:** Drill size + 10 mil minimum (e.g., 12 mil drill → 22 mil pad).
- **Component Hole Pad Size:** Drill size + 14 mil minimum.
- **Minimum Via Drill:** 0.15mm (mechanical), 0.075mm (laser). Vias below 0.25mm typically cost extra.

**Inner Layer Considerations:**
Inner layer annular rings are especially critical because defects cannot be repaired. IPC Class 3 requires minimum 1 mil internal and 2 mil external annular ring, but designing to larger margins improves yield.

### G.3 Acid Traps

An acid trap is a geometry that can trap etchant during PCB fabrication, causing over-etching and potentially creating open circuits.

**What Creates Acid Traps:**
- Acute angles (less than 90°) where traces meet pads
- Sharp corners in trace routing
- Small, nearly enclosed areas in copper pours

**Prevention:**
- Route traces to pads at 45° or 90° angles.
- Use 45° chamfers or rounded corners instead of sharp 90° turns.
- Avoid creating small enclosed copper areas where etchant can pool.
- Run DFM checks to automatically identify potential acid traps.

### G.4 Solder Mask Design

Solder mask protects copper from oxidation and prevents solder bridges during assembly. Proper solder mask design is essential for reliable soldering.

**Design Rules:**
- **Solder Mask Web:** Minimum 4 mil between adjacent mask openings (5 mil for non-green colors).
- **Solder Mask Clearance:** 2-4 mil larger than copper pads.
- **Solder Mask Dam:** Ensure adequate mask between fine-pitch component pads to prevent bridging.

**Common Issues:**
- **Solder Mask Slivers:** Thin strips of mask between closely spaced pads can flake off and cause debris. Minimum sliver width is 4 mil.
- **Missing Mask Between Pads:** If the mask web is too narrow, the manufacturer may remove it entirely, potentially causing solder bridges.

### G.5 Silkscreen Guidelines

Silkscreen provides visual reference for assembly and debugging. Poor silkscreen design can interfere with soldering or be illegible.

**Clearance Requirements:**
- Minimum 6 mil clearance from pads, vias, and solder mask openings.
- Never place silkscreen over exposed copper or SMT pads.
- Standard silkscreen-to-hole spacing: 8 mil.

**Legibility Requirements:**
- Minimum line width: 4 mil.
- Minimum font height: 40 mil (1mm) for reliable readability.
- Minimum stroke width: 6 mil.
- Use sans-serif fonts for best clarity.

**Best Practices:**
- Orient all text to be readable from one or two directions (avoid random rotation).
- Always mark pin 1 and component polarity.
- Include reference designators near components.
- Align text consistently across the board.
- **Label every connector with its function** (`DFT_CONN_LABEL_001`): Reference designators like "J3" do not tell a technician what a connector is for. Add a descriptive label (e.g., "USB", "SWD", "CAN BUS", "PWR 12V") adjacent to each connector. This reduces assembly errors, speeds up debugging, and is essential for field service.

### G.6 Panelization

Most PCBs are manufactured in panels containing multiple boards. Proper panelization design affects assembly yield and board quality.

**V-Score Guidelines:**
- Keep copper and components at least 1mm from V-score lines.
- Pull inner layer planes back 1mm from V-grooves.
- V-score residual thickness: 0.3-0.5mm for balance between handling strength and easy separation.
- Add jump scoring on leading/trailing edges to prevent array warping in wave solder.

**Breakaway Tab Guidelines:**
- Place tabs every 2-3 inches along board edges.
- Keep SMT components 3mm (1/8 inch) from perforation holes.
- **Critical:** Keep MLCCs at least 6mm (1/4 inch) from perforations—stress from depaneling can crack ceramic capacitors.
- First tab should be 10-12mm from board corners.

**Panel Rails:**
- Add 5-10mm rails around the panel for handling and fixtures.
- Rails provide space for fiducials and tooling holes.

### G.7 Fiducial Marks

Fiducials are alignment targets used by pick-and-place machines for accurate component placement.

**Requirements:**
- **Quantity:** Minimum 3 fiducials per panel/board in an L-shaped pattern.
- **Size:** 1mm diameter (acceptable range: 1-3mm). All fiducials must be the same size.
- **Clear Area:** Maintain clearance of at least 2x the fiducial radius (3x preferred) around each mark—no copper, silkscreen, or solder mask in this zone.
- **Placement:** At least 5mm from V-score lines or breakaway tabs, at least 3mm from board edges.
- **Asymmetry:** Place fiducials asymmetrically to prevent board orientation errors.

**Local Fiducials:**
For fine-pitch components (BGA, QFP with pitch ≤0.5mm), add local fiducials near the component for enhanced placement accuracy.

### G.8 Board Edge Clearance

Copper too close to board edges can be exposed during routing, leading to shorts, corrosion, or delamination.

**Clearance Requirements:**
- Minimum 10 mil (0.25mm) from copper to board edge.
- Account for routing tolerance (typically ±4 mil).
- Pull ground pours back from edges.

**Exceptions:**
- Castellated edges (plated half-holes) require specific manufacturer guidance.
- Edge-plated boards for RF shielding have different requirements.

### G.9 Copper Slivers

Copper slivers are thin, narrow copper features that can break off during manufacturing, causing shorts or debris.

**Prevention:**
- Eliminate copper features narrower than 6 mil.
- Remove isolated copper islands with no electrical purpose.
- Check pour/fill areas for thin necks or appendages.
- Run DFM checks to identify sliver conditions automatically.

### G.10 Component Placement Near Board Edges

Components placed too close to board edges are at risk during depanelization, board handling, and automated assembly. This is distinct from copper-to-edge clearance—components have larger keep-out requirements.

**Why It Matters:**
- **Depanelization stress:** V-scoring and tab routing create mechanical stress that can crack solder joints or damage components near edges.
- **Pick-and-place access:** Assembly machines need clearance for nozzles to place components; tall nearby components or edge proximity can block access.
- **Handling damage:** Board edges are touched during handling, inspection, and testing.
- **ICT fixtures:** In-circuit test fixtures need edge clearance for vacuum seals.

**Clearance Requirements:**
| Condition | Minimum Clearance |
|-----------|-------------------|
| Standard board edge | 100 mil (2.5mm) |
| V-score or tab-routed edge | 5mm |
| Tall components (>5mm height) | Additional clearance based on height |
| Test points (for ICT) | 100 mil from edge |
| Connectors | 3mm minimum |

**Best Practices:**
- Orient components near edges **parallel to the board outline**. Components at an angle experience non-uniform stress during depaneling and may tear from pads.
- Keep heavy or tall components away from edges—they're more susceptible to handling damage and can interfere with conveyor systems.
- Place connectors near edges (for accessibility) but maintain minimum clearance for depaneling.
- Consider the assembly panel, not just the individual board—components near internal panel cuts need the same clearance.

### G.11 DFM Checklist Summary

Before releasing a design for fabrication, verify:

| Check | Minimum Value |
|-------|---------------|
| Trace width | 6 mil (standard), 4 mil (advanced) |
| Trace spacing | 6 mil (standard), 4 mil (advanced) |
| Via annular ring | 10 mil |
| Via drill size | 0.25mm (cost-effective) |
| Solder mask web | 4 mil (green), 5 mil (other colors) |
| Silkscreen clearance | 6 mil from pads |
| Silkscreen line width | 4 mil |
| Silkscreen font height | 40 mil |
| Copper to board edge | 10 mil |
| Component to board edge | 100 mil (2.5mm) |
| Component to V-score/tab edge | 5mm |
| Fiducial count | 3 minimum |
| Fiducial diameter | 1mm |
| Component to V-score | 1mm |
| MLCC to breakaway tab | 6mm |

**IPC Standards Reference:**
- IPC-2221: Generic Standard on Printed Board Design
- IPC-A-600: Acceptability of Printed Boards
- IPC-7351: Generic Requirements for Surface Mount Design
- IPC-SM-840: Qualification and Performance of Permanent Solder Mask

---
## Appendix H: Schematic Review Checks

This appendix provides systematic schematic review guidelines based on common errors that lead to board respins. A thorough schematic review catches the majority of issues before they become expensive layout or manufacturing problems.

### H.1 Net and Connection Verification

Net connectivity issues are the most common source of schematic errors and often the most costly to fix.

**Single-Pin Nets (`SCH_NET_002`):**
- Run ERC (Electrical Rule Check) to identify nets with only one connection
- These typically indicate forgotten connections or incomplete wiring
- Use "no connect" symbols for intentionally floating pins to distinguish from errors

**Net Name Consistency (`SCH_NET_003`):**
- The same signal must have identical names everywhere
- Watch for case sensitivity issues (VCC vs Vcc vs vcc)
- Check for separator inconsistencies (VCC_3V3 vs VCC-3V3 vs VCC3V3)
- Typos in common character pairs (0/O, 1/l/I) cause hidden disconnections

**Duplicate Net Names (`SCH_NET_004`):**
- Using "VCC" for multiple voltage rails shorts them together
- Use explicit voltage values: 3V3, 5V0, 1V8, not generic VCC/VDD
- Power domains should have clear, distinct names

### H.2 Component Application Verification

**IC Datasheet Compliance (`SCH_IC_001`):**
- Read the complete datasheet, not just the pinout
- Check application circuits and reference designs
- Review errata documents for known issues
- Verify recommended external component values

**Floating Input Prevention (`SCH_FLOAT_001`):**
- CMOS inputs must never float—they oscillate between rails
- Tie unused digital inputs to ground or VCC (check datasheet preference)
- ADC inputs need defined bias voltage, not floating
- Consider weak pull resistors for inputs that may be used in future revisions

### H.3 Component Value and Rating Verification

**Value Sanity Check (`SCH_VAL_001`):**
Common transcription errors include:
- 10 vs 10k vs 10M (factor of 1000 errors)
- 100 vs 100k (missing 'k')
- 4.7 vs 47 (decimal point errors)
- p vs n vs u prefix confusion

**Polar Capacitor Verification (`SCH_POL_001`):**
- Verify polarity direction on schematic matches circuit voltage
- Voltage rating should be ≥1.5x maximum applied voltage
- Check for reverse voltage during power sequencing
- Electrolytic capacitors can fail violently if reverse biased

**DNP Status (`SCH_DNP_001`):**
- Review all "Do Not Populate" marked components
- Verify optional variants are correctly flagged
- Ensure BOM matches schematic DNP status
- Test DNP configurations before production

### H.4 Protection and Safety

**Relay and Inductive Load Protection (`PWR_RELAY_001`):**
- Relay coils, solenoids, and motors need flyback diodes
- Place diode cathode to positive terminal
- Use fast recovery diodes for faster turn-off
- Diode must handle coil current

**Overcurrent Protection (`PWR_FUSE_001`):**
- Size fuses to protect wiring and connectors, not just load
- Consider resettable PTCs for user-accessible circuits
- Verify interrupting capacity exceeds possible fault current
- Critical for battery-powered and high-current designs

### H.5 Experimental Options

**Design Flexibility (`SCH_OPT_001`):**
When behavior is uncertain, add options to tune circuit:
- Optional series resistor positions (populate with 0Ω default)
- Optional parallel capacitor footprints
- Jumper options for configuration selection
- DNP positions for alternate component values

### H.6 I2C Address Documentation

I2C address conflicts are a common source of board bring-up failures. Because multiple devices share a two-wire bus, every device must have a unique slave address. Documenting addresses on the schematic makes conflicts visible during review rather than during debugging.

**Address Annotation (`SCH_I2C_001`):**
- Annotate the hex I2C address (e.g., `0x48`) near each I2C device symbol on the schematic
- Document the state of address configuration pins (A0, A1, A2) that produce the annotated address
- For fixed-address devices, note the address and reference the datasheet
- Include both the 7-bit address and the read/write byte values if the design documentation uses 8-bit notation

**Address Conflict Detection (`SCH_I2C_002`):**
- Verify that no two devices on the same I2C bus share the same slave address
- Common conflict scenarios:
  - Two identical sensors (e.g., two TMP102 temperature sensors) with address pins in the same configuration
  - A fixed-address device (e.g., EEPROM at `0x50`) conflicting with another device that defaults to the same address
  - Forgetting that some devices occupy multiple addresses (e.g., 16-bit I/O expanders using two consecutive addresses)
- Mitigation strategies:
  - Use address configuration pins to assign unique addresses
  - Use an I2C multiplexer (e.g., TCA9548A) to create separate bus segments
  - Assign devices to different I2C bus instances on the MCU

---
## Appendix I: Component Selection Guidelines

Component selection significantly impacts reliability, performance, and cost. This appendix covers critical selection criteria for passive components.

### I.1 Capacitor Selection

**Dielectric Material Selection:**

| Dielectric | Characteristics | Use Cases |
|------------|-----------------|-----------|
| C0G/NP0 | Stable with voltage, temperature, time | Oscillators, precision filters, low-noise circuits |
| X5R | ±15% over -55°C to +85°C, DC bias derating | General decoupling, bulk bypass |
| X7R | ±15% over -55°C to +125°C, DC bias derating | General decoupling, higher temp applications |
| Y5V | -82% to +22% over temp, severe DC bias derating | Non-critical bulk only (avoid for timing/filtering) |

**DC Bias Derating (`COMP_CAP_001`):**
Class 2 ceramics (X5R, X7R, Y5V) lose capacitance under DC bias:
- Y5V can lose up to 80% at rated voltage
- X7R typically loses 20-40% at rated voltage
- Always check manufacturer's DC bias curves
- Select voltage rating 2-3x applied voltage for full capacitance

**ESR and ESL Considerations (`COMP_CAP_006`):**
- SMPS output capacitors: ESR affects stability and ripple
- High-frequency decoupling: low ESL critical (use X2Y, reverse geometry)
- Parallel multiple smaller caps for lower effective ESR/ESL

**Electrolytic Limitations:**
- High leakage current (`COMP_CAP_003`): avoid for sample-and-hold
- Ripple current affects life (`COMP_CAP_005`): life halves per 10°C above rated
- ESR increases with age and cold temperature
- Consider polymer aluminum for lower ESR and leakage

### I.2 Resistor Selection

**Technology Comparison:**

| Type | Noise | Tempco | Linearity | Cost | Notes |
|------|-------|--------|-----------|------|-------|
| Thick Film | High 1/f | 100-250 ppm/°C | Poor | Low | Standard general purpose |
| Thin Film | Low | 25-50 ppm/°C | Excellent | Medium | Precision applications |
| Metal Film | Very Low | 15-50 ppm/°C | Good | Medium | Low noise, precision |
| Wire Wound | Lowest | 5-20 ppm/°C | Excellent | High | Highest precision, inductive |

**Low-Noise Applications (`COMP_RES_001`):**
- Thick-film 1/f noise can dominate in sensitive circuits
- Use thin-film or metal-film for audio, sensor, and precision analog
- 1/f noise increases with resistance value
- Check noise index specification in datasheet

**Precision Applications (`COMP_RES_002`):**
- Thick-film nonlinearity causes distortion
- Temperature coefficient mismatch causes gain drift
- Use resistor networks for matched tempco
- Thin-film provides best overall precision

**Power Derating (`COMP_RES_003`):**
- Calculate P = I²R for each resistor
- Derate to 50% of rated power for reliability
- Account for ambient temperature in derating
- Use larger package for significant dissipation

### I.3 Inductor Selection

**Saturation Current (`COMP_IND_002`):**
- Most critical parameter for power inductors
- Select Isat ≥ 1.3x peak operating current
- Saturation decreases with temperature
- Ferrite cores saturate abruptly; powder cores saturate gradually

**Tolerance and Q Factor:**
- Cored inductors can have ±20% tolerance (`COMP_IND_001`)
- Q factor varies with frequency (`COMP_IND_004`)
- Air-core inductors have highest Q but larger size
- Match tolerances in filter applications

**Self-Resonant Frequency (`COMP_IND_003`):**
- Operating frequency must be well below SRF
- Above SRF, inductor becomes capacitive
- Rule of thumb: SRF ≥ 10x operating frequency
- Check impedance vs frequency curves in datasheet

---
## Appendix J: Hans Rosenberg Checklist Reference

This appendix documents the design review process from Hans Rosenberg's "First Time Right Electronics" checklist, a systematic approach to catching common electronics design errors before manufacturing.

**Source:** Hans Rosenberg, hans-rosenberg.com

### J.1 Schematic Phase Checks

Before proceeding to layout, verify:

1. **Net Integrity**
   - No single-pin (orphan) nets
   - Consistent naming across all sheets
   - No duplicate names for different signals
   - All cross-sheet labels have matching destinations

2. **Component Application**
   - Every IC applied per datasheet requirements
   - No floating digital or ADC inputs
   - Component values checked for transcription errors
   - DNP status verified for all optional components

3. **Power and Protection**
   - Polar capacitor polarity verified
   - Voltage ratings adequate with margin
   - Relay/inductor flyback protection present
   - Fuses sized for safety requirements

### J.2 Component Selection Phase

Critical parameter verification:

1. **Capacitors**
   - DC bias derating for ceramic types
   - Voltage rating margin (≥1.5x)
   - ESR/ESL requirements for SMPS
   - Ripple current rating for electrolytics

2. **Resistors**
   - Power rating with 50% derating
   - Noise index for low-noise circuits
   - Tempco matching for precision applications
   - Inductance consideration for HF

3. **Inductors**
   - Saturation current margin (≥1.3x peak)
   - SRF above operating frequency
   - Q factor for resonant circuits
   - Tolerance for filter applications

### J.3 Thermal Design Phase

1. **Power Dissipation Analysis**
   - Calculate dissipation for each power component
   - Identify hottest components
   - Determine required thermal solutions

2. **Temperature Rise Verification**
   - Calculate junction temperature: Tj = Ta + (θja × Pd)
   - Verify 20°C margin below maximum
   - Account for worst-case ambient

3. **Thermal Solutions**
   - Heatsink sizing if required
   - Forced cooling if passive insufficient
   - Component spreading for heat distribution

### J.4 Mechanical Verification

1. **Enclosure Compatibility**
   - Board outline matches enclosure
   - Mounting holes in correct positions
   - Component height restrictions verified
   - UI elements align with cutouts

2. **Heatsink Integration**
   - Heatsink fitment verified with 3D model
   - Mounting hardware clearance confirmed
   - Thermal interface gap appropriate

### J.5 Layout Phase Checks

1. **Placement**
   - Reserve routing channels for critical signals
   - Minimize critical trace lengths
   - Separate aggressors from sensitive circuits
   - Logical placement minimizes crossings

2. **Library Verification**
   - Print 1:1 and verify footprints with parts
   - Pin numbers match datasheet exactly
   - Connector orientations verified

3. **Stackup**
   - Each signal layer has ground reference
   - 4+ layers for RF and high-DR designs
   - Standard via size (≥0.3mm) where possible
   - Trace/space ≥0.15mm for cost control

### J.6 DFT/DFM Verification

1. **Design Rule Checks**
   - Layout DRC passed with no errors
   - Connectivity check shows 100% routed
   - Paste layer verified for each component

2. **Assembly Preparation**
   - Fiducials placed for P&P alignment
   - Board identification text added
   - Layer markers for stackup verification
   - BOM has order codes for all parts

3. **Manufacturing Verification**
   - Courtyard spacing adequate
   - Trace current capacity verified
   - Copper balance checked
   - Ground planes without problematic slots

### J.7 Validation Phase

1. **Prototype Build**
   - Assemble prototype before production
   - Document all issues encountered
   - Update design based on learnings

2. **Parameter Verification**
   - Measure all design parameters
   - Verify against specifications
   - Test under worst-case conditions

3. **Production Readiness**
   - Complete validation testing
   - Environmental testing as appropriate
   - EMC pre-compliance verification
   - Design approval documented

---
## Appendix K: Aerospace & Aviation Design

Aerospace boards (general aviation, aerobatic, rotorcraft, military) face environmental and reliability requirements that commercial-grade designs do not — sustained high-G vibration, deep thermal cycling, alternator-bus transients, lightning-induced surges, single-fault tolerance, decades-long service life, and field-installation by mechanics rather than factory technicians. This appendix collects the rules and citations that distinguish aerospace-grade hardware design from commercial.

The rules summarized here back the `AERO_*` rule family in the ontology.

### K.1 Mechanical retention beyond solder fillet (`AERO_VIB_001`)

**Standards:** AS-50881 (aerospace wiring & interconnect), MIL-STD-202 Method 204 (vibration testing), IEC 60068-2-6 (random vibration), IEC 60068-2-27 (shock), IPC-A-610 Class 3 §5.5.

**The problem:** PCB lead solder fillets are sized for thermal cycling, not for sustained high-G vibration of components with significant body mass. A 4 g relay subjected to +6 G aerobatic loading at 10–500 Hz random vibration applies cyclical stresses to its solder meniscus that fatigue-crack the leads in hundreds of hours. Commercial-grade products either don't see this vibration profile or are tolerant of single-component failure; aerospace boards rarely are.

**Mass threshold rule of thumb:**
- Components below ~1 g: solder fillet alone is generally adequate.
- 1–3 g: assess case-by-case based on vibration profile and lead geometry; through-hole leads more tolerant than SMD.
- Above 3 g: must have mechanical retention beyond solder. Common candidates: relays, radial electrolytic capacitors (>6.3 mm diameter), large inductors and transformers, crystals and oscillators on tall lead frames, modules and daughter-cards.

**Retention methods (in order of typical preference):**
1. **RTV silicone stake** (per AS-50881 Method 13) — apply at two opposite leads (or body-to-PCB joint for radial-lead parts). Common materials: MG Chemicals 4226A, Dow CV-2566, DAP 100% silicone. 24-hour ambient cure required before vibration testing.
2. **Mechanical clamp or strap** — used for components above 10 g (large transformers, big electrolytics) or for serviceable parts that would resist re-staking after replacement.
3. **Epoxy potting** — last resort for non-serviceable assemblies; eliminates field rework.

**Design implications:**
- Coat AFTER staking is fully cured. Conformal coating over wet RTV traps solvent and prevents adhesion.
- Stakes do double-duty as moisture seals when paired with conformal coat.
- Photograph the stake on the first article to set a visual standard for the assembly house.

### K.2 Leaded solder for Class 3 (`AERO_SLD_001`)

**Standards:** IPC J-STD-001 Class 3 (Pb-bearing exemption), JESD201 Class 1A (whisker test), MIL-PRF-19500 (semiconductor reliability), IPC-A-610 Class 3 §1.4.

**The problem:** Lead-free SAC305 (Sn-Ag-Cu) solder fails two requirements common to high-reliability assemblies:
1. **Tin whisker growth** — pure-tin surfaces grow conductive crystalline whiskers under mechanical or thermal stress, reaching millimeters in length over years. Whiskers bridge fine-pitch features (especially under fine-pitch BGAs and at QFN edge pads) and cause intermittent shorts that are nearly impossible to diagnose. RoHS-compliant lead-free assemblies in benign environments occasionally exhibit whisker failures; aerobatic / under-cowl environments with thermal cycling and mechanical stress accelerate growth.
2. **Solder joint brittleness** — SAC305 has higher Young's modulus and lower elongation-at-break than Sn63/Pb37. At -40 °C ambient (typical for aircraft cold start above 10,000 ft), SAC305 joints fracture under thermal expansion mismatches that Sn63/Pb37 absorbs plastically. Deep thermal-cycle endurance is markedly worse.

**Solution:**
- Specify **Sn63/Pb37 eutectic solder** in the fab order, citing the IPC J-STD-001 Class 3 / Pb-bearing exemption.
- Component lead finishes must be JESD201 Class 1A whisker-tested (matte tin, hot-air-leveled tin-lead, or vendor-equivalent). Vishay -E3 / -M3, ON Semi -G3, and similar suffixes meet the requirement.
- For DoD or NASA work, also conform to MIL-PRF-19500-derivative finishes where applicable.
- Reject SAC305 substitutions even when proposed as "equivalent" — they are not equivalent for Class 3 service.
- Hand-rework procedures must use leaded solder; mixed-alloy joints fail unpredictably.

### K.3 Reverse-polarity protection on aircraft DC bus (`AERO_RPP_001`)

**The problem:** Aircraft electrical systems are field-serviced and field-jumped. Battery installation in reverse, jumper-cable polarity error, or trans-battery jump from an aircraft with opposite polarity is a design-level certainty over the life of the board. Without active reverse-polarity protection, the first such event destroys downstream electronics. Schottky-only designs work but waste forward-drop power (~3 W at 8 A continuous) and have an open-failure mode that disables the load even after the polarity error is corrected.

**Preferred topology:**
- **Active ideal-diode controller + low-Rds(on) N-MOSFET.** The controller monitors the FET's V_DS and turns the FET on when V_anode > V_cathode, dropping I²·Rds(on) (typically <0.1 W at 8 A through a 1.4 mΩ FET) instead of the 0.4 V (~3 W) of a Schottky. Reverse polarity: the FET body diode blocks; the controller's discharge transistor pulls the gate to ANODE keeping the FET fully off.
- Suitable controllers: TI LM74700-Q1 (AEC-Q100 grade 1, 3.2–65 V), ADI LTC4376, Maxim MAX17612.
- Pair with an AEC-Q101 N-FET in the desired Vds class. For 14 V aircraft bus, a 30–40 V Vds part with sub-2-mΩ Rds(on) gives generous margin. D2PAK-3 (TO-263-3) is the standard package for >5 A.

**Common mistakes:**
- Bare Schottky in series — wastes power, requires heat-sink, opens at end-of-life.
- P-FET-only "high-side switch" — works but Rds(on) is typically 2–3× worse than equivalent N-FET, and gate-drive is more complex (bootstrap or charge pump). Acceptable below ~3 A continuous.
- Polyfuse in series — does not prevent reverse-polarity damage to active components downstream; it only limits reverse-current eventually.

### K.4 ISO 7637-2 / DO-160 input clamping (`AERO_TVS_001`)

**Standards:** ISO 7637-2 (road-vehicle electrical disturbances; aerospace adopts the test methodology for piston-engine aircraft with belt-driven alternators), DO-160 §16-22 (lightning-induced transients), LM74700-Q1 datasheet §8.2.1 / figure 8-1 (typical application with input TVS).

**The problem:** Aircraft electrical systems generate input transients that exceed any sane IC absolute-maximum:
- **Load dump (alternator field-decay):** When a contactor opens with the alternator field still energized, the field collapse produces an inductive spike on the bus. Magnitude depends on alternator size and field decay rate; 60 A alternators on 14 V buses commonly produce 80–100 V pulses lasting 250–400 ms with 100–500 mJ of energy. Equivalent to ISO 7637-2 pulse 5b on automotive.
- **Lightning-induced transients (DO-160 §16-22):** Indirect lightning effects on aircraft wiring produce damped sinusoidal transients with peak voltages exceeding 100 V and rise times of microseconds.

**Mitigation:**
- Place a **bidirectional TVS** (CA suffix on the SMBJ or SMCJ family) within ~50 mm of the active rectifier IC's ANODE pin, on the same input net.
- **Size the clamp voltage Vc(IPP) below the IC absolute-max with at least 1.5× derating margin.** Example: LM74700-Q1 ANODE abs-max = 80 V. Vishay SMCJ18CA clamps at 29.2 V at 51.7 A IPP; 80 V / 29.2 V = 2.7× margin, comfortable.
- **Choose 1500 W SMC-package parts (SMCJ series) over 600 W SMB-package parts (SMBJ series)** for the input clamp on aircraft buses. Pulse currents during alternator field-decay can exceed 25 A; SMBJ runs out of headroom while SMCJ has substantial margin.
- **Stitch the TVS GND pad to the GND plane with at least 2 dedicated vias** per pad. Single thermal-relief connections add inductance that lifts the effective clamp voltage during fast transients.
- **For the signal-side TVS** (cockpit-harness inputs that run alongside higher-voltage feeders), 600 W SMBJ parts are adequate — pulse currents are limited by signal-wire inductance.

### K.5 Conformal-coat masking (`AERO_TERM_001`)

**Standards:** IPC-CC-830B (conformal coating qualification), MIL-I-46058C Type UR (coating material spec).

**The problem:** Conformal coatings (HumiSeal 1A33A polyurethane, MG Chemicals 422C silicone-modified acrylic, etc.) are insulating polymers that prevent any subsequent solder or screw-clamp joint from making electrical contact. Aerospace boards routinely combine blanket-coated assemblies with field-serviceable terminals that must remain bare — failing to mask these terminals during the coat step produces a board that physically cannot be wired in the field.

**Features that must be masked:**
- **Turret posts and screw-terminal pads** — the brass post / screw face must remain conductive for ring-lug clamp contact.
- **Battery clips and harness connectors** — pin contacts must remain conductive.
- **NPTH mounting holes** — the inner annulus must remain conductive for chassis screw contact (or, conversely, the chassis ground design intentionally isolates the mount from PCB GND — see `AERO_GND_001` — but the bare copper either way must not be coated).
- **Test points** — if any are physically accessible.

**Mask materials:**
- HumiSeal MSK1500 latex peelable mask — the industry standard for irregular shapes, dries to a peel-off film.
- Kapton dots cut to size — clean removal, no residue, ideal for round flat features.
- Silicone caps (vendor-supplied) — for connector pins, threaded posts.
- Thread protectors — for internally threaded fasteners and posts.

**Process discipline:**
- Identify every masked feature in the work-instruction document.
- Photograph mask coverage on the first article both before coat and after demask; retain for traceability.
- Verify post-coat that bare copper / brass surfaces are bright and uncoated. Any visible film is a reject.
- Confirm masking expectations with the assembly house in writing — many CMs default to blanket coat without masking unless explicitly told.

### K.6 Single-point chassis ground (`AERO_GND_001`)

**Standards:** FAA AC 43.13-1B Ch 11 (mounting hardware torque, ring terminals, bonding); industry practice for aircraft DC systems.

**The problem:** Aircraft DC systems are not earth-referenced. Chassis ground is a return path for the airframe DC negative bus only and is intentionally separated from PCB signal ground except at one designated bonding point (typically a dedicated GND turret terminal). When PCB GND is also connected to the chassis through unkeepout copper around mounting holes, the mount screws become parallel ground returns:
- Each screw is a low-quality intermittent contact (vibration loosens it, corrosion increases its impedance).
- Different screws carry different portions of digital and motor return currents, creating ground potential differences across the board.
- The loops formed by the multiple parallel paths radiate EMI.
- Brass screw against tin-plated copper accelerates galvanic corrosion at every mount point.

**Solution:**
- **Copper keepout zone around every NPTH mounting hole, on every layer.** 4 mm radius is conservative for #6 hardware (covers screw head + lockwasher OD); larger for bigger hardware. Verify keepout on F.Cu, every inner layer, AND B.Cu — not just outer layers.
- **Single dedicated bonding turret** (or screw block) for chassis-to-PCB-GND attachment, placed near the chassis bond stud.
- **Stainless screw + lockwasher + nylock nut.** Avoid brass-on-tin combinations which are galvanically active.
- **Torque per FAA AC 43.13-1B Ch 11 Table 11-7:** #6-32 SS = 8 in-lb; #8-32 brass = 12 in-lb (brass thread crush limit).
- **Document the single-point bond expectation in the install drawing** so a maintainer doesn't accidentally bond multiple mount points.

### K.7 Color-coded ring-terminal posts (best-practice supplement)

While not formalized as an `AERO_*` rule, color-coded turret terminals dramatically reduce field-installation errors on aircraft boards. The Keystone 8191-X family (and its competitors' equivalents) use the same brass post and #8-32 thread across SKUs but vary the molded plastic head color:

| Color | Suffix | Convention |
|---|---|---|
| Red | -2 | Positive supply |
| Black | -3 | Ground / return |
| White | -4 | Neutral / signal |
| Blue | -5 | Output A or signal |
| Green | -6 | Active / "go" signal |
| Yellow | -7 | Cockpit-input signal |
| Nickel | (none) | Unrestricted use |

A red/black supply pair, plus distinct colors on signal and motor pairs, makes wiring errors visually obvious before power is applied. The cost premium is essentially zero (~$0.05 per terminal across colors), and the field-debug time saved on a single mistake far exceeds the lifetime cost.

### K.8 Citation reference

| Standard | Subject | Where it applies in this appendix |
|---|---|---|
| **FAA AC 43.13-1B Ch 11** | Aircraft electrical hardware torque, ring lugs, bonding | K.6 (mount torque), K.7 (#8-32 brass turret torque) |
| **IPC-A-610 Class 3** | High-reliability assembly acceptance | K.1 (vibration), K.2 (solder) |
| **IPC J-STD-001 Class 3** | High-reliability soldering | K.2 (Pb-bearing exemption) |
| **IPC-CC-830B** | Conformal coating qualification | K.5 (masking) |
| **MIL-I-46058C Type UR** | Polyurethane coating material spec | K.5 |
| **MIL-PRF-19500** | Semiconductor reliability | K.2 (lead finishes) |
| **MIL-STD-202 Method 204** | Vibration testing | K.1 |
| **AS-50881** | Aerospace wiring & interconnect | K.1 (RTV staking method 13) |
| **JESD201 Class 1A** | Tin-whisker test | K.2 (lead finish qualification) |
| **IEC 60068-2-6** | Random vibration testing | K.1 |
| **IEC 60068-2-27** | Shock testing | K.1 |
| **ISO 7637-2 pulse 5b** | Load-dump transient (automotive, applies to piston aircraft) | K.4 |
| **DO-160 §16-22** | Lightning-induced transients | K.4 |
| **AEC-Q100 / Q101 / Q200** | Automotive component qualification | underlies all AERO_RPP / AERO_TVS hardware choices |
