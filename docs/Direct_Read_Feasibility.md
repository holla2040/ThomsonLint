# Direct MCP Reads vs. Export ULPs — Feasibility Investigation

**Date:** 2026-08-28
**Branch:** `feature/direct-UlP`
**Verified against:** live Fusion Electronics session, design `series-shunt`
(1 sheet, 74 components placed, unrouted), Fusion MCP Server over the
`tools/fusion_bridge.py` transport and the registered `fusion` MCP tools.

## Verdict

**Yes — the two JSON exporters can be replaced by direct
`fusion_mcp_electronics_read` queries.** Everything
`fusion-electronics-export.ulp` (both modes) and
`fusion-electronics-stackup.ulp` write is either directly readable as an
entity field or derivable client-side from raw entity rows with the same
arithmetic the ULP already performs. The gaps found are small, enumerated
below, and none regress against what the ULP produces today.

**`fusion-electronics-images.ulp` is not replaceable.** There is no render
endpoint in the MCP surface (roadmap §"What to Ask Autodesk For" item 4), and
Fusion's screenshot query returns "No active graphics view" for the 2D
electronics editors. The image pass keeps the ULP + `RUN` dispatch + one
Escape per pass.

The headline operational win: **the JSON capture becomes a zero-Escape
workflow.** Reads are never latch-blocked, and — verified live today —
dispatching `EDIT .brd;` / `EDIT .sch;` to switch editors does **not** latch
the execute channel (a no-op `fusion_mcp_execute` succeeded immediately after
both switches). The post-`RUN` dialog latch only remains for the image pass.

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

- **No dialog latch for JSON capture.** Reads never latch; `EDIT .brd;` /
  `EDIT .sch;` editor switches verified latch-free. Only the image pass still
  needs `RUN` + one Escape.
- **UTF-8 end to end.** Python writes the JSON, retiring the Latin-1 ULP
  output wart (the `gesam-Maß` decode workaround).
- **Richer data:** per-pad signal + drill + geometry, via drill/span/tenting,
  pour hatch/orphan settings, `Element.locked`.
- **`electronics.Error`** exposes the live DRC/ERC table (including airwires
  with coordinates — verified live) — a new evidence category the ULP path
  never had; the roadmap already earmarks it for findings evidence (§7 v1.5).
- No staging of ULPs to a Windows-visible share for the JSON pass
  (`stage-ulps` remains only for images).

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

## Recommended next step

Implement `python tools/fusion_bridge.py export` (or a sibling
`tools/fusion_export.py`) that emits the exact `-thomson-export-sch.json`,
`-brd.json`, and `-stack.json` contracts from entity reads, then run the
roadmap §7 acceptance test: capture a poured, routed design (comet) both ways
and diff the data fields. `PolyPour`, `Via`, `Hole`, and the trace aggregates
are the parts today's unrouted design could not exercise — the parity diff
covers them. The images ULP and its Step 0 choreography stay as-is.
