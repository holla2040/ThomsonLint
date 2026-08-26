#!/usr/bin/env python3
"""Fusion Electronics HTTP bridge for ThomsonLint — vendored, stdlib-only.

ThomsonLint reviews a design that is *open in Fusion Electronics*. This module
lets the reviewer drive that live session directly instead of asking the user to
run the export ULPs by hand: it can run any EAGLE command (including
``RUN <ulp>``), switch between the schematic and the board, enumerate sheets, and
read the electronics object model.

It is the read/dispatch half of the "v1.5 hybrid" path in
``docs/Future_Direction_and_Roadmap.md`` §7 — the ULPs still do the extraction and
the pre-computation; the bridge just runs them without a human at the EAGLE prompt.

How it talks to Fusion (vendored from the ``~/hendley`` project's verified
``docs/fusion-notes.md`` recipe, so a fresh checkout needs no session notes):

- Fusion publishes a local HTTP endpoint on port 27182 at ``/mcp`` when
  Preferences > General > API > "Fusion MCP Server" is enabled. That Autodesk
  toggle is the only thing here named "MCP" — this is plain JSON-RPC over HTTP,
  no MCP client library involved.
- The right host depends on the WSL networking mode (``wslinfo
  --networking-mode``). **Mirrored**: WSL shares the Windows loopback, so
  ``127.0.0.1:27182`` works directly and no portproxy may exist (a stale
  ``0.0.0.0`` rule steals Fusion's bind). **NAT**: the Windows loopback is
  unreachable; connect to the WSL default-gateway IP through a Windows
  ``netsh interface portproxy`` rule forwarding ``<gateway-ip>:27182`` →
  ``127.0.0.1:27182`` (bind the gateway IP, not ``0.0.0.0``).
  :func:`_default_host` probes loopback first and falls back to the gateway,
  so both modes work unconfigured. See README "Reading from Fusion
  Electronics"; troubleshoot with ``~/claude-code-fusion-mcp-check/check.sh``.
- ...but send ``Host: 127.0.0.1:27182`` on every request — the server validates
  the ``Host`` header and 403s ("Invalid Host header") on the gateway IP.
- Capture the ``MCP-Session-Id`` response header from ``initialize`` and resend it;
  POST ``notifications/initialized`` once before any ``tools/call``. Reads return
  rows as a JSON string in ``result.content[0].text`` → ``{"items", "pagination"}``.

CLI verbs (the reviewer composes these; orchestration lives in
``docs/REVIEWER_INSTRUCTIONS.md`` "Step 0 — Live Fusion Capture"):

    python tools/fusion_bridge.py ping
    python tools/fusion_bridge.py eagle "BOARD;"
    python tools/fusion_bridge.py eagle "RUN 'C:\\...\\fusion-electronics-export.ulp'"
    python tools/fusion_bridge.py read electronics.Sheet
    python tools/fusion_bridge.py stage-ulps
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 27182

SETUP_HINT = (
    "Could not reach Fusion's MCP server. Check that:\n"
    "  1. Fusion is running with an Electronics design open (no modal dialog).\n"
    "  2. Preferences > General > API > 'Fusion MCP Server' is enabled.\n"
    "  3. NAT-mode WSL only: a netsh portproxy forwards <gateway-ip>:27182 ->\n"
    "     127.0.0.1:27182 (bind the gateway IP, not 0.0.0.0; turn Tailscale off).\n"
    "     Mirrored-mode WSL shares the Windows loopback and needs no portproxy.\n"
    "  Diagnose layer-by-layer: ~/claude-code-fusion-mcp-check/check.sh\n"
    "  Override the host with --fusion-host or $THOMSONLINT_FUSION_HOST."
)

# WSL <-> Windows shared staging directory. The ULPs must live on a path Fusion
# (Windows) can RUN, and their JSON/PNG output lands in a sibling exports/ that
# WSL reads back. Same directory, two names — the pattern Hendley proved.
DEFAULT_SHARE_WSL = "/mnt/c/Users/Public/thomsonlint"


class BridgeError(RuntimeError):
    """Raised when the Fusion bridge returns an error or an unusable response."""


def _default_gateway() -> str:
    """The Windows host IP as seen from WSL2 = the default route's gateway."""
    out = subprocess.check_output(["ip", "route"], text=True)
    for line in out.splitlines():
        if line.startswith("default"):
            return line.split()[2]
    raise BridgeError("no default gateway found; pass the Fusion host explicitly")


def _default_host(port: int = DEFAULT_PORT) -> str:
    """Pick the host that actually reaches Fusion, whatever the WSL mode.

    Mirrored-mode WSL shares the Windows loopback (and its default gateway is
    just the LAN router, which can never work); NAT-mode WSL reaches Fusion
    only through the gateway portproxy. A quick connect probe on loopback
    distinguishes the two without asking which mode this is.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return "127.0.0.1"
    except OSError:
        return _default_gateway()


def wsl_to_windows(path: str) -> str:
    """``/mnt/c/Users/Public/x`` -> ``C:\\Users\\Public\\x`` for use in EAGLE commands."""
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", path)
    if not m:
        raise BridgeError(
            f"{path!r} is not under /mnt/<drive>/ — Fusion (Windows) cannot RUN a "
            "ULP from a pure-WSL path. Use a directory under /mnt/c (see --dir)."
        )
    drive, rest = m.group(1).upper(), m.group(2).replace("/", "\\")
    return f"{drive}:\\{rest}"


class FusionBridge:
    """One HTTP session to Fusion's local endpoint.

    Host resolution order: explicit ``host`` arg → ``THOMSONLINT_FUSION_HOST`` →
    ``HENDLEY_FUSION_HOST`` → loopback if it answers (mirrored WSL), else the
    WSL default-gateway IP (NAT WSL). The session id is held
    in-process and created lazily on the first call.
    """

    def __init__(self, host: str | None = None, port: int = DEFAULT_PORT, timeout: int = 120):
        self.host = (
            host
            or os.environ.get("THOMSONLINT_FUSION_HOST")
            or os.environ.get("HENDLEY_FUSION_HOST")
            or _default_host(port)
        )
        self.url = f"http://{self.host}:{port}/mcp"
        self._loopback = f"127.0.0.1:{port}"  # what the Host header must read as
        self.timeout = timeout
        self._sid: str | None = None

    # -- plumbing ----------------------------------------------------------

    def _post(self, payload: dict, want_headers: bool = False):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Host": self._loopback,
        }
        if self._sid:
            headers["MCP-Session-Id"] = self._sid
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except (urllib.error.URLError, OSError) as exc:
            raise BridgeError(f"cannot reach Fusion at {self.url}: {exc}\n\n{SETUP_HINT}") from exc
        body = resp.read().decode()
        return (resp.headers, body) if want_headers else body

    def _ensure_session(self) -> None:
        if self._sid:
            return
        headers, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "thomsonlint", "version": "1.0"},
                },
            },
            want_headers=True,
        )
        sid = headers.get("MCP-Session-Id") or headers.get("mcp-session-id")
        if not sid:
            raise BridgeError("initialize returned no MCP-Session-Id header")
        self._sid = sid
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call_tool(self, name: str, arguments: dict) -> dict:
        """``tools/call`` → the parsed payload from ``result.content[0].text``."""
        self._ensure_session()
        body = self._post(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        doc = json.loads(body)
        if "error" in doc:
            raise BridgeError(f"bridge error: {doc['error']}")
        return json.loads(doc["result"]["content"][0]["text"])

    # -- reads --------------------------------------------------------------

    def read(self, entity_type: str, obj: dict | None = None) -> dict:
        """One ``fusion_mcp_electronics_read`` call (rows come back paginated)."""
        args: dict = {"entity_type": entity_type}
        if obj:
            args["object"] = obj
        return self.call_tool("fusion_mcp_electronics_read", args)

    def read_all(self, entity_type: str, obj: dict | None = None, page: int = 1000) -> list[dict]:
        """Read every row of an entity: loop offsets until an empty batch."""
        items: list[dict] = []
        offset = 0
        for _ in range(100):  # runaway guard
            o = dict(obj or {})
            o["pagination"] = {"limit": page, "offset": offset}
            batch = self.read(entity_type, o).get("items", [])
            if not batch:
                break
            items.extend(batch)
            offset += len(batch)
        return items

    # -- dispatch -----------------------------------------------------------

    def execute_script(self, py_source: str) -> dict:
        """``fusion_mcp_execute``: run Python (must define ``def run(_context):``) in Fusion."""
        return self.call_tool(
            "fusion_mcp_execute", {"featureType": "script", "object": {"script": py_source}}
        )

    def run_eagle(self, command: str) -> dict:
        """Dispatch an EAGLE command into the electronics interpreter.

        Wraps the command in ``Electron.run "…"`` (a bare ``executeTextCommand``
        hits Fusion's *core* channel and fails). ``Electron.run`` returns no echo,
        so effects (files written, context switched) are verified out-of-band.

        The command may contain single quotes and backslashes — e.g.
        ``RUN 'C:\\tools\\x.ulp'``. The whole ``Electron.run "…"`` string is
        embedded into the executed Python with ``repr()`` so quotes and
        backslashes survive intact. A naive f-string would break on a Windows
        path (``C:\\Users`` is an invalid ``\\U`` escape in a Python literal) or
        on the single quotes colliding with the source literal. Double quotes are
        rejected because they delimit the ``Electron.run`` argument itself.
        """
        if '"' in command:
            raise ValueError(
                f"EAGLE command may not contain double quotes: {command!r} "
                "(quote ULP paths with single quotes, e.g. RUN '...')"
            )
        inner = f'Electron.run "{command}"'
        source = (
            "import adsk.core\n"
            "def run(_context):\n"
            "    app = adsk.core.Application.get()\n"
            f"    app.executeTextCommand({inner!r})\n"
        )
        return self.execute_script(source)

    def design_name(self) -> str | None:
        """The open design's name, or None if no schematic is readable."""
        rows = self.read_all("electronics.Schematic")
        if not rows:
            return None
        # name is a temp path ending in "<design> sch.sch"
        stem = rows[0].get("name", "").replace("\\", "/").rsplit("/", 1)[-1]
        return stem.removesuffix(".sch").removesuffix(" sch").strip() or None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _bridge(args) -> FusionBridge:
    return FusionBridge(host=args.fusion_host)


def cmd_ping(args) -> int:
    """Preflight: initialize and confirm an electronics design is open."""
    bridge = _bridge(args)
    try:
        design = bridge.design_name()
    except BridgeError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not design:
        print(
            "Connected to Fusion, but no electronics schematic is readable. "
            "Is a design open and free of modal dialogs?",
            file=sys.stderr,
        )
        return 3
    sheets = bridge.read_all("electronics.Sheet")
    print(f"OK — Fusion reachable at {bridge.host}; design '{design}', {len(sheets)} sheet(s).")
    return 0


def cmd_eagle(args) -> int:
    """Dispatch a single EAGLE command via Electron.run."""
    bridge = _bridge(args)
    try:
        result = bridge.run_eagle(args.command)
    except (BridgeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2
    # Electron.run returns no echo; report the execute envelope for visibility.
    ok = result.get("success", True)
    msg = (result.get("message") or "").strip()
    print(f"dispatched: {args.command}" + (f" — {msg}" if msg else ""))
    return 0 if ok else 4


def cmd_read(args) -> int:
    """Read an electronics entity and print items as JSON."""
    bridge = _bridge(args)
    obj: dict = {}
    if args.filter:
        obj["filters"] = [
            {"property": prop, "op": op, "value": _coerce(val)} for prop, op, val in args.filter
        ]
    try:
        if args.limit:
            obj["pagination"] = {"limit": args.limit, "offset": 0}
            items = bridge.read(args.entity, obj or None).get("items", [])
        else:
            items = bridge.read_all(args.entity, obj or None)
    except BridgeError as exc:
        print(exc, file=sys.stderr)
        return 2
    json.dump(items, sys.stdout, indent=2)
    print()
    return 0


def _coerce(val: str):
    """Filter values arrive as strings; pass ints through as ints."""
    try:
        return int(val)
    except ValueError:
        return val


def cmd_stage_ulps(args) -> int:
    """Copy the export ULPs into a Windows-visible dir and print its C:\\ path.

    The ULPs derive their output directory from their own location
    (``<ulpDir>/../exports``), so we also create the sibling exports/ dir here.
    The printed Windows tools path is what goes into ``RUN '<path>/...ulp'``;
    the WSL exports path (where output lands) is reported on stderr.
    """
    repo_tools = Path(__file__).resolve().parent
    ulps = sorted(repo_tools.glob("fusion-electronics-*.ulp"))
    if not ulps:
        print(f"no fusion-electronics-*.ulp found in {repo_tools}", file=sys.stderr)
        return 2

    share = Path(args.dir).expanduser()
    win_tools = share / "tools"
    wsl_exports = share / "exports"
    try:
        win_tools.mkdir(parents=True, exist_ok=True)
        wsl_exports.mkdir(parents=True, exist_ok=True)
        for ulp in ulps:
            shutil.copy2(ulp, win_tools / ulp.name)
        win_tools_path = wsl_to_windows(str(win_tools))
    except (OSError, BridgeError) as exc:
        print(f"could not stage ULPs into {share}: {exc}", file=sys.stderr)
        return 2

    print(
        f"staged {len(ulps)} ULP(s) -> {win_tools}\n"
        f"output will land in (WSL): {wsl_exports}\n"
        f"copy results back with:   cp {wsl_exports}/*-thomson-export-*.json "
        f"{wsl_exports}/*-img-*.png exports/",
        file=sys.stderr,
    )
    # stdout = just the Windows tools dir, so `STAGE=$(... stage-ulps)` is clean.
    print(win_tools_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Drive a live Fusion Electronics session for ThomsonLint capture.",
    )
    p.add_argument(
        "--fusion-host",
        default=None,
        help="Fusion host IP (default: $THOMSONLINT_FUSION_HOST, $HENDLEY_FUSION_HOST, or WSL gateway).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("ping", help="Confirm Fusion is reachable and a design is open.")
    sp.set_defaults(func=cmd_ping)

    sp = sub.add_parser("eagle", help="Dispatch one EAGLE command (e.g. \"BOARD;\", \"EDIT .S1;\", \"RUN '...'\").")
    sp.add_argument("command", help="The EAGLE command; may not contain double quotes.")
    sp.set_defaults(func=cmd_eagle)

    sp = sub.add_parser("read", help="Read an electronics entity (e.g. electronics.Sheet) as JSON.")
    sp.add_argument("entity", help="Entity type, e.g. electronics.Sheet / electronics.Part.")
    sp.add_argument(
        "--filter",
        nargs=3,
        action="append",
        metavar=("PROP", "OP", "VALUE"),
        help="Filter, e.g. --filter part_object_id eq 42. Repeatable.",
    )
    sp.add_argument("--limit", type=int, default=None, help="Cap rows (default: read all).")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser(
        "stage-ulps",
        help="Copy the export ULPs to a Windows-visible dir; prints the C:\\ tools path.",
    )
    sp.add_argument(
        "--dir",
        default=os.environ.get("THOMSONLINT_FUSION_SHARE", DEFAULT_SHARE_WSL),
        help=f"WSL path under /mnt/<drive> to stage into (default: {DEFAULT_SHARE_WSL}).",
    )
    sp.set_defaults(func=cmd_stage_ulps)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
