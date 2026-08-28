# Direct MCP Reads vs. Export ULPs — Feasibility Investigation

**Date:** 2026-08-28
**Branch:** `feature/direct-UlP`
**Verified against:** live Fusion Electronics session, design `series-shunt`
(1 sheet, 74 components placed, unrouted), Fusion MCP Server over the
`tools/fusion_bridge.py` transport and the registered `fusion` MCP tools.

## Verdict

**Yes — all four ULPs are replaceable.**

The two JSON exporters (`fusion-electronics-export.ulp` both modes,
`fusion-electronics-stackup.ulp`) map to direct
`fusion_mcp_electronics_read` queries: everything they write is either
directly readable as an entity field or derivable client-side from raw
entity rows with the same arithmetic the ULP already performs. The gaps
found are small, enumerated below, and none regress against what the ULP
produces today.

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
outline, placement context; 2270×1420 px at 300 DPI = exactly the 192×120 mm
board), and the execute channel was **not latched afterward**. A schematic
`WINDOW FIT; EXPORT IMAGE` pair worked identically. There is still no render
*endpoint* (screenshot query returns "No active graphics view" for the 2D
editors) — the PNGs land on the Fusion host's filesystem and are read back
via `/mnt/c`, same as the ULP path.

The headline operational win: **the whole capture becomes a zero-Escape,
zero-ULP, zero-staging workflow.** Reads are never latch-blocked, and —
verified live today — `EDIT .brd;`/`EDIT .sch;` editor switches, `RATSNEST`,
`DISPLAY`, `WINDOW FIT`, and `EXPORT IMAGE` dispatches do **not** latch the
execute channel (a no-op `fusion_mcp_execute` succeeded immediately after
each). The post-`RUN` dialog latch disappears with the `RUN`s themselves,
and `stage-ulps` is no longer needed at all.

## Field-by-field mapping

### Schematic export (`-thomson-export-sch.json`)

| ULP output | MCP source | Status |
|---|---|---|
| `project.name` | `electronics.Schematic.name` (temp path; strip like `FusionBridge.design_name()`) | verified |
| `project.variant` | `electronics.Variant` / `electronics.VariantDef` | verified (empty = no variants) |
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
| `components[].pads[]` (absolute) | `electronics.Smd` + `electronics.Pad` — **global board coords** with resolved `signal` name; join `contact_object_id` to `ContactRef` | verified (better than ULP: signal + drill + geometry per pad) |
| `board.area` | **gap** — `electronics.Board` has no bbox; derive from layer-20 (`BoardOutline`) `Wire` rows with `board_object_id` set | verified (outline wires read 0,0→192,0→192,120…) |
| `board.layers_used`, `layer_count` | `electronics.Layer` — but Fusion reports `used:1` for essentially every layer; derive copper usage from `Wire`/`Smd`/`PolyPour` presence per layer (the images ULP already uses the same workaround for its pre-scan) | workaround |
| `board.holes` | `electronics.Hole` (`x`, `y`, `drill`) | schema verified; design had none |
| `board.polygons` | `electronics.PolyPour` (`layer`, `isolate`, `rank`, `thermals` + `hatched`, `orphans`, `thermal_width`) via `signal_object_id` → `Signal.name` | schema verified; design had none — needs a poured design (comet) for parity |
| `signals[]` name/classification | `electronics.Signal.name` + client-side heuristics | verified |
| `signals[]` trace aggregates (`trace_length_mm`, min/max width, `segment_count`) | derive from `electronics.Wire` rows (`signal_object_id`, `layer`, `width`, endpoints) — same arithmetic the ULP runs | client-side |
| `signals[].trace_segments[]` | the same `Wire` rows, verbatim | verified |
| `signals[].via_count` | `electronics.Via` — richer than the ULP (drill, diameter, layer span, tenting flags) | schema verified; design unrouted |
| `analysis.component_edge_distances` | derive: `Element` positions vs. outline bbox | client-side |
| `analysis.decoupling_proximity` | derive: `ContactRef` ⋈ `Smd`/`Pad` (global coords) ⋈ `Signal` ⋈ `Element` | client-side |
| `analysis.ground_plane_layers` | `PolyPour` ⋈ `Signal.name` | client-side |

### Stackup export (`-thomson-export-stack.json`)

| ULP output | MCP source | Status |
|---|---|---|
| `all_layers[]` | `electronics.Layer` (`number`, `name`, `used`, `visible`) + the `IsCopperLayer` port | verified (with the `used` caveat above) |
| `copper_stack[]` physical order | same `CopperRank` logic, client-side | port |
| `board_description` | `electronics.Board.description` | verified |
| per-layer thickness / material | not exposed — **same gap the ULP has** (.dru not reachable); no regression | parity |

## Gaps (none regress vs. the ULP)

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
4. **`Layer.used` is unreliable** in Fusion (everything reads 1); copper-layer
   usage must be derived from object presence per layer — the images ULP
   already ships this exact workaround, so port it.

## Advantages over the ULP path

- **No dialog latch anywhere.** Reads never latch; `EDIT .brd;` /
  `EDIT .sch;`, `RATSNEST`, `DISPLAY`, `WINDOW FIT`, and `EXPORT IMAGE`
  dispatches all verified latch-free. The latch was a post-`RUN` artifact,
  and nothing `RUN`s anymore.
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
- `electronics.Schematic` and `electronics.Board` use camelCase `objectId`;
  every other entity uses snake_case `object_id`. Field selection must match
  (`{"fields": ["object_id"]}` errors on Schematic).
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

## Recommended next step

Implement `python tools/fusion_bridge.py export` (or a sibling
`tools/fusion_export.py`) that emits the exact `-thomson-export-sch.json`,
`-brd.json`, and `-stack.json` contracts from entity reads plus the
dispatch-generated images above, then run the roadmap §7 acceptance test:
capture a poured, routed design (comet) both ways and diff the data fields
and image inventory. `PolyPour`, `Via`, `Hole`, and the trace aggregates are
the parts today's unrouted design could not exercise — the parity diff
covers them. Once parity holds, Step 0 drops `stage-ulps`, both `RUN`
dispatches, and the Escape choreography entirely.
