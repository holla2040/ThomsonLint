# AI Extraction Validation

PR27 validates saved `raw_response.json` files produced by a future AI packet
runner. It does not call AI, execute prompts, apply patches, mutate topology or
calculation artifacts, create findings, create violations, emit severity, or
make compliance judgments.

## Expected Response Shape

Each packet may contain:

```text
exports/TestProject/ai_packets/phase_12/packets/12B-001/raw_response.json
```

The raw response must be JSON with this top-level shape:

```json
{
  "packet_id": "12B-001",
  "schema_version": "ai_extraction_result_v1",
  "status": "completed",
  "extracted_items": [],
  "unknown_items": [],
  "notes": [],
  "warnings": []
}
```

`scripts/ai_extraction_validate.py` validates the response against
`schemas/ai_extraction_result_schema.json` and then applies packet-aware
semantic checks using the PR26 packet request/context.

## Lifecycle

Packets are classified as:

- `pending`: no `raw_response.json` exists.
- `accepted`: response exists and all extracted items are accepted.
- `rejected`: one or more extracted items were rejected.
- `human_review_needed`: evidence exists, but the item needs review before it
  can become patch input.
- `validation_failed`: packet-level JSON, schema, or packet ID validation
  failed.

Missing raw responses are pending by default, not failures. `--strict` treats
missing responses as validation errors.

## Evidence Requirements

Datasheets are the primary evidence source for component facts. Accepted
numeric values must include:

- `source_file`
- `source_page` when available
- `evidence_quote` or `evidence_ref`
- `unit`
- `condition` for current-related fields
- `confidence`

Datasheet-sourced values without `source_file` are rejected. Numeric values
without evidence are rejected. Source files and citations matter because later
patch application must be auditable and reversible.

## Confidence Thresholds

Confidence alone does not accept an item. Schema validity, supported target and
field names, supported units, and evidence are still required.

- `confidence >= 0.80`: eligible for acceptance when all evidence and semantic
  rules pass.
- `0.50 <= confidence < 0.80`: routed to human review.
- `confidence < 0.50`: rejected.

Ambiguous conditions, missing source pages, role/pin uncertainty, and multiple
candidate values can route an item to human review even when confidence is
otherwise acceptable.

## Unit Normalization

Supported normalizations:

- `A`, `mA`, `uA`, `µA` normalize to `A`.
- `V`, `mV` normalize to `V`.
- `ohm`, `mOhm`, `Ω`, `mΩ` normalize to `ohm`.
- `F`, `uF`, `µF`, `nF`, `pF` normalize to `F`.
- `text` remains `text`.

Unsupported units reject the item.

## Forbidden Outputs

The validator rejects AI output that attempts to emit findings, violations,
severity, pass/fail, compliance judgments, final calculations, or direct
topology/current/rating/copper/margin patches. Forbidden keys are rejected
anywhere in the response tree.

## Future Patch Apply

Accepted validation output is still not directly applied. It becomes candidate
input for a future AI patch apply PR, where deterministic patch schemas,
manifest linkage, and artifact regeneration gates can be enforced before any
current/rating/topology/copper/margin artifacts are changed.
