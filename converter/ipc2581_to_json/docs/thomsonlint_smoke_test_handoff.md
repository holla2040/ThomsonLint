# ThomsonLint Smoke-Test Handoff (Phase 7)

## Staged exports
- exports/example-bom.json
- exports/example-conversion-report.json
- exports/example-conversion-report.md
- exports/example-thomson-export-brd.json
- exports/example-thomson-export-sch.json
- exports/example-thomson-export-stack.json

## Backup
- Backup created: NONE (no prior non-empty `exports/` directory detected).

## Validation summary
From `examples/post_conversion/example-conversion-report.json`:
- ok: true
- json_round_trip_ok: true
- required_outputs_ok: true
- image_outputs_ok: true
- warnings_count: 4
- strict_would_fail: true
- ready_for_thomsonlint_smoke_test: true
- issues: []

## Claude Code launch command (Local LM Studio)
```bash
cd <repo root>
export ANTHROPIC_BASE_URL=http://192.168.5.5:1234
export ANTHROPIC_AUTH_TOKEN=lmstudio
unset ANTHROPIC_API_KEY
unset CLAUDE_CODE_USE_BEDROCK
unset AWS_BEDROCK_SERVICE_TIER
unset CLAUDE_CODE_USE_VERTEX
claude --model openai/qwen3.6-35b-a3b
```

## Claude Code launch command (Cloudflare LM Studio)
```bash
cd <repo root>
export ANTHROPIC_BASE_URL=https://lmstudio.qneural.org
export ANTHROPIC_AUTH_TOKEN=lmstudio
unset ANTHROPIC_API_KEY
unset CLAUDE_CODE_USE_BEDROCK
unset AWS_BEDROCK_SERVICE_TIER
unset CLAUDE_CODE_USE_VERTEX
claude --model openai/qwen3.6-35b-a3b
```

## In-Claude command
```text
/design-review
```

## Fallback prompt if `/design-review` is unavailable
```text
Read docs/REVIEWER_INSTRUCTIONS.md and follow it to review the converted example design in exports/. Use ontology/ontology.json, examples/examples.json, docs/AI_Hardware_Design_Review_KnowledgeBase.md, and the exported design files. Write exports/example-findings.json using the expected ThomsonLint findings format, validate it with tools/validate_findings.py, and generate the HTML report with tools/gen_report.py. This is a smoke test, so keep the review concise and focus on concrete evidence from the converted exports.
```

## Post-review validation commands
```bash
python3 tools/validate_findings.py exports/example-findings.json
python3 tools/gen_report.py exports/example-findings.json --output exports/
ls -lah exports
xdg-open exports/example-review.html
```
