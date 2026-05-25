#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--base", default=os.environ.get("SEARXNG_BASE", "http://192.168.5.5:8888"))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    url = args.base.rstrip("/") + "/search"
    params = {
        "q": args.query,
        "format": "json",
    }

    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": "searxng_query_failed",
            "detail": str(exc),
            "base": args.base,
            "query": args.query,
        }, indent=2))
        return 1

    results = []
    for item in data.get("results", [])[: args.limit]:
        href = item.get("url") or ""
        parsed = urlparse(href)
        results.append({
            "title": item.get("title"),
            "url": href,
            "domain": parsed.netloc,
            "content": item.get("content"),
            "score": item.get("score"),
            "is_pdf": href.lower().split("?")[0].endswith(".pdf") or "pdf" in (item.get("title") or "").lower(),
        })

    print(json.dumps({
        "ok": True,
        "base": args.base,
        "query": args.query,
        "count": len(results),
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
