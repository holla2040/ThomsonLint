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
- Run natively (Windows or macOS, same machine as Fusion): the endpoint is
  ``127.0.0.1:27182`` and nothing else is needed.
- Under WSL2 (legacy), the right host depends on the networking mode (``wslinfo
  --networking-mode``). **Mirrored**: WSL shares the Windows loopback, so
  ``127.0.0.1:27182`` works directly and no portproxy may exist (a stale
  ``0.0.0.0`` rule steals Fusion's bind). **NAT**: the Windows loopback is
  unreachable; connect to the WSL default-gateway IP through a Windows
  ``netsh interface portproxy`` rule forwarding ``<gateway-ip>:27182`` →
  ``127.0.0.1:27182`` (bind the gateway IP, not ``0.0.0.0``).
  :func:`_default_host` probes loopback first and, on Linux/WSL only, falls
  back to the gateway, so both modes work unconfigured. See README "Reading
  from Fusion Electronics"; troubleshoot with
  ``~/claude-code-fusion-mcp-check/check.sh``.
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
import ntpath
import os
import platform
import posixpath
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 27182


def host_platform() -> str:
    """``"windows"``, ``"macos"``, ``"wsl"`` or ``"linux"`` (where this Python runs).

    Natively (Windows / macOS) this process and Fusion share one filesystem
    and one loopback. Under WSL they do not, so paths and the host need
    translating. Plain Linux cannot run Fusion; it gets the WSL behaviour.
    """
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower():
        return "wsl"
    return "linux"


def _setup_hint(plat: str | None = None) -> str:
    plat = plat or host_platform()
    lines = [
        "Could not reach Fusion's MCP server. Check that:",
        "  1. Fusion is running with an Electronics design open (no modal dialog).",
        "  2. Preferences > General > API > 'Fusion MCP Server' is enabled.",
    ]
    if plat in ("wsl", "linux"):
        lines += [
            "  3. NAT-mode WSL only: a netsh portproxy forwards <gateway-ip>:27182 ->",
            "     127.0.0.1:27182 (bind the gateway IP, not 0.0.0.0; turn Tailscale off).",
            "     Mirrored-mode WSL shares the Windows loopback and needs no portproxy.",
            "  Diagnose layer-by-layer: ~/claude-code-fusion-mcp-check/check.sh",
        ]
    else:
        lines += [
            "  3. This runs on the same machine as Fusion: the server listens on",
            f"     127.0.0.1:{DEFAULT_PORT} only. No port forwarding is needed.",
        ]
    lines.append(
        "  Override the host with --fusion-host or the THOMSONLINT_FUSION_HOST "
        "environment variable."
    )
    return "\n".join(lines)


SETUP_HINT = _setup_hint()

# Shared staging directory. The ULPs must live on a path Fusion can RUN, and
# Fusion's JSON/PNG output lands in a sibling exports/ that this process reads
# back. Natively that is one path seen identically by both sides; under WSL it
# is the same Windows directory under two names — the pattern Hendley proved.
DEFAULT_SHARE_WSL = "/mnt/c/Users/Public/thomsonlint"


def default_share_dir(plat: str | None = None) -> str:
    """A per-platform directory that Fusion itself can write to.

    Windows: ``%PUBLIC%\\thomsonlint`` (normally ``C:\\Users\\Public\\thomsonlint``,
    the same physical directory the WSL default names). macOS: ``~/.thomsonlint``
    (outside the TCC-protected Desktop/Documents/Downloads folders). WSL / Linux:
    the existing ``/mnt/c`` path.
    """
    plat = plat or host_platform()
    if plat == "windows":
        public = os.environ.get("PUBLIC") or r"C:\Users\Public"
        return ntpath.join(public, "thomsonlint")
    if plat == "macos":
        return posixpath.join(posixpath.expanduser("~"), ".thomsonlint")
    return DEFAULT_SHARE_WSL


DEFAULT_SHARE = default_share_dir()


class BridgeError(RuntimeError):
    """Raised when the Fusion bridge returns an error or an unusable response."""


def _default_gateway() -> str | None:
    """The Windows host IP as seen from WSL2 = the default route's gateway.

    Returns None when it cannot be determined (no ``ip`` binary, no default
    route); the caller then falls back to loopback, whose connection failure
    carries the setup hint.
    """
    try:
        out = subprocess.check_output(["ip", "route"], text=True, encoding="utf-8")
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        if line.startswith("default"):
            return line.split()[2]
    return None


def _default_host(port: int = DEFAULT_PORT, plat: str | None = None) -> str:
    """Pick the host that actually reaches Fusion.

    Natively (Windows / macOS) Fusion is always on loopback. Under WSL,
    mirrored mode shares the Windows loopback (and its default gateway is
    just the LAN router, which can never work); NAT mode reaches Fusion only
    through the gateway portproxy. A quick connect probe on loopback
    distinguishes the two without asking which mode this is. The gateway is
    only tried on Linux/WSL; everywhere else (or when no gateway is found)
    loopback is returned and the first request fails with the setup hint.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return "127.0.0.1"
    except OSError:
        pass
    if (plat or host_platform()) in ("wsl", "linux"):
        gateway = _default_gateway()
        if gateway:
            return gateway
    return "127.0.0.1"


def to_fusion_path(path: str, plat: str | None = None) -> str:
    """The local ``path`` as Fusion sees it, for use inside EAGLE commands.

    Natively that is the same path, made absolute (Windows keeps its
    backslashes; callers that want ``C:/...`` replace them). Under WSL it is
    translated with :func:`wsl_to_windows`. EAGLE commands quote paths with
    single quotes and may not contain double quotes, so a path containing
    either is rejected here rather than producing a broken command.
    """
    plat = plat or host_platform()
    if plat in ("wsl", "linux"):
        fusion_path = wsl_to_windows(path)
    elif plat == "windows":
        fusion_path = ntpath.abspath(path)
    else:
        fusion_path = posixpath.abspath(posixpath.expanduser(path))
    if "'" in fusion_path or '"' in fusion_path:
        raise BridgeError(
            f"{fusion_path!r} contains a quote character, which cannot be passed "
            "inside an EAGLE command. Use a share directory without quotes "
            "(--share / --dir or THOMSONLINT_FUSION_SHARE)."
        )
    return fusion_path


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
    ``HENDLEY_FUSION_HOST`` → loopback if it answers (native, mirrored WSL),
    else on Linux/WSL the default-gateway IP (NAT WSL), else loopback. The
    session id is held
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
            self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except (urllib.error.URLError, OSError) as exc:
            raise BridgeError(f"cannot reach Fusion at {self.url}: {exc}\n\n{SETUP_HINT}") from exc
        body = resp.read().decode("utf-8")
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

        Every command is prefixed with ``SET CONFIRM YES;`` — without it the
        MCP add-in latches into "Cannot perform 'script' while a command dialog
        is open" after dispatches like ``EDIT`` or ``RUN`` (a known Fusion
        issue: no dialog is actually visible, and only an Escape keypress in
        the Fusion window clears the latch). The prefix auto-confirms whatever
        the add-in thinks is pending, so back-to-back dispatches work.
        """
        if '"' in command:
            raise ValueError(
                f"EAGLE command may not contain double quotes: {command!r} "
                "(quote ULP paths with single quotes, e.g. RUN '...')"
            )
        inner = f'Electron.run "SET CONFIRM YES; {command}"'
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
        if not design:
            # Reads follow the active editor: with the board tab active the
            # schematic reads empty. That is still a live, capturable design —
            # the schematic pass's leading "EDIT .S1;" switches back to it.
            boards = bridge.read_all("electronics.Board")
            if boards:
                stem = boards[0].get("name", "").replace("\\", "/").rsplit("/", 1)[-1]
                design = stem.removesuffix(".brd").strip()
                print(
                    f"OK — Fusion reachable at {bridge.host}; design '{design}', "
                    "board editor active (sheet count readable once the schematic is active)."
                )
                return 0
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
    """Copy the export ULPs into a Fusion-visible dir and print Fusion's path to it.

    The ULPs derive their output directory from their own location
    (``<ulpDir>/../exports``), so we also create the sibling exports/ dir here.
    The printed tools path (as Fusion sees it — a ``C:\\`` path under WSL) is
    what goes into ``RUN '<path>/...ulp'``; the local exports path (where
    output lands) is reported on stderr.
    """
    repo_tools = Path(__file__).resolve().parent
    ulps = sorted(repo_tools.glob("fusion-electronics-*.ulp"))
    if not ulps:
        print(f"no fusion-electronics-*.ulp found in {repo_tools}", file=sys.stderr)
        return 2

    share = Path(args.dir).expanduser()
    share_tools = share / "tools"
    share_exports = share / "exports"
    try:
        share_tools.mkdir(parents=True, exist_ok=True)
        share_exports.mkdir(parents=True, exist_ok=True)
        for ulp in ulps:
            shutil.copy2(ulp, share_tools / ulp.name)
        fusion_tools_path = to_fusion_path(str(share_tools))
    except (OSError, BridgeError) as exc:
        print(f"could not stage ULPs into {share}: {exc}", file=sys.stderr)
        return 2

    print(
        f"staged {len(ulps)} ULP(s) -> {share_tools}\n"
        f"output will land in:      {share_exports}\n"
        f"copy results back with:   {_copy_back_hint(share_exports)}",
        file=sys.stderr,
    )
    # stdout = just Fusion's tools path, so `STAGE=$(... stage-ulps)` is clean.
    print(fusion_tools_path)
    return 0


def _copy_back_hint(exports: Path, plat: str | None = None) -> str:
    """A copy command for the platform's usual shell (PowerShell on Windows)."""
    if (plat or host_platform()) == "windows":
        return (f"Copy-Item '{exports}\\*-thomson-export-*.json', "
                f"'{exports}\\*-img-*.png' exports\\")
    return f"cp {exports}/*-thomson-export-*.json {exports}/*-img-*.png exports/"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Drive a live Fusion Electronics session for ThomsonLint capture.",
    )
    p.add_argument(
        "--fusion-host",
        default=None,
        help="Fusion host IP (default: THOMSONLINT_FUSION_HOST, HENDLEY_FUSION_HOST, else "
        "127.0.0.1; under WSL falls back to the default gateway).",
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
        help="Copy the export ULPs to a dir Fusion can read; prints Fusion's path to it.",
    )
    sp.add_argument(
        "--dir",
        default=os.environ.get("THOMSONLINT_FUSION_SHARE", DEFAULT_SHARE),
        help="Directory to stage into; under WSL it must be under /mnt/<drive> "
        f"(default: THOMSONLINT_FUSION_SHARE or {DEFAULT_SHARE}).",
    )
    sp.set_defaults(func=cmd_stage_ulps)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
