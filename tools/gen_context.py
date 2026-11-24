#!/usr/bin/env python3
"""Generate review_instructions.txt — the cross-platform port of gen_context.sh.

A single-file bundle for upload to web AIs (Gemini, Claude.ai, ChatGPT, etc.).
This path is untested by the maintainers. The tested driver is Claude Code,
which reads docs/REVIEWER_INSTRUCTIONS.md and the knowledge base files directly
and does NOT need this bundle (see README §5).

The output is byte-identical to ``./gen_context.sh``: the source files are
copied as raw bytes (UTF-8, LF line endings preserved) with the same separator
text between them. Paths resolve against the repo root, so it runs from any
directory.

    python tools/gen_context.py -o review_instructions.txt
    python tools/gen_context.py > review_instructions.txt   # bash / cmd.exe

On Windows PowerShell 5.1, prefer ``-o``: its ``>`` re-encodes output as
UTF-16, which would break the bundle.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_KB_START = b"""
---
### KNOWLEDGE BASE START
---

The knowledge base referenced by the instructions above follows. Process it
before beginning the review.

--- START OF ONTOLOGY ---
"""

_ONTOLOGY_END = b"""
--- END OF ONTOLOGY ---


--- START OF EXAMPLES ---
"""

_EXAMPLES_END = b"""
--- END OF EXAMPLES ---


--- START OF KNOWLEDGE BASE DOCUMENT ---
"""

_KB_END = b"""
--- END OF KNOWLEDGE BASE DOCUMENT ---

---
### KNOWLEDGE BASE END
---
"""


def build_bundle(root: Path = REPO_ROOT) -> bytes:
    """The bundle bytes, assembled exactly as gen_context.sh's cat/heredocs do."""
    def read(rel: str) -> bytes:
        return (root / rel).read_bytes()

    return b"".join([
        read("docs/REVIEWER_INSTRUCTIONS.md"),
        _KB_START,
        read("ontology/ontology.json"),
        _ONTOLOGY_END,
        read("examples/examples.json"),
        _EXAMPLES_END,
        read("docs/AI_Hardware_Design_Review_KnowledgeBase.md"),
        _KB_END,
    ])


def write_bundle(path: Path, root: Path = REPO_ROOT) -> None:
    Path(path).write_bytes(build_bundle(root))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate the review_instructions.txt bundle.")
    p.add_argument("-o", "--output", default=None,
                   help="write to this file instead of stdout")
    args = p.parse_args(argv)
    try:
        data = build_bundle()
    except OSError as exc:
        print(f"gen_context: {exc}", file=sys.stderr)
        return 1
    if args.output:
        Path(args.output).write_bytes(data)
    else:
        sys.stdout.buffer.write(data)  # binary: no CRLF translation on Windows
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
