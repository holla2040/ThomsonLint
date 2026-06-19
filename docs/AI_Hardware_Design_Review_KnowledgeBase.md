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

### I.4 Voltage Regulator Selection (`COMP_REG_001`)

Regulators that dominate tutorials, dev boards, and $1 modules are frequently the wrong choice for a production design. They work on the bench, then fail in the field through thermal stress, EMC test failures, brownout resets, or counterfeit-part variability.

**Source:** John Teel, Predictable Designs, https://www.youtube.com/@PredictableDesigns — video "9 Voltage Regulators You Should NEVER Use in Your Product" (youtu.be/KM8I2idEsF4).

**Known-problematic parts and replacements:**

| Part | Why it fails in production | Use instead |
|---|---|---|
| 78xx series | ~2 V dropout burns power as heat; large package; poor transient response, PSRR, and noise | Synchronous buck (large step-down) or modern LDO (small step-down) |
| LM2596 | 150 kHz switching → large passives, high EMI; module layouts fail FCC/CE; heavily counterfeited | Synchronous buck switching ≥ 500 kHz |
| MC34063 | Uncontrolled switching waveforms, ~80% best-case efficiency, tricky compensation, high part count | Dedicated buck or boost IC for the topology needed |
| XL6009 / XL4015 (no-name switchers) | Unverifiable datasheets, no application support, parts vanish from the market | ICs from established vendors (TI, ADI, ST, onsemi, Microchip) stocked at authorized distributors |
| AMS1117 | Real dropout > 1 V at rated current despite "LDO" label; poor transient response; rampant counterfeits | Modern LDO with dropout < 250 mV and fast transient response (e.g., TPS793 / TPS799 class) |
| Cheap unshielded switcher modules | Radiated EMI fails FCC/CE; poor layout kills IC performance; batch-to-batch variation | Shielded module from a reputable supplier with EMC-compliant layout |
| HT7333 / HT7533 | No thermal shutdown; load regulation collapses above ~100 mA; PSRR rolls off above ~1 kHz | LDO with thermal protection and specs guaranteed across temperature |
| LM317 (and adjustable regulators generally) | Divider tolerance stack-up; open bottom resistor passes full input voltage to output; > 2 V dropout; no enable pin; 3.5–10 mA minimum load | Fixed-output LDO matched to the rail voltage |
| MCP1700 | 1.6 µA Iq is attractive, but 250 mA max and slow transient response cause brownout resets on load bursts | LDO combining low Iq with fast transient response and headroom for worst-case bursts |

**Selection principles (apply to any regulator, not just this list):**

- **Dropout headroom:** verify dropout at the *actual load current* against the *worst-case* input-to-output differential — including battery end-of-discharge voltage, not the nominal pack voltage.
- **Transient load profile:** size for the worst-case burst (Wi-Fi/cellular TX, motor start, wake from deep sleep), not steady-state. A part that passes steady-state bench testing can still brownout-reset the MCU in the field.
- **Linear vs. switching:** all power across a linear regulator's input-output gap is dissipated as heat. Use a buck converter for any large step-down; reserve LDOs for small differentials or noise-sensitive rails.
- **Fixed over adjustable:** if the rail voltage is known, a fixed-output part removes two resistors, their tolerance stack-up, and two open-circuit failure modes.
- **Protection:** require thermal shutdown and current limit for production parts.
- **Sourcing:** if it can't be bought from a major authorized distributor (Mouser, Digi-Key), it doesn't belong in the product. Verified datasheets, reference designs, and application support typically cost under $0.50/unit extra.
- **Never select on one headline spec** (cost, Iq, "LDO" in the title) — check the full datasheet picture across temperature and load.

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

## Appendix L — Vendor Part Number Conventions

This appendix documents conventions for identifying and looking up component part numbers from common distributors. The reviewer uses these to fetch datasheets and product details deterministically (see Step 3, "Self-Retrieve Missing Datasheets").

### L.1 LCSC

- **Format:** Prefix `C` followed by 4–8 digits (examples: `C84817`, `C52717`, `C49166832`).
- **Lookup URL:** `https://www.lcsc.com/product-detail/<LCSC_PN>.html`
- **Where they appear:** BOM exports, schematic component attributes, and `exports/*.pdf` datasheet filenames in this repo (e.g., `Boost - MT3608 - SOT23-6 - C84817.pdf`).
- **Notes:** The LCSC product page links to the manufacturer datasheet PDF and shows package, parametric data, and stock. Fetch the product page first; follow the datasheet link only if parametric data on the page is insufficient.

---
## Appendix M: Prototype-to-Production Readiness

A working prototype proves the concept; it does not prove the product can be built, tested, certified, and sold at a profit in volume. This appendix captures the five "gaps" a design must cross between a hand-tuned bench unit and a repeatable production run. For each gap it lists the design-review checks plus the field-failure pitfalls that stay hidden until scale exposes them. Many items are already enforced by other rules in this knowledge base (DFM in Appendix G, DFT in Appendix E, EMC/SI throughout, reliability in Appendix K) and are cross-referenced rather than duplicated; the four `PROD_*` ontology rules cover the gaps those appendices do not.

**Source:** John Teel, Predictable Designs, https://predictabledesigns.com — checklist "The 5 Gaps From Prototype to Production" (© 2026 Predictable Designs LLC).

### M.1 Manufacturing Consistency (`PROD_SOURCE_001`)

**Can it be manufactured consistently?** Ensuring the design works in automated factory production, not just on the one board you hand-tuned.

1. **Layout and assembly**
   - PCB laid out for automated assembly equipment (see Appendix G, DFM, and the `DFM_*` rules).
   - All hand-tuning removed from the build process — no trimming, selecting, or "tweak until it works" steps on the line.

2. **Sourcing and lifecycle** (`PROD_SOURCE_001`)
   - Every component verified available in production quantities, not just sample quantities.
   - Second sources identified for critical components, and end-of-life (EOL) / lifecycle status checked before the layout is locked.

3. **Margin and tolerances**
   - Design margin added to account for component tolerances (ties to the derating rules in Appendix I and `COMP_*`).
   - Units tested at the tolerance extremes, not just at typical values.

4. **Change control**
   - Every design change and revision documented (board revision header, see `DFT_SILK_*`).

**Watch out:**
- A design with no margin can work perfectly on the one board you hand-tuned, then fail on ~5% of units in production. On a 5,000-unit run that is 250 dead boards you pay to build, diagnose, and scrap.
- Undocumented hand-fixes are silent killers. Every tweak, reflowed joint, or jumper wire that never makes it into the design files becomes a defect the factory faithfully builds in at scale.

### M.2 Test at Scale (DFT — Appendix E, `DFT_*`)

**Can it be tested at scale?** Building testability into the product from day one. This gap is largely covered by the existing DFT rules; the checklist below is the production-test overlay.

1. **Access and coverage**
   - Test points added for key signals on the board (`DFT_TP_*`, `MS_I2C_001`).
   - Design for Testability (DFT) considered from the start, not retrofitted.

2. **Procedure and criteria**
   - Clear pass/fail criteria defined for each test.
   - Documented factory test procedure created.

3. **Cost and tooling**
   - Custom test-fixture development budgeted.
   - Per-unit test time verified against the cost target.

**Watch out:**
- A custom test fixture can cost thousands of dollars to design and build. If you do not plan for it, it shows up as a surprise expense right when you are trying to start production.
- Skip testability and you are left with two bad options: ship units that were never properly tested and eat the returns, or pay people to slowly hand-test every unit and watch your margin disappear.

### M.3 Real-World Survival (`PROD_ENV_001`)

**Will it survive the real world?** Designing for reliability in harsh operating conditions. Appendix K covers this for aerospace; `PROD_ENV_001` generalizes the discipline to any product.

1. **Environmental stress**
   - Environmental stress testing conducted across heat, cold, and humidity.
   - Tested in conditions matching the actual target use environments.

2. **Mechanical durability**
   - Vibration and thermal-cycle testing performed on solder joints.
   - Drop testing run on the finished enclosure.

3. **Power and longevity**
   - Battery performance tested across the full temperature range (capacity fade in cold, dropout headroom at end-of-discharge).
   - Long-term reliability verified under continuous use.

**Watch out:**
- A battery that behaves fine at room temperature can lose a large part of its capacity in the cold, and solder joints that look perfect can slowly crack from months of vibration.
- Reliability failures almost never show up on your bench while you are babying the product. They show up months later, in your customers' hands — the most expensive time possible to find them.

### M.4 Certification (`PROD_CERT_001`)

**Can it pass certification?** Meeting FCC, CE, UL, and other regulatory requirements. The EMC/SI rules throughout this KB give you the emissions margin; `PROD_CERT_001` covers the planning gap.

1. **Requirements and planning**
   - Certification requirements researched for the target markets.
   - Certification guidelines followed during the initial design, not after layout.
   - Certification testing budgeted, including the possibility of a retest.

2. **Design for compliance**
   - PCB layout designed to minimize EMI/EMC emissions (`EMC_*`, plus the high-speed SI rules).
   - Proper electrical isolation and safety spacing (creepage/clearance) ensured.
   - Pre-certified modules used where possible.

**Watch out:**
- A single failed certification attempt can mean a new PCB layout, a board re-spin, fresh prototypes, and another round of expensive lab testing. That adds months and tens of thousands of dollars.
- A pre-certified module will not save you if your own PCB layout or enclosure causes the problem. The rest of the product still has to be designed with testing in mind.

### M.5 Design-to-Cost (`PROD_COST_001`)

**Can you manufacture it at a profit?** Designing to cost from the beginning, because most of the cost is locked in at the design stage.

1. **Cost targets**
   - Total landed cost per unit calculated — not just parts.
   - Target manufacturing cost worked backward from the target selling price.
   - The design driven toward that cost target from day one.

2. **Cost drivers**
   - Component selection optimized for cost and availability.
   - Enclosure design evaluated for manufacturing efficiency.
   - Scrap rate, duties, and shipping factored into the cost model.

**Watch out:**
- Most of your product's cost is locked in at the design stage, in the parts you picked and the way you chose to build it. By the time you are in production, the cheapest changes are off the table.
- If the math does not work in production, both options are ugly: redesign a product you already paid to tool, or ship something that barely breaks even or loses money on every unit.

---
## Appendix N: Rigid-Flex PCB Design Review

Rigid-flex PCB design sits at the intersection of mechanical and electrical engineering in a way standard rigid-board design does not. In the flex zone, a single trace-routing decision drives impedance *and* long-term bend reliability simultaneously, and a stackup choice made in the first week of a project determines whether the bend radius is even achievable. Unlike rigid boards — where most problems can be corrected at the layout stage — rigid-flex failures are usually baked in at the stackup and floor-planning stage and only surface during fabrication, assembly, or environmental qualification, where they are expensive and often impossible to reverse.

This appendix captures a pre-fabrication verification framework for rigid-flex designs, organized by the ten design domains where rigid-flex errors most commonly originate, plus the industry-specific deltas for military, aerospace/space, medical, and automotive applications. Each item is tied to its governing standard — primarily **IPC-2223E** (the sectional design standard for flex and rigid-flex), **IPC-6013** (qualification and acceptance, with the **E** revision adding explicit transition-zone criteria), **IPC-2221** (conductor sizing and annular ring), and the **IPC-TM-650** test methods — so a reviewer knows not just *what* to check but *why* and *which clause* defines the acceptance criterion.

**Source:** Cadence Design Systems, www.cadence.com — design guide "Rigid-Flex PCB Design Review Checklist: A pre-fabrication design verification resource aligned with IPC-2223E, IPC-6013, IPC-2221, and IPC-TM-650" (© 2026 Cadence Design Systems, Inc.).

### N.1 Why rigid-flex is different

- **Mechanical and electrical are coupled.** One flex-zone trace decision sets both impedance and bend reliability at once; you cannot optimize them independently.
- **Decisions lock early.** Stackup, material, and floor-plan choices made before routing determine feasibility and cannot be undone after lamination.
- **Failures surface late.** Most rigid-flex defects appear at fabrication, assembly, or environmental qualification — the most expensive places to find them.
- **The flex zone is not a rigid zone.** It uses different materials (polyimide, RA copper, coverlay) with a different dielectric constant and different design rules. Simulate and rule-check the flex and rigid regions **separately**.
- **The transition zone is the single most failure-prone region.** Treat it as a first-class design object with its own dimensions and acceptance criteria.
- **Scope:** review N.2–N.10 for *every* rigid-flex design regardless of industry; add only the applicable N.11 industry deltas on top — they do not repeat the core checks.

### N.2 Bend Zone Design (IPC-2223E primary, IPC-6013)

The bend zone is the highest-risk region in any rigid-flex design and the leading cause of field failures. All bend parameters must be established **before routing begins**.

**Bend radius (calculate and document before routing):**
- Static (fold-once during assembly): minimum **6× total flex thickness** for single- and double-layer flex; **12×** for three or more flex layers.
- Dynamic (repeated flexing in operation): minimum **100×** single-layer, **150×** double-layer, **200×** multilayer.
- Expressed as the bend ratio **r/h** (r = minimum bend radius, h = total flex thickness). Multipliers rise with layer count; confirm total flex thickness and the required radius with the fabricator — material choice affects it.

**Construction rules:**
- No plated through-holes or vias in the bend zone — vias crack under mechanical stress.
- Enforce a via keepout of **0.050"–0.100" (1.27–2.54 mm)** from the flex-to-rigid transition line.
- No components in active bend zones (rigid stress concentration cracks solder joints).
- Route traces perpendicular to the bend line; use curved transitions, never 90° or sharp-angle turns (sharp angles concentrate stress).
- Stagger traces across layers — do **not** stack them. Stacked traces create an "I-beam" effect that drastically reduces flexibility and increases crack risk.
- Dimension the bend line and minimum bend radius on the fabrication drawing — the fabricator cannot verify compliance without it.

**Neutral axis design:**
- Position flex layers at the center of the stackup to locate conductors on the neutral axis, minimizing bending strain.
- Conductors smaller than 10 mils positioned inside the neutral bend axis (thin conductors withstand compression better than stretching).
- Maintain symmetric copper balance in the flex zone — asymmetric copper curls the board toward the heavy side.
- For tight radii with 3+ flex layers, specify **bookbinder (unbonded)** construction so layers slide relative to one another.

### N.3 Stackup and Material Selection (IPC-2223E, IPC-4203/1, IPC-6013)

Material decisions cannot be reversed after fabrication begins; confirm the stackup with the fabricator before routing.

**Stackup architecture:**
- Center flex layers in the overall construction and match rigid build-up above and below the flex zone in thickness and copper weight. Unequal rigid build-up creates differential-CTE warping during reflow. (This is *distinct* from neutral-axis positioning: neutral axis governs bend performance, overall stackup balance governs reflow warping — address both. Asymmetric layer counts are not automatically invalid but require explicit fabricator review.)
- All rigid sections share the same layer count and stackup (mixed layer counts cause differential thermal expansion and lamination problems).
- Place power/ground plane pairs on adjacent layers for distributed capacitance and low PDN inductance.
- Provide a stackup diagram differentiating rigid and flex zones with all layer boundaries and material callouts.
- Specify air-gap (unbonded) construction for high-flexibility multilayer flex sections.

**Flex-layer materials:**
- **Adhesiveless polyimide core** for flex layers — adhesive-based cores have high CTE mismatch and crack vias; adhesiveless is **mandatory for dynamic** flex (acrylic adhesive through the rigid portion must not exceed **10% of total construction thickness**).
- **Rolled-annealed (RA) copper** for all dynamic flex layers — superior ductility and fatigue resistance vs. electrodeposited (ED) copper; non-negotiable for dynamic flex. ED copper is acceptable for rigid sections only (more brittle).
- Minimum **0.25 oz** copper for flex zones; size conductors per IPC-2221 current-capacity tables.

**Rigid-section materials & the boundary:**
- High-Tg FR-4 (**Tg > 170 °C**) for rigid sections in Class 3 / high-reliability designs.
- **No-flow / low-flow prepreg** at the rigid-to-flex boundary to prevent resin flowing into the flex zone during lamination.
- Acrylic adhesive in the rigid section ≤ 10% of total construction (excess causes thermal-expansion mismatch and via cracking).

**Coverlay (replaces solder mask in flex):**
- Polyimide coverlay for flex zones — LPI solder mask cracks under repeated bending and is not acceptable.
- Coverlay engages the rigid area by **≈0.025" (0.64 mm)** overlap to seal the transition and prevent edge lifting.
- Typical coverlay thickness 12.5 µm or 25 µm polyimide + adhesive (choose by static vs. dynamic use).
- Laser-cut coverlay for fine-pitch component areas (≈0.2 mm minimum clearance; mechanical punching is too imprecise).
- IPC-6013 acceptance: no adhesive voids that propagate under flexing, no lifted edges, no adhesive wicking beyond limits.

**Stiffeners:**
- Specify stiffeners under all connector mounting areas (prevents solder-joint stress during mate/unmate).
- Material: FR-4 for components; polyimide for ZIF connectors or thin sections.
- Stiffeners must **not** extend into the active bend zone.
- Stiffener overlaps coverlay by **min 30 mil (0.76 mm)**; specify rounded corners (sharp corners initiate cracks).

### N.4 Trace Routing in Flex Zones (IPC-2223E, IPC-2221)

Routing decisions must account simultaneously for electrical performance and bending stress.

**Flex-zone routing rules:**
- Minimum trace width meets fabricator minimum (typically **0.005" / 0.127 mm**); minimum spacing typically **0.006" / 0.152 mm** (wider spacing reduces mechanical stress concentration).
- Curved transitions at all direction changes.
- Teardrop pad connections at all via-to-trace junctions in or near flex zones — **mandatory for Class 3**.
- Do not run traces parallel to the bend axis in the bend zone (parallel traces are more susceptible to delamination and cracking).
- No large solid copper pours in flex or bend areas — use a crosshatch pattern.

**Ground/power planes — crosshatch.** IPC-2223E requires crosshatch in flex zones but does not mandate a specific geometry; the designer defines it and confirms against fabricator capability:
- Hatch conductor width (HW): minimum **0.010" (0.25 mm)** for standard fabricators (narrower risks etching non-uniformity).
- Hatch pitch (HP): the longest opening dimension should not exceed **0.050" (1.27 mm)** (larger openings reduce shielding and create stiffness discontinuities).
- Orientation: hatch at **45°** to the bend axis (parallel/perpendicular concentrates stress at conductor junctions).
- Copper fill %: flexibility gain is proportional to copper removal — removing 30% gives minimal gain; **60–70% removal** produces meaningful improvement. The HW/HP ratio sets the fill %.
- Any change to hatch geometry on an impedance-controlled design requires impedance **re-simulation**.
- For impedance-controlled signals, specify a **narrow solid reference strip ≈2× the signal trace width** beneath each trace in place of crosshatch — explicitly designed and called out, verified by simulation; the remainder of the plane uses crosshatch.

**Transition-zone routing:**
- Gradual trace-width changes at the rigid-to-flex boundary — no abrupt neckdowns (they create mechanical stress and impedance discontinuities).
- Keep features on outer surfaces **≥0.025" (0.64 mm)** from the flex-to-rigid transition (the rolled edge can damage features placed too close).
- Apply strain-relief fillets to traces at the rigid-to-flex boundary (required per IPC-2223E figures).

**Controlled impedance in flex:**
- Use **flex-zone material properties** — polyimide Dk ≈ 3.4 differs from FR-4 (Dk ≈ 4.2–4.5); calculating with FR-4 values yields out-of-tolerance designs. Typical targets 50 Ω single-ended, 90–100 Ω differential.
- Impedance test coupons must reflect the composite flex structure including coverlay.
- Tolerance: **±10%** is the achievable baseline; **±5%** is extremely difficult in flex zones due to material movement.
- Specify IPC-TM-650 **Method 2.5.5.7** (TDR impedance) and **2.5.5.12A** (signal loss) on the fabrication drawing for high-speed designs.

### N.5 Via and PTH Design (IPC-2223E, IPC-6013)

Via placement relative to the flex zone and transition line is one of the most common rigid-flex failure sources.

**Placement:**
- **No vias in dynamic flex zones** (strictly prohibited — vias crack under repeated bending).
- Vias in static flex zones reinforced with teardrop pads; blind/buried vias preferred over PTH in flex areas (less mechanically disruptive).
- PTH/via keepout from the flex-to-rigid transition line: **min 0.050" (1.27 mm)**, **0.100" (2.54 mm) recommended** for margin.
- Vias on or near stiffener edges maintain **50 mil (1.27 mm)** clearance from the stiffener edge (differential stiffness raises cracking risk).

**Annular ring & plating (IPC-6013 class-dependent):**
- Class 2: controlled breakout permitted. Class 3: no fractured or lifted rings, no breakout.
- PTH copper plating: Class 3 minimum average hole-wall **0.001" (25.4 µm)**, no point below **0.0007" (17.8 µm)**; Class 2 average **0.0008" (20.3 µm)**. Confirm against IPC-6013 tables — these differ from IPC-6012 rigid-board values.
- Plating voids: a void = plating < 80% of required thickness, max one void per panel, never at the hole-wall/internal-layer interface. **Class 3:** zero voids in the hole wall; **no voids at the knee (pad-to-hole-wall transition) for any class.** Class 2: up to 3 sidewall voids, total ≤ 5% of hole-wall surface. Class 1: up to 3 voids ≤ 10%.
- Teardrop pads at all via-to-trace junctions in/near flex — mandatory for Class 3.
- Pad size per IPC-2221 formula: finished hole dia. + 2× min annular ring + fabrication allowance.
- **Button (pad) plating vs. panel plating:** flex/rigid-flex commonly use button plating (copper deposited only at the barrels and surrounding pads, not the full surface) to preserve base-copper ductility in the flex. IPC-6013 thickness minimums then apply to the **hole wall and pad surfaces only** — reviewers from a rigid-board background may wrongly expect panel-plating uniformity across the flex. Confirm with the fabricator which method is used and how compliance is measured and qualified.

### N.6 Component Placement (IPC-2223E, IPC-7711/7721)

- No components in active bend zones (solder joints fail during flexing).
- Components requiring flex-zone placement mounted on stiffeners that extend beyond the component footprint.
- Components ≥ **0.025"** from the flex-to-rigid transition on the outer edge (rollover at the rigid edge damages parts placed too close).
- Heavy or tall components in rigid sections only (mass/height create lever-arm stress on solder joints during flex and handling).
- Epoxy underfill or staking on large SMT components near flex zones.
- FPC/ZIF connector insertion-force direction verified against flex-zone orientation.
- Test points and fiducials in rigid sections only (flex-zone fiducials shift position when the board deflects during optical inspection).

**Assembly process:**
- **Pre-bake polyimide before reflow** — polyimide absorbs up to **3% moisture by weight**, which causes delamination in reflow. Typical bake **100–120 °C for several hours immediately before reflow** (confirm exact protocol with fabricator/assembler).
- Panelization waste tabs connect rigid sections only (never flex sections — tabs on flex compromise bend geometry during handling).
- Specify assembly fixturing/support for SMT placement on flex-adjacent rigid sections (standard conveyors can't handle unrestrained flex).
- Verify 3D clearance in all intended folded/bent configurations.

### N.7 Rigid-to-Flex Transition Zone (IPC-2223E, IPC-6013E)

The transition zone is the highest-stress location in a rigid-flex PCB and the most common failure point. IPC-6013E added explicit transition-zone acceptance criteria, recognizing it as the most failure-prone area (imperfections that do not cause functional degradation are permitted within defined limits).

- Gradual taper/fillet at the boundary — no abrupt thickness changes.
- Coverlay extends past the rigid-to-flex boundary by the specified overlap (typically **0.5–1 mm**) to engage the rigid section for mechanical anchoring.
- Note the transition-zone inspection range on the drawing: **3.0 mm from the transition centerline**.
- Explicitly dimension the rigid-to-flex boundary on **all** fabrication drawings (the fabricator cannot assume transition locations).
- Use stress-relief slots or diamond cutouts where transition stress is elevated.
- Stagger flex-layer terminations (not all ending at the same location) to distribute stress across multiple planes; maintain a symmetrical stackup in the flex; avoid unbalanced copper in adjacent rigid sections (causes bowing/twisting during reflow).
- **Soda strawing** (a lifting/tenting of the coverlay film around a conductor, tube-like in appearance) is an accepted IPC-6013 workmanship condition that does **not** appear in IPC-6012, provided the conductor is not exposed and the coverlay stays adhered at the pad openings. Inspectors from a rigid-board background may wrongly flag it — confirm before first article that acceptance is judged against IPC-6013 / IPC-A-600, not IPC-6012.

### N.8 Mechanical Analysis and Testing (IPC-TM-650)

FEA is **not** universally required by IPC. For static fold-once designs, manual bend-radius calculation per IPC-2223E is typically sufficient. For **dynamic applications exceeding 1,000 cycles, FEA should be treated as mandatory** before routing begins.

**Pre-layout simulation:**
- Target bending strain **< 0.3%** across the flex region for dynamic applications. This is an industry best-practice *design target*, **not** an IPC limit — it is the threshold below which RA-copper conductor fatigue life is generally acceptable; designs exceeding it should be reassessed.
- FEA model with correct material properties: polyimide tensile strength ≈ **231 MPa**, RA copper, adhesive layers. If simulation approaches the polyimide tensile limit, increase bend radius or change material.
- Analyze both concave and convex bending orientations.
- Solder-joint strain below the fatigue threshold for parts adjacent to flex (target **< 500 µε** for QFP-class parts with an FR-4 stiffener, IPC-9704).
- Verify rounded trace corners (min **0.1 mm** radius) in the flex zone — they reduce peak stress by ≈ 40% and significantly extend fatigue life.

**Vibration & thermal:**
- Modal analysis for vibration-exposed designs (rigid-flex hinge regions exhibit different modal behavior than solid boards).
- Fully define the dynamic bending environment: cycles, bend angle, frequency, operating temperature range (all four are required for bend-life prediction).
- Thermal-cycling stress analysis for wide-temperature designs (CTE mismatch between polyimide, FR-4, and copper drives cyclic stress at the transition).

**Physical & environmental tests (key IPC-TM-650 methods):**
- **2.4.3** flexural endurance (dynamic) — failure criterion **10% increase in trace resistance**; bend conditions must represent worst-case in-service use.
- **2.4.8** peel strength — coverlay adhesion meets minimum.
- **2.6.7.2** thermal shock — **−65 °C / +150 °C for 100 cycles**, no delamination or solder-joint failure.
- **2.6.27** thermal stress / reflow simulation — **min 6 reflow cycles at 260 °C** peak, failure = **5% resistance change** (detects latent microvia / via-barrel failures; note the 5% criterion here vs. 10% for flex endurance).

### N.9 Electrical Analysis and Testing (IPC-TM-650, IPC-9257)

**Pre-layout signal integrity:**
- Impedance simulation using flex-zone material properties (polyimide Dk ≈ 3.4, **not** FR-4) — flex and rigid zones simulated separately.
- Model insertion/return loss for high-speed differential pairs crossing the flex zone (Method 2.5.5.12A; standard rigid SI simulation won't capture the flex-zone transitions).
- Crosstalk analysis where high-speed signals run parallel through flex (reduced ground coverage from crosshatch increases coupling; no dedicated IPC-TM-650 crosstalk method exists — verify against the system SI budget).
- Length-match differential pairs across the rigid-to-flex boundary, accounting for the Dk difference across the transition.

**Power delivery network (PDN):**
- Verify current capacity of all power/ground conductors in flex zones per IPC-2221.
- Voltage-drop analysis for power traces routed through flex (thin flex conductors have higher resistance per unit length than rigid traces).

**Post-fabrication tests:**
- TDR impedance (**2.5.5.7**) for all impedance-controlled designs — confirms continuity across the transition.
- Continuity test for all nets (flying probe or fixture) — detects opens, trace breaks, plating problems.
- Insulation resistance (**2.5.1**) — min **10 MΩ** between adjacent isolated nets.
- Dielectric withstand / HiPot (**2.5.7.2**) — confirms insulation strength of the thin flex dielectrics.
- Moisture & insulation resistance (**2.6.3**) for high-humidity / outdoor / industrial use.
- Post-bend-cycle continuity — verify all nets before and after the specified bend count (10% resistance increase = failure per 2.4.3).

### N.10 Fabrication Documentation and DFM (IPC-2223E, IPC-6013, IPC-A-600)

Every critical rigid-flex parameter must be stated explicitly — ambiguity scraps panels and produces non-conforming deliveries.

- Bend-zone location and bend radius dimensioned on the drawing.
- Flex section labeled **static or dynamic** (drives material, copper type, and bend-radius requirements).
- **Separate** fab notes for rigid vs. flex sections (combined notes create ambiguity).
- Stackup diagram showing all layers with material callouts (flex PI, rigid FR-4, adhesive, prepreg) and layer boundaries.
- Impedance details: layer, trace width, target impedance, tolerance (reference the specific flex-zone layer/dielectric stack).
- Stiffener locations, materials, thicknesses (all explicit — cannot be inferred).
- Coverlay type, thickness, overlap distance (distinguish polyimide coverlay from flexible LPI).
- **IPC-6013 Class** (2 or 3) declared — cannot be retroactively upgraded after fabrication.
- **IPC-6013 Type** declared *alongside* Class — Type 1 (single-sided flex, no PTH), Type 2 (double-sided flex with PTH), Type 3 (multilayer flex, no rigid), **Type 4 (multilayer rigid-flex with PTH — most rigid-flex designs)**, Type 5 (multilayer rigid-flex, specific construction). Type determines which fabrication/acceptance requirements apply; declaring Class without Type is incomplete.
- Layer map identifying rigid vs. flex layers by Gerber layer number (required beyond standard Gerbers).
- Outline drawing marking bend zones, transition zones, and stiffener locations (the primary mechanical reference for fabrication/inspection).
- Test requirements documented: impedance coupons, bend-cycle test, **IST** (required for Class 3 qualification).
- Visual inspection criteria: IPC-A-600 class + IPC-6013 revision (used jointly).
- **Fabricator engagement:** review the stackup with the fab **before** routing begins; complete a DFM review before final file release (it catches manufacturability issues DRC does not); confirm fabricator capabilities — impedance Cpk, microvia capability, registration accuracy.

### N.11 Industry-Specific Requirements

These deltas cover only what *changes* because of the end-use industry; they do not repeat the core checks in N.2–N.10.

**N.11.1 Military & Defense** — Governing: MIL-PRF-50884 (legacy flex/rigid-flex spec, still governs many active programs), MIL-PRF-31032 (all PCBs, required for new programs; mandates a DLA-qualified facility on the QPL/QML), MIL-STD-810 (environmental), MIL-STD-461 (EMC), MIL-HDBK-454.
- MIL-PRF-31032 demands a **larger minimum annular ring** than IPC-6013 Class 3 in some via/layer configurations, **stricter surface-imperfection criteria** (measling, crazing, foreign material — stricter than IPC-A-600 Class 3), stricter solder-coating thickness, and more explicit plating-void thresholds.
- IPC-6013 Class 3 is a **prerequisite** for both MIL specs; it does not replace either. MIL-PRF-31032 supersedes MIL-PRF-50884 for new starts but cannot be interchanged on existing programs without program-office approval.
- **Resolve the governing-document hierarchy before inspection.** Applying IPC-6013E transition-zone criteria to a MIL-PRF-31032 program (which lacks mirrored criteria) can cause either unwarranted rejections (where IPC-6013E is more permissive) or non-conforming acceptance (where MIL-PRF-31032 is stricter). Confirm with the program quality engineer.
- Environmental qualification must include the **transition zone** in test coupons: MIL-STD-810 Method 514 (vibration), 516 (shock), 503 (thermal cycling, −55/+125 °C with continuity monitoring), 507 (humidity).
- EMC: verify ground-plane continuity across the transition for MIL-STD-461; a dedicated shield layer / conductive coverlay in the flex may be needed where standard crosshatch can't meet radiated limits.

**N.11.2 Aerospace & Space** — Governing: adds outgassing, radiation, and space-qualification constraints beyond IPC-6013 Class 3 (IPC-6012ES, ASTM E595, NASA-STD-8739.4A, GSFC-STD-7000 GEVS, J-STD-001FS).
- **FR-4 is prohibited for space flex** — polyimide required (FR-4 lacks the thermal stability and radiation tolerance). Rigid sections may still use high-Tg FR-4 for LEO/commercial launches (confirm via mission thermal analysis).
- **Outgassing:** all flex-zone materials (coverlay, stiffener and flex-core adhesives, conformal coating) confirmed against ASTM E595 / NASA GSFC outgassing database — **TML < 1.0%**, **CVCM < 0.1%**. Polyimide base typically passes; acrylic coverlay/stiffener adhesives may not meet CVCM limits — verify the material lot before specifying.
- **Thermal vacuum (TVAC)** cycling with electrical continuity monitoring across the transition; thermal-cycle profile **−40/+80 °C (LEO)** or **−55/+125 °C (GEO)** taken from the mission thermal model, not assumed.
- Random-vibration (GEVS / GSFC-STD-7000) and pyrotechnic-shock survival verified with the board in the **deployed (bent)** configuration; flexural-endurance coupons must include the transition zone (flex-only coupons miss the highest-stress region).
- Space soldering per **J-STD-001FS** (zero-defect for bridges/cold joints near the transition); conformal coating selectively masked so it doesn't bridge/rigidize a dynamic flex; moisture bake-out immediately before integration; **IPC-6012ES** aerospace amendment applied on top of IPC-6013 Class 3 (stricter conductor and via-quality limits — specified in addition to, not instead of, Class 3).

**N.11.3 Medical Devices** — Governing: adds biocompatibility, electrical-safety, and sterilization constraints (IPC-6012EM, IEC 60601-1 / -1-2, ISO 10993, ISO 14971, ISO 11135/11137).
- **Biocompatibility (ISO 10993):** standard industrial polyimide is **not** automatically ISO 10993 approved — confirm per ISO 10993-5 (cytotoxicity) for body-contact/implantable designs; coverlay adhesive per ISO 10993-10 (sensitization); include stiffener adhesives in the assessment (commonly overlooked).
- **Creepage/clearance (IEC 60601-1):** distances are based on working voltage, pollution degree, and material **CTI**, and are typically larger than IPC-2221 minimums — add them as DRC constraints **before** flex-zone routing. Route Functional/Protective Earth through rigid sections where possible to avoid leakage-current paths through the flex; account for the dielectric change at the transition in leakage analysis.
- **Sterilization:** choose the surface finish for the intended method — ENIG/ENEPIG are generally sterilization-compatible; OSP can degrade under gamma/EtO. **Parylene C** is the standard biocompatible, pinhole-free, sterilization-resistant coating for implantable / surgically-adjacent flex sections.
- **IPC-6012EM** medical amendment applied on top of IPC-6013 Class 3 for life-critical PCBs (does not replace Class 3); **IEC 60601-1-2** EMC — crosshatch reduces shielding effectiveness vs. a solid plane, so verify immunity/emissions and transition-zone ground continuity; a thin shield layer in the flex may be needed for high-frequency sections. Confirm device classification (Class I/II/III) before fixing the fabrication standard.

**N.11.4 Automotive & Functional Safety** — Governing: AEC-Q200 (passives), ISO 16750-3/4 (mechanical/climatic loads), ISO 26262 (functional safety), IPC-CC-830 (conformal coating).
- **Temperature range:** RA copper for all flex subject to the automotive thermal-cycling range (**−40/+125 °C**, AEC-Q200 Grade 2; **Grade 0 −40/+150 °C** for under-hood/powertrain). High-Tg FR-4 or polyimide rigid for continuous +150 °C; adhesiveless flex core for engine-compartment/powertrain (thermal stability, not just dynamic flex); coverlay rated for the operating environment (standard acrylic-adhesive coverlay ≈ +105/+130 °C continuous — under-hood may need a higher-temperature adhesive).
- ISO 16750-3 vibration (vehicle body 20–2000 Hz / powertrain 10–2000 Hz) and mechanical-shock survival; ISO 16750-4 thermal cycling and humidity/condensation — all with continuity monitoring at the flex and test coupons that include the transition zone.
- Where the board both flexes *and* thermal-cycles (e.g., articulating camera mounts, door assemblies), calculate flex-conductor fatigue life under the **combined** loading, not each load independently.
- **ISO 26262:** confirm the **ASIL** level before design; place test points for ASIL diagnostic circuits in **rigid sections only**; route BIST signals to test points in rigid sections; perform single-point-fault analysis treating a flex-conductor open/short at the transition as a potential ASIL-relevant failure mode — mitigate by redundant routing or declare it tolerable within the ASIL budget, and capture it in the FMEDA.
- Conformal coating selectively masked so it doesn't bridge a dynamic flex section (a coating bridge fails by cracking and creates a contamination path), while still fully covering the transition-zone edge.

### N.12 Glossary of Key Rigid-Flex Terms

Brief definitions a reviewer needs; the primary governing standard is cited for each.

- **Bend radius** — radius of curvature at the innermost flex surface when bent; expressed as a multiple of total flex thickness (static 6×/12×, dynamic 100×/150×/200×). The most fundamental design parameter; calculate before routing. (IPC-2223E §4)
- **Bend ratio (r/h)** — minimum bend radius ÷ total flex thickness; quantifies bend severity and indexes IPC material/construction tables. (IPC-2223E)
- **Bend zone** — region designed to flex; governed by via prohibition, trace orientation, copper-pour prohibition, and neutral-axis rules; the highest-stress region. (IPC-2223E)
- **Neutral axis** — the plane through a bent laminate with no tensile/compressive strain; center flex layers and place small conductors here to minimize strain. (IPC-2223E §4)
- **Adhesiveless flex core** — copper bonded directly to polyimide with no intermediate adhesive; far lower CTE mismatch; mandatory for dynamic flex. (IPC-2223E)
- **RA (rolled-annealed) copper** — mechanically rolled then annealed; fine directional grain giving high ductility/fatigue resistance; mandatory for dynamic flex. (IPC-2223E)
- **ED (electrodeposited) copper** — plated copper, columnar grain, more brittle; rigid sections only, never dynamic flex. (IPC-2223E)
- **Coverlay** — polyimide film + adhesive laminated over flex conductors in place of solder mask; overlaps the rigid ≈0.64 mm; LPI solder mask is not acceptable in flex. (IPC-4203/1, IPC-2223E, IPC-6013)
- **Crosshatch copper** — grid/mesh ground or power plane in the flex zone that preserves flexibility while maintaining continuity; solid pours are prohibited in flex (they act as structural elements). (IPC-2223E)
- **No-flow / low-flow prepreg** — partially-cured bonding sheet that limits resin flow; mandatory at the rigid-to-flex boundary to keep resin out of the flex zone. (IPC-2223E)
- **Bookbinder construction** — multilayer flex with unbonded layers free to slide through the bend; required for tight radii with 3+ flex layers (bonded layers force all layers to one radius, overstraining the outer ones). (IPC-2223E)
- **Dynamic vs. static flex** — *dynamic* flexes repeatedly in operation (highest requirements: adhesiveless core, RA copper, 100–200× radius, flexural-endurance test); *static* folds once at assembly and stays fixed (6×/12× radius). Declare the type on the drawing. (IPC-2223E)
- **Rigid-to-flex transition zone** — boundary where the rigid structure ends and the flex begins; highest-stress location; needs gradual taper, coverlay overlap, staggered terminations, 3.0 mm inspection zone. (IPC-2223E, IPC-6013E)
- **Transition line** — the dimensioned boundary line on the drawing; defines the via-keepout zone (min 0.050"/1.27 mm), coverlay-overlap extent, and the inspection region. (IPC-2223E)
- **Via keepout zone** — area around the transition line where PTH/vias are prohibited; min 0.050" (1.27 mm), 0.100" (2.54 mm) recommended. (IPC-2223E)
- **Stiffener** — rigid backing bonded to the flex for component/connector support; FR-4 (components) or polyimide (ZIF/thin sections); must not enter the bend zone; overlaps coverlay ≥0.76 mm; rounded corners; sized beyond the component footprint. (IPC-2223E)
- **Teardrop pad** — tapered fillet blending trace into pad; reduces stress at the via-to-trace junction; mandatory at flex via-to-trace junctions for Class 3. (IPC-6013, IPC-2223E)
- **ZIF connector (zero insertion force)** — accepts a flex tail with no insertion force; requires a polyimide stiffener (not FR-4) sized to the connector's specified tail thickness. (IPC-2223E)
- **Soda strawing** — tube-like lifting of coverlay around a conductor; an accepted IPC-6013 workmanship condition (absent from IPC-6012); confirm acceptance against IPC-6013/IPC-A-600. (IPC-6013, IPC-A-600)
- **Measling / crazing** — measling = discrete white spots from glass-bundle separation; crazing = connected microcracks in the glass reinforcement; MIL-PRF-31032 rejection criteria are stricter than IPC-A-600 Class 3. (IPC-A-600, MIL-PRF-31032)
- **Knee (via)** — the pad-to-hole-wall transition; the most mechanically stressed point in a PTH and a zero-void zone for all classes; rigid-flex via failures often initiate here, especially near the transition. (IPC-6013)
- **Void (plating)** — hole-wall plating absent or below 80% of required thickness; Class 3 = zero voids in the hole wall; no voids at the knee for any class. (IPC-6013)
- **Flexural endurance** — number of bend cycles a flex conductor survives before a 10% resistance increase; tested per IPC-TM-650 Method 2.4.3 with bend angle/frequency/temperature matched to service. (IPC-TM-650 2.4.3)
- **CTE (coefficient of thermal expansion)** — expansion rate per °C; CTE mismatch between polyimide flex and FR-4 rigid drives stress at the transition under thermal cycling. (IPC-2223E, IPC-6013)
- **Dk (dielectric constant)** — polyimide ≈3.4 vs. FR-4 ≈4.2–4.5; flex traces must be wider than equivalent rigid traces for the same impedance; using FR-4 Dk for flex yields out-of-tolerance designs. (IPC-2223E)
- **Polyimide** — base flex dielectric: Dk ≈3.4, tensile ≈231 MPa, low CTE, up to 3% moisture absorption (pre-bake before reflow); mandatory for space flex. (IPC-2223E, IPC-4203/1)
- **LPI solder mask** — liquid photoimageable mask; standard for rigid, not acceptable in flex (lacks the elongation-at-break to survive bending). (IPC-4203/1, IPC-6013)
- **FPC (flexible printed circuit)** — all-flex circuit with no rigid sections; the flex-section design rules of a rigid-flex board derive from FPC practice; "FPC/ZIF connector" is the mating connector for a flex tail. (IPC-2223E)

> **Note on informal terminology.** "Flex zone stiffening / rigidizing," "bookbinder construction," and "transition zone" are widely used in fabricator application notes but are not all formally defined in the current IPC-2223E revision. Where this glossary uses an informal term, the closest governing clause is cited; do not rely on informal terms in fabrication drawings or quality documentation where a formally defined IPC term or parameter exists.

### N.13 Governing Standards Quick Reference

- **IPC-2223E** — sectional design standard for flex/rigid-flex (primary design authority).
- **IPC-6013 / IPC-6013E** — qualification & acceptance for flex/rigid-flex (Classes 1/2/3; E adds transition-zone criteria). Declare **Class and Type** on the drawing.
- **IPC-2221** — generic PCB design: conductor sizing, annular-ring formula, clearances.
- **IPC-4203/1** — coverlay / bonding materials for flex.
- **IPC-4101** — base-material (laminate/prepreg) specification.
- **IPC-A-600** — visual acceptance (used jointly with IPC-6013).
- **IPC-7711/7721** — rework / repair.
- **IPC-TM-650** test methods — 2.4.3 (flex endurance, 10% R fail), 2.4.8 (peel), 2.5.1 (insulation R), 2.5.5.7 (TDR), 2.5.5.12A (signal loss), 2.5.7.2 (HiPot), 2.6.3 (moisture), 2.6.7.2 (thermal shock), 2.6.27 (thermal stress/reflow, 5% R fail).
- **Industry:** MIL-PRF-50884 / MIL-PRF-31032, MIL-STD-810 / 461 (military); IPC-6012ES, ASTM E595, NASA-STD-8739.4A, GSFC-STD-7000, J-STD-001FS (aerospace/space); IPC-6012EM, IEC 60601-1 / -1-2, ISO 10993, ISO 11135/11137 (medical); AEC-Q200, ISO 16750-3/4, ISO 26262, IPC-CC-830 (automotive).
