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
- **Shielding & Stitching:** Use ground pours on outer layers and and "stitch" them frequently to the main ground plane with vias, especially along board edges.

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