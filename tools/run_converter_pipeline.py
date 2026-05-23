#!/usr/bin/env python3
"""
Run the integrated ThomsonLint converter and stage outputs into ./exports.

This script intentionally does not run an AI review. It prepares the evidence
bundle that ThomsonLint/OpenHands should review.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run integrated converter and stage ThomsonLint exports.")
    parser.add_argument("input_root", help="Input design folder containing IPC/PADS/BOM/PDF files.")
    parser.add_argument("--project-name", default="example", help="Project name prefix for generated files.")
    parser.add_argument("--pretty", action="store_true", default=True, help="Pretty-print JSON output.")
    parser.add_argument("--clean", action="store_true", help="Remove existing exports before running.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    converter_repo = repo / "converter" / "ipc2581_to_json"
    converter = converter_repo / "thomson_bundle_converter.py"
    input_root = Path(args.input_root).resolve()
    exports = repo / "exports"

    if not converter.exists():
        raise SystemExit(f"Converter not found: {converter}")

    if not input_root.exists():
        raise SystemExit(f"Input root not found: {input_root}")

    if args.clean and exports.exists():
        shutil.rmtree(exports)

    exports.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3",
        str(converter),
        str(input_root),
        "--project-name",
        args.project_name,
        "--output-root",
        str(exports),
        "--pretty",
    ]

    run(cmd, cwd=repo)

    print()
    print("Converter outputs staged in:", exports)
    print("Generated files:")
    for path in sorted(exports.glob("*")):
        if path.is_file():
            print(" -", path.relative_to(repo))


if __name__ == "__main__":
    main()
