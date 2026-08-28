# Direct MCP Reads vs. Export ULPs — Feasibility Investigation

**Date:** 2026-08-28
**Branch:** `feature/direct-UlP`
**Verified against:** live Fusion Electronics session, design `series-shunt`
(1 sheet, 74 components placed, unrouted), Fusion MCP Server over the
`tools/fusion_bridge.py` transport and the registered `fusion` MCP tools.
**Independently re-verified** the same day by a fresh agent, which confirmed
the conclusion and corrected several claims (the `objectId` quirk's scope,
the `Layer.used` failure mode, "verified" labels that rested on empty reads)
and surfaced gaps 5–7 below. Entities the unrouted test design had zero rows
for — `PolyPour`, `Via`, `Hole`, signal-parented `Wire` — remain
**schema-verified only** until the comet parity diff.

## Verdict

**Yes — all four ULPs are replaceable.**

The two JSON exporters (`fusion-electronics-export.ulp` both modes,
`fusion-electronics-stackup.ulp`) map to direct
`fusion_mcp_electronics_read` queries: everything they write is either
directly readable as an entity field or derivable client-side from raw
entity rows with the same arithmetic the ULP already performs. The gaps
found are small and enumerated below; two genuinely lose data the ULP
exports today (net-class clearance, the active assembly variant), the rest
have workarounds.

**`fusion-electronics-images.ulp` is replaceable too — not by reads, but by
dispatching its EAGLE command stream directly** (the pattern proven in
`~/steinmetz/src/screenshot.py`). The ULP's only irreplaceable-looking part
was `EXPORT IMAGE`, but that is itself just an EAGLE command; the ULP merely
computes which sheets/layers to iterate — which the reads above already
provide. Verified live today in one chained dispatch:

```
EDIT .brd; RATSNEST; DISPLAY NONE 20 17 18 19 21 22 39 40 41 42 1;
WINDOW FIT; EXPORT IMAGE 'C:/tmp/thomsonlint_cu_L1_test.png' 300;
DISPLAY ALL; EDIT .sch;
```

— produced a correct top-copper review PNG (copper+pads, THT pads, airwires,
outline, placement context; 2270×1420 px at 300 DPI ≈ the 192×120 mm board —
the outline wires read exactly 0,0→192,0→192,120→0,120, and the render adds
a small WINDOW FIT margin), and the execute channel was **not latched
afterward**. A schematic
`WINDOW FIT; EXPORT IMAGE` pair worked identically. There is still no render
*endpoint* (screenshot query returns "No active graphics view" for the 2D
editors) — the PNGs land on the Fusion host's filesystem and are read back
via `/mnt/c`, same as the ULP path.

The headline operational win: **the capture becomes a zero-ULP,
zero-staging, and (for single-sheet designs) zero-Escape workflow.** Reads
are never latch-blocked, and the dialog-latch rule was isolated live with an
A/B test (2026-08-28): a **real** editor/sheet switch (`EDIT .brd;`,
`EDIT .S1;` from the board), `RATSNEST`, `DISPLAY`, `WINDOW FIT`, and
`EXPORT IMAGE` dispatches do **not** latch the execute channel — but a
**no-op `EDIT`** (opening the sheet that is already open) reliably does.
That is why chains starting `EDIT .S1;` on an already-active sheet 1
latched, and it likely explains steinmetz's "invisible block after a fully
successful batch". `tools/fusion_export.py` avoids no-op EDITs (no `EDIT`
for 1-sheet designs; sheet 1 captured last on multi-sheet), and its
`wait_channel()` detects a latch before each dispatch, prompts for one
Escape, and continues — the failure mode is a pause, not a broken capture.
The guaranteed post-`RUN` latch disappears with the `RUN`s themselves, and
`stage-ulps` is no longer needed at all.

## Field-by-field mapping

### Schematic export (`-thomson-export-sch.json`)

| ULP output | MCP source | Status |
|---|---|---|
| `project.name` | `electronics.Schematic.name` (temp path; strip like `FusionBridge.design_name()`) | verified |
| `project.variant` | `electronics.Variant` / `electronics.VariantDef` — but the *active* variant is not identifiable (gap 5) | partial |
| `project.sheets` | `electronics.Sheet` row count | verified |
| `components[].ref`, `.value` | `electronics.Part.name`, `.value` | verified |
| `components[].package` | `Part.device_object_id` → `Device.package_object_id` → `Package.name` | verified |
| `components[].device` | `Part.deviceset_object_id` → `DeviceSet.name` (+ `Device.name` variant suffix) | verified |
| `components[].description` | `DeviceSet.headline` / `Device.headline` | verified |
| `components[].populate` | **gap** — `Part` has no `populate`; board-side `Element.populate` has it, and the DNP/DNI/`value` heuristics come from `electronics.Attribute` | workaround |
| `components[].type` | derived (`ClassifyComponent` port) | client-side |
| `components[].attributes` | `electronics.Attribute` (parent object ids) | entity exists; design had none |
| `nets[].name` | `electronics.Net.name` | verified |
| `nets[].class` | `Net.net_class_number` → `electronics.NetClass` (`name`, `width`, `drill`) | **`clearance` missing** — see gaps |
| `nets[].pins[]` (part/pin/direction) | `electronics.PinRef` → `Part.name` + `Pin.name`/`Pin.direction`; `Pin.net` is a direct shortcut | verified |
| pin direction strings | `Pin.direction` enum, documented in the schema resource: 0=nc 1=in 2=out 3=io 4=oc 5=pwr 6=pas 7=hiz 8=sup | verified |
| `analysis.*` (power/ground/clock/diff classification, voltage guess, floating inputs, single-pin nets) | pure name/direction heuristics — port the ULP logic to Python over the raw rows | client-side |

### Board export (`-thomson-export-brd.json`)

| ULP output | MCP source | Status |
|---|---|---|
| `components[]` placement (`x/y/rotation/side`) | `electronics.Element` (`x`, `y`, `angle`, `mirror`, plus `populate`, `locked`) | verified |
| `components[].pads[]` (absolute) | `electronics.Smd` + `electronics.Pad` — **global board coords** with resolved `signal` name; element attribution via `ContactRef` join for connected pads, `Contact`+`Element` transform for unconnected ones (gap 6) | verified for connected pads (better than ULP there: signal + drill + geometry per pad) |
| `board.area` | **gap** — `electronics.Board` has no bbox; derive from layer-20 (`BoardOutline`) `Wire` rows with `board_object_id` set | verified (outline wires read 0,0→192,0→192,120…) |
| `board.layers_used`, `layer_count` | `electronics.Layer` — but `used` is unreliable as a content indicator (see gap 4); derive copper usage from signal-parented `Wire`/`Smd`/`PolyPour` presence per layer (the images ULP's pre-scan workaround) | workaround |
| `board.holes` | `electronics.Hole` (`x`, `y`, `drill`) | schema verified; design had none |
| `board.polygons` | `electronics.PolyPour` (`layer`, `isolate`, `rank`, `thermals` + `hatched`, `orphans`, `thermal_width`) via `signal_object_id` → `Signal.name` | schema verified; design had none — needs a poured design (comet) for parity |
| `signals[]` name/classification | `electronics.Signal.name` + client-side heuristics | verified |
| `signals[]` trace aggregates (`trace_length_mm`, min/max width, `segment_count`) | derive from `electronics.Wire` rows (`signal_object_id`, `layer`, `width`, endpoints) — same arithmetic the ULP runs | client-side |
| `signals[].trace_segments[]` | the same `Wire` rows, verbatim | schema-verified (test board unrouted — zero signal-parented copper wires; comet parity diff must exercise this) |
| `signals[].via_count` | `electronics.Via` — richer than the ULP (drill, diameter, layer span, tenting flags) | schema verified; design unrouted |
| `analysis.component_edge_distances` | derive: `Element` positions vs. outline bbox | client-side |
| `analysis.decoupling_proximity` | derive: `ContactRef` ⋈ `Smd`/`Pad` (global coords) ⋈ `Signal` ⋈ `Element` | client-side |
| `analysis.ground_plane_layers` | `PolyPour` ⋈ `Signal.name` | client-side |

### Stackup export (`-thomson-export-stack.json`)

| ULP output | MCP source | Status |
|---|---|---|
| `all_layers[]` | `electronics.Layer` (`number`, `name`, `used`, `visible`) + the `IsCopperLayer` port | verified (with the `used` caveat above) |
| `copper_stack[]` physical order | same `CopperRank` logic, client-side | port |
| `board_description` | `electronics.Board.description` | field verified (empty on test design) |
| per-layer thickness / material | not exposed — **same gap the ULP has** (.dru not reachable); no regression | parity |

## Gaps

1. **`NetClass.clearance` is not exposed** (only `name`, `number`, `width`,
   `drill`). The ULP exports `clearance_mm` per net class. Losing it means the
   `-sch.json` `class.clearance_mm` field would be null/absent. Candidate
   sources: none found in the MCP surface. Flag to Autodesk; emit `null`
   meanwhile.
2. **Schematic-side `populate`** — `Part` has no populate flag. Derive from
   `Element.populate` (board side), `Attribute` DNI/DNP rows, and the ULP's
   value-prefix heuristics. Matches the ULP's effective behavior for designs
   without assembly variants.
3. **Board bbox** must be computed from outline wires instead of `B.area`.
   Slightly different semantics (true outline extent vs. drawing extent) —
   arguably more correct.
4. **`Layer.used` is unreliable as a content indicator — in both
   directions.** It is *not* all-1s (Route2..Route63 read `used:0` on the
   test board), but it over-reports (Bottom reads 1 on an unrouted board;
   surely-empty user layers like fp8/HeatSink read 1) and — per the images
   ULP's own documented failure mode — under-reports pour-only inner layers
   (`used==0`). Derive copper usage from object presence per layer, and
   **filter the presence scan to signal-parented objects**
   (`signal_object_id != 0`): package pad geometry appears as copper-layer
   `Wire` rows with `signal_object_id:0` and would false-positive a naive
   scan. The ULP's prescan iterates `B.signals(S)` wires only — match that.
5. **The active assembly variant is not readable.** The ULP writes
   `project.variant` from `variant()` — the *currently active* variant.
   `VariantDef` has no active/current flag and `Variant` is per-part, so on a
   design that defines variants the direct path cannot reproduce this field.
   Emit the `VariantDef` list and `null` for the active one; flag to
   Autodesk.
6. **Unconnected pads lose element attribution via the join path.**
   `Smd`/`Pad` rows carry no element id; attribution runs through
   `ContactRef`, which exists only for *connected* pads. An unconnected
   pad must be attributed by transforming `Contact` (package-local x/y)
   through `Element` placement client-side. The ULP's
   `E.package.contacts` covers all pads unconditionally.
7. **`electronics.Error.type` enum drift.** The schema resource documents
   3=airwire, but live airwire rows read `type:4` (description "Air Wire",
   layer 19). Classify by `description`/`layer`, not by the schema's enum.

## Advantages over the ULP path

- **The dialog latch is understood and mostly gone.** Reads never latch.
  Real editor/sheet switches, `RATSNEST`, `DISPLAY`, `WINDOW FIT`, and
  `EXPORT IMAGE` dispatches are latch-free; only a **no-op `EDIT`** arms
  the latch (verified by A/B isolation). The exporter avoids no-op EDITs
  and rides out any residual latch with a prompt-and-wait.
- **UTF-8 end to end.** Python writes the JSON, retiring the Latin-1 ULP
  output wart (the `gesam-Maß` decode workaround).
- **Richer data:** per-pad signal + drill + geometry, via drill/span/tenting,
  pour hatch/orphan settings, `Element.locked`.
- **`electronics.Error`** exposes the live DRC/ERC table (including airwires
  with coordinates — verified live) — a new evidence category the ULP path
  never had; the roadmap already earmarks it for findings evidence (§7 v1.5).
- No staging of ULPs to a Windows-visible share at all — `stage-ulps`
  retires with the ULPs. Images land on the Fusion host (`C:/...`) and are
  read back over `/mnt/c`, same as before.

## Transport facts confirmed today

- Rows are paginated: 100/page default, 1000 max — always auto-paginate
  (`FusionBridge.read_all` / steinmetz `electronics_read` both do).
- Every response carries `coordinate_unit` (mm here). Units follow the
  document grid unit — check it per capture rather than assuming mm.
- `electronics.Schematic` — alone — uses camelCase `objectId`; every other
  entity, `electronics.Board` included, uses snake_case `object_id`. Field
  selection must match (`{"fields": ["object_id"]}` errors on Schematic;
  `{"fields": ["objectId"]}` errors on Board).
- Reads follow the active editor (unchanged doctrine). A pre-latched execute
  channel blocks *dispatches* (even `readOnly: true` ones, contra the tool's
  own docs — matches `~/steinmetz/docs/fusion-mcp-blocking-dialog-bug-report.md`);
  reads keep working. If a dispatch fails with the dialog-open error, ask for
  one Escape, then proceed.

## Image pass without the ULP

Port `fusion-electronics-images.ulp`'s command generation to the bridge:

- **Schematic:** `electronics.Sheet` count → per sheet
  `EDIT .S<n>; WINDOW FIT; EXPORT IMAGE '<prefix>-img-sch-p<n>.png' 300;`.
- **Board:** `RATSNEST;` once (pours render filled), then the silk-top,
  silk-bottom, and per-copper-layer `DISPLAY NONE <set>; WINDOW FIT;
  EXPORT IMAGE ... 1200;` sequences, ending `DISPLAY ALL;`. The copper-layer
  list comes from the `Layer` read plus the object-presence scan (the ULP's
  own poly-only inner-layer workaround, already needed for stackup).
- **Pre-delete each target PNG** on the WSL side before dispatching
  (steinmetz's pattern) so the overwrite prompt can never fire; the bridge's
  `SET CONFIRM YES;` prefix is belt-and-suspenders.
- Caveats carried over unchanged: 1200 DPI board PNGs can exceed 150 MB;
  a failing command mid-chain (e.g. bad export path) can raise a modal and
  corrupt the rest of the chain (steinmetz bug report incident 4) — validate
  paths first and verify each PNG landed afterward.

## Implementation and first parity results (2026-08-28)

`tools/fusion_export.py` implements the direct capture (verbs `sch`, `brd`,
`images`, `all`). The same design (`series-shunt`) had been captured by the
ULP path the same morning, giving a real acceptance diff:

- **Schematic: parity is exact** except the two documented deltas —
  `clearance_mm` `0.0` (ULP) vs `null` (gap 1), and `export_date`. All 55
  components byte-equal (device/package/description/populate/type/
  attributes), all six analysis arrays identical.
- **Board: parity is exact** on all 55 placements, **every pad coordinate**
  (validating the mirror-then-rotate transform), area, `layer_count`,
  all signal aggregates, and all three analysis arrays. One cosmetic delta:
  `layers_used` has 96 rows vs the ULP's 16 — the MCP `used` flag
  over-reports relative to the UL API's.
- **Stackup: the direct output is *more correct* than the ULP's.** The ULP
  emitted `copper_stack: [Top, Unrouted(19)]` for this design — its name
  fallback classifies layer 19 "Unrouted" as copper ("ROUTE" substring) and
  it missed the real Bottom (304). The exporter excludes system layers
  17-52 from copper detection and produced `[Top, Bottom]`.
- **Images:** per-sheet + silk top/bottom + per-copper-layer PNGs produced
  by dispatch chains; all checksums distinct; board renders byte-identical
  in *size* (known fixed-canvas trait, unchanged).
- New parity facts learned: EAGLE's `N.pinrefs` **excludes supply-symbol
  pins** (GND stamps, +3V…) — the MCP `PinRef` table includes them, so the
  exporter filters pinrefs of package-less parts to match the contract.

## Comet acceptance test — PASSED (2026-08-28)

The roadmap §7 acceptance test ran against the committed 2026-07-11 ULP
exports with comet live in Fusion. Every diff is accounted for; none is an
exporter defect:

- **Schematic:** exact parity. Only diff: D1 changed SMF5.0A → SMF7.0A
  (value + MPN/LCSC attributes) — genuine design drift since July.
- **Board:** all 33 components and **every pad coordinate** exact (round
  board, so the transform saw arbitrary angles). `holes` exact after
  filtering to board-parented rows (the MCP read also returns
  footprint-definition holes in package space — the ULP's `B.holes()`
  never sees those). Decoupling proximity and ground-plane arrays exact.
- **The ULP was blind to Fusion inner copper 303, numerically:** 9V0 routes
  12 segments on L1 + **8 on L303** (16.71 + 23.93 = 40.64 mm; the ULP
  reported 16.71), N$2 likewise (+3 segments, +6.91 mm), and the 5V0 pour
  on 303 was absent from the ULP's `polygons`. The direct path counts all
  of it. `layer_count` 4 vs the ULP's 3, same cause.
- **`board.area` semantics:** comet's outline is a layer-20 **Circle**
  (r = 14.8 mm — round board), now included in the outline bbox
  (29.6×29.6). The ULP's `B.area` was the drawing extent (35.6×41.3,
  silk/docu overhang) — against which its `component_edge_distances`
  check was effectively broken: it reported **zero** parts near the edge,
  while the true outline puts three parts within 3 mm.
- **Stackup:** `copper_stack` byte-equal (Top/GND/POWER/Bottom, 4/4).
- **Images:** inventory equals the committed set minus the ULP's bogus
  `L19-Unrouted` render; every byte-size matches the committed
  counterpart (fixed-canvas trait); the L303 render visually shows the
  9V0 inner-layer routing. **Zero Escape presses for the whole capture.**

## Recommended next step

Parity holds — retire the ULP path from Step 0: rewrite
`docs/REVIEWER_INSTRUCTIONS.md` "Step 0 — Live Fusion Capture" around
`tools/fusion_export.py all` (no staging, no `RUN` dispatches, no Escape
choreography for 1-sheet designs), keep the ULPs in `tools/` for the
manual-EAGLE-prompt fallback, and note the intentional deltas above
(outline-based area, layer-303 coverage, `clearance_mm` null) wherever the
old outputs are described.
