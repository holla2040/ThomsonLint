#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


def safe_name(text: str, max_len: int = 90) -> str:
    text = text.strip() or "datasheet"
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:max_len] or "datasheet"


def infer_ext(url: str, content_type: str | None) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf"):
        return ".pdf"

    if content_type:
        content_type = content_type.split(";")[0].strip().lower()
        if content_type == "application/pdf":
            return ".pdf"
        ext = mimetypes.guess_extension(content_type)
        if ext:
            return ext

    return ".bin"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--mpn", default="")
    parser.add_argument("--manufacturer", default="")
    parser.add_argument("--row-index", required=True)
    parser.add_argument("--out-dir", default="datasheets")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    label_parts = [
        f"row{args.row_index}",
        args.manufacturer,
        args.mpn,
    ]
    base = safe_name("_".join(p for p in label_parts if p))

    headers = {
        "User-Agent": "Mozilla/5.0 ThomsonLint datasheet retrieval"
    }

    try:
        r = requests.get(args.url, headers=headers, timeout=args.timeout, allow_redirects=True)
        r.raise_for_status()
    except Exception as exc:
        print(f"DOWNLOAD_FAILED: {exc}", file=sys.stderr)
        return 2

    content_type = r.headers.get("content-type", "")
    ext = infer_ext(args.url, content_type)

    # Reject obvious HTML pages as a "datasheet file".
    # Manufacturer product pages may be useful as candidate URLs, but they are not saved as found datasheets.
    if "text/html" in content_type.lower() and ext != ".pdf":
        print(f"DOWNLOAD_REJECTED_HTML: content-type={content_type}", file=sys.stderr)
        return 3

    content = r.content
    if len(content) < 512:
        print(f"DOWNLOAD_REJECTED_TOO_SMALL: {len(content)} bytes", file=sys.stderr)
        return 4

    # If it claims PDF or filename is PDF, require PDF magic.
    if ext == ".pdf" and not content.startswith(b"%PDF"):
        print("DOWNLOAD_REJECTED_NOT_PDF_MAGIC", file=sys.stderr)
        return 5

    digest = hashlib.sha256(content).hexdigest()[:12]
    out_path = out_dir / f"{base}_{digest}{ext}"
    out_path.write_bytes(content)

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
