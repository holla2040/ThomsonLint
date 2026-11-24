#!/usr/bin/env python3
"""ThomsonLint non-interactive review pipeline — the cross-platform port of run_review.sh.

Usage:
    python tools/run_review.py                    # auto-detect project from exports/
    python tools/run_review.py MySpecialProject   # explicit project name

Environment:
    THOMSONLINT_MODEL   Claude model to use (default: claude-opus-4-7)
    THOMSONLINT_BUDGET  Max spend in USD per run (default: 3 [dollars])

Requirements: the ``claude`` (Claude Code CLI) on PATH. No jq: the CLI's JSON
envelope is parsed here. The validate and report steps run under the same
Python interpreter as this script (``sys.executable``), so a venv just works.

What it does, in order (same as run_review.sh):

1. Detects the project from exports/*-thomson-export-sch.json (or the argument)
2. Regenerates review_instructions.txt (tools/gen_context.py)
3. ``claude --print`` with --allowedTools, --model, --output-format json,
   --json-schema <tests/findings_schema.json>, --no-session-persistence and
   --max-budget-usd; the envelope is saved to exports/.claude.output
4. Prints the envelope's ``result``; if Claude wrote no findings file, writes
   the envelope's ``structured_output`` to exports/<project>-findings.json
5. validate_json.py, then tools/gen_report.py

Example with overrides (PowerShell):
    $env:THOMSONLINT_MODEL = "claude-sonnet-4-6"; $env:THOMSONLINT_BUDGET = "10"
    python tools/run_review.py
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_context  # noqa: E402

DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_BUDGET = "3"
ALLOWED_TOOLS = "Read,Write,WebSearch,WebFetch,Bash(curl:*),Bash(wget:*)"
SCH_SUFFIX = "-thomson-export-sch.json"


class PipelineError(RuntimeError):
    """A fatal pipeline condition; the message is printed as ``ERROR: ...``."""


def detect_project(exports: Path, project: str | None) -> tuple[str, Path, Path]:
    """(project, sch, brd) — the argument wins, else the sole *-sch.json export."""
    if project:
        sch = exports / f"{project}{SCH_SUFFIX}"
        brd = exports / f"{project}-thomson-export-brd.json"
    else:
        sch_files = sorted(exports.glob(f"*{SCH_SUFFIX}"))
        if not sch_files:
            raise PipelineError(f"No *{SCH_SUFFIX} found in exports/")
        if len(sch_files) > 1:
            raise PipelineError(
                "Multiple projects in exports/. Pass the project name as the first argument.")
        sch = sch_files[0]
        project = sch.name[: -len(SCH_SUFFIX)]
        brd = exports / f"{project}-thomson-export-brd.json"
    if not sch.is_file():
        raise PipelineError(f"Schematic not found: {_rel(sch)}")
    if not brd.is_file():
        raise PipelineError(f"Board file not found: {_rel(brd)}")
    return project, sch, brd


def find_claude() -> str:
    """The ``claude`` executable on PATH (PATHEXT-aware on Windows)."""
    claude = shutil.which("claude")
    if not claude:
        raise PipelineError("Missing command 'claude'. Please install and try again.")
    if os.name == "nt" and claude.lower().endswith((".cmd", ".bat")):
        # cmd.exe re-parses the arguments; the JSON schema's quotes and
        # metacharacters would not survive it.
        raise PipelineError(
            f"'claude' resolves to a batch shim ({claude}); its arguments go through "
            "cmd.exe, which mangles the JSON schema. Install the native Claude Code "
            "(claude.exe) or put it first on PATH.")
    return claude


def build_prompt(project: str, review_date: str) -> str:
    return (
        "Follow the instructions in review_instructions.txt exactly. "
        f"Read and analyse exports/{project}-thomson-export-sch.json "
        f"and exports/{project}-thomson-export-brd.json. "
        "Output a JSON object matching tests/findings_schema.json. "
        f"Set project_name to '{project}' and review_date to '{review_date}'."
    )


def build_claude_cmd(claude: str, prompt: str, model: str, budget: str,
                     schema_text: str) -> list[str]:
    return [
        claude, "--print", prompt,
        "--allowedTools", ALLOWED_TOOLS,
        "--model", model,
        "--output-format", "json",
        "--json-schema", schema_text,
        "--no-session-persistence",
        "--max-budget-usd", budget,
    ]


def _jq_raw(value) -> str:
    """What ``jq -r`` prints for a value: strings raw, everything else as JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False)


def summarize(envelope_text: str) -> tuple[str, object]:
    """(console summary, structured_output) from the CLI's JSON envelope.

    Mirrors ``jq -r 'if .result then .result else (. | tostring) end'``:
    jq treats only null/false as false.
    """
    try:
        doc = json.loads(envelope_text)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"exports/.claude.output is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        return json.dumps(doc, separators=(",", ":"), ensure_ascii=False), None
    result = doc.get("result")
    if result is None or result is False:
        summary = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    else:
        summary = _jq_raw(result)
    return summary, doc.get("structured_output")


def _rel(path: Path) -> str:
    try:
        return Path(path).relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _run_step(cmd: list[str]) -> None:
    rc = subprocess.run(cmd, cwd=REPO_ROOT).returncode
    if rc != 0:
        raise SystemExit(rc)


def main(argv: list[str] | None = None, runner=subprocess.run) -> int:
    p = argparse.ArgumentParser(description="ThomsonLint non-interactive review pipeline.")
    p.add_argument("project", nargs="?", default=None,
                   help="project name (default: auto-detect from exports/)")
    args = p.parse_args(argv)
    # Claude's summary may hold characters the Windows console/pipe code page
    # cannot encode; degrade them instead of crashing after a paid run.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    os.chdir(REPO_ROOT)
    exports = REPO_ROOT / "exports"
    model = os.environ.get("THOMSONLINT_MODEL") or DEFAULT_MODEL
    budget = os.environ.get("THOMSONLINT_BUDGET") or DEFAULT_BUDGET

    try:
        # -- 1a. Detect project from exports/ ------------------------------
        project, _sch, _brd = detect_project(exports, args.project)
        # -- 1b. Required commands -----------------------------------------
        claude = find_claude()

        # -- 2. Regenerate review instructions ----------------------------
        print("[1/5] Regenerating review_instructions.txt...", flush=True)
        gen_context.write_bundle(REPO_ROOT / "review_instructions.txt", REPO_ROOT)

        review_date = datetime.date.today().isoformat()
        findings = exports / f"{project}-findings.json"
        report = exports / f"{project}-review.html"
        print(f"[2/5] Project : {project}")
        print(f"      Date    : {review_date}")
        print(f"      Model   : {model}")
        print(f"      Budget  : ${budget}")

        # -- 3. Run AI review ----------------------------------------------
        print("[3/5] Running AI review (this may take a minute)...", flush=True)
        schema_text = (REPO_ROOT / "tests" / "findings_schema.json").read_text(encoding="utf-8")
        cmd = build_claude_cmd(claude, build_prompt(project, review_date),
                               model, budget, schema_text)
        envelope_path = exports / ".claude.output"
        with open(envelope_path, "wb") as out:
            rc = runner(cmd, cwd=REPO_ROOT, stdout=out).returncode
        if rc != 0:
            return rc

        envelope = envelope_path.read_text(encoding="utf-8")
        summary, structured = summarize(envelope)
        print(summary)

        # Claude sometimes doesn't write the findings file itself (e.g. its
        # gen_report call was blocked for approval); recover it from the
        # envelope's structured output, as run_review.sh does.
        if not findings.exists():
            findings.write_text(_jq_raw(structured) + "\n", encoding="utf-8")
        print(f"      Findings : {_rel(findings)}")
    except PipelineError as exc:
        print(f"ERROR: {exc}")
        return 1

    # -- 4. Validate all JSON files ----------------------------------------
    print("[4/5] Validate findings report...", flush=True)
    _run_step([sys.executable, "validate_json.py"])

    # -- 5. Generate HTML report -------------------------------------------
    print("[5/5] Generating HTML report...", flush=True)
    _run_step([sys.executable, "tools/gen_report.py", _rel(findings), "--output", "exports/"])

    print("")
    print(f"Done — open '{_rel(report)}' in a browser to triage findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
