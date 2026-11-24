"""Native Windows / macOS (and WSL fallback) behaviour of the Python tools.

Run with pytest from the repo root:

    python -m pytest tests/test_native_platform.py

Nothing here talks to Fusion or runs the ``claude`` CLI: the bridge's network
calls, Fusion's file writes and the claude invocation are all faked.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import fusion_bridge as fb  # noqa: E402
import fusion_export as fx  # noqa: E402
import gen_context  # noqa: E402
import run_review  # noqa: E402


# ---------------------------------------------------------------------------
# Host selection
# ---------------------------------------------------------------------------

def _refuse(*_a, **_k):
    raise ConnectionRefusedError("refused")


def test_native_host_never_runs_ip_route(monkeypatch):
    monkeypatch.setattr(fb.socket, "create_connection", _refuse)
    monkeypatch.setattr(fb, "_default_gateway",
                        lambda: pytest.fail("gateway probed on a native platform"))
    for plat in ("windows", "macos"):
        assert fb._default_host(plat=plat) == "127.0.0.1"


def test_wsl_host_falls_back_to_gateway(monkeypatch):
    monkeypatch.setattr(fb.socket, "create_connection", _refuse)
    monkeypatch.setattr(fb, "_default_gateway", lambda: "172.20.0.1")
    assert fb._default_host(plat="wsl") == "172.20.0.1"
    monkeypatch.setattr(fb, "_default_gateway", lambda: None)
    assert fb._default_host(plat="wsl") == "127.0.0.1"


def test_gateway_lookup_without_ip_binary(monkeypatch):
    def missing(*_a, **_k):
        raise FileNotFoundError("ip")
    monkeypatch.setattr(fb.subprocess, "check_output", missing)
    assert fb._default_gateway() is None


def test_unreachable_fusion_raises_bridge_error_with_hint(monkeypatch):
    def down(*_a, **_k):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))
    monkeypatch.setattr(fb.urllib.request, "urlopen", down)
    bridge = fb.FusionBridge(host="127.0.0.1")
    with pytest.raises(fb.BridgeError) as exc:
        bridge.read_all("electronics.Sheet")
    assert "Fusion MCP Server" in str(exc.value)


def test_setup_hint_fits_platform():
    for plat in ("windows", "macos"):
        hint = fb._setup_hint(plat)
        assert "portproxy" not in hint and "check.sh" not in hint
        assert "127.0.0.1:27182" in hint
    assert "portproxy" in fb._setup_hint("wsl")
    if sys.platform == "win32":
        assert fb.host_platform() == "windows"


# ---------------------------------------------------------------------------
# Share directory and Fusion-side paths
# ---------------------------------------------------------------------------

def test_default_share_dir(monkeypatch):
    monkeypatch.setenv("PUBLIC", r"D:\Users\Public")
    assert fb.default_share_dir("windows") == r"D:\Users\Public\thomsonlint"
    monkeypatch.delenv("PUBLIC")
    assert fb.default_share_dir("windows") == r"C:\Users\Public\thomsonlint"
    monkeypatch.setenv("HOME", "/Users/me")
    assert fb.default_share_dir("macos") == "/Users/me/.thomsonlint"
    assert fb.default_share_dir("wsl") == "/mnt/c/Users/Public/thomsonlint"


def test_to_fusion_path():
    assert (fb.to_fusion_path("/mnt/c/Users/Public/thomsonlint/exports/x", "wsl")
            == "C:\\Users\\Public\\thomsonlint\\exports\\x")
    with pytest.raises(fb.BridgeError):
        fb.to_fusion_path("/home/me/share", "wsl")
    assert (fb.to_fusion_path("/Users/me/.thomsonlint/exports/x", "macos")
            == "/Users/me/.thomsonlint/exports/x")
    if sys.platform == "win32":
        assert (fb.to_fusion_path(r"C:\Users\Public\thomsonlint\exports\x", "windows")
                == r"C:\Users\Public\thomsonlint\exports\x")
    with pytest.raises(fb.BridgeError):
        fb.to_fusion_path("/Users/o'brien/share", "macos")


class FakeBridge:
    """Answers reads from canned rows; 'renders' EXPORT IMAGE targets locally."""

    def __init__(self, rows: dict[str, list[dict]], to_local):
        self.rows = rows
        self.to_local = to_local  # Fusion path -> local path
        self.commands: list[str] = []
        self.present_at_dispatch: list[bool] = []

    def read_all(self, entity, obj=None):
        return self.rows.get(entity, [])

    def execute_script(self, _src):
        return {"success": True}

    def run_eagle(self, command):
        if '"' in command:
            raise ValueError("double quote in EAGLE command")
        self.commands.append(command)
        for part in command.split("EXPORT IMAGE '")[1:]:
            local = self.to_local(part.split("'", 1)[0])
            self.present_at_dispatch.append(os.path.exists(local))
            Path(local).write_bytes(b"png")
        return {"success": True}


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows path check")
def test_image_commands_native_windows(tmp_path):
    share = tmp_path / "Share Dir" / "exports"
    share.mkdir(parents=True)
    prefix = str(share / "comet_sch")
    stale = Path(prefix + "-img-sch-p1.png")
    stale.write_bytes(b"old")
    rows = {
        "electronics.Sheet": [{"number": 1}],
        "electronics.Board": [{"name": "comet brd.brd"}],
        "electronics.Layer": [{"number": 1, "name": "Top", "used": True},
                              {"number": 16, "name": "Bottom", "used": False}],
    }
    bridge = FakeBridge(rows, to_local=lambda p: p.replace("/", "\\"))
    exp = fx.Exporter(bridge)

    out = exp.images_schematic(prefix, 300)
    assert out == [prefix + "-img-sch-p1.png"]
    fusion_prefix = prefix.replace("\\", "/")
    assert bridge.commands[-1] == (
        f"WINDOW FIT; EXPORT IMAGE '{fusion_prefix}-img-sch-p1.png' 300;")
    assert bridge.present_at_dispatch == [False]  # stale PNG pre-deleted

    out = exp.images_board(str(share / "comet_brd"), 1200)
    assert [Path(p).name for p in out] == [
        "comet_brd-img-silk-top.png", "comet_brd-img-silk-bot.png",
        "comet_brd-img-cu-L1-Top.png"]
    assert "\\" not in bridge.commands[-1]
    assert all(Path(p).exists() for p in out)


def test_stage_ulps_native(tmp_path, capsys):
    args = SimpleNamespace(dir=str(tmp_path / "share"))
    assert fb.cmd_stage_ulps(args) == 0
    cap = capsys.readouterr()
    tools = tmp_path / "share" / "tools"
    assert sorted(p.name for p in tools.glob("*.ulp")) == sorted(
        p.name for p in (REPO / "tools").glob("fusion-electronics-*.ulp"))
    assert (tmp_path / "share" / "exports").is_dir()
    if sys.platform == "win32":
        assert cap.out.strip() == str(tools)
        assert "Copy-Item" in cap.err
    assert "cp " in fb._copy_back_hint(Path("/Users/me/.thomsonlint/exports"), "macos")


# ---------------------------------------------------------------------------
# validate_json.py / gen_context.py
# ---------------------------------------------------------------------------

def _copy_repo_subset(dst: Path) -> None:
    for rel in ("validate_json.py", "ontology/ontology.json", "examples/examples.json",
                "tests/ontology_schema.json", "tests/examples_schema.json",
                "tests/findings_schema.json", "tests/sample_findings.json",
                "tools/gen_report.py", "tools/gen_context.py", "tools/run_review.py",
                "docs/REVIEWER_INSTRUCTIONS.md",
                "docs/AI_Hardware_Design_Review_KnowledgeBase.md"):
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, dst / rel)
    (dst / "exports").mkdir()


def _validate(cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    return subprocess.run([sys.executable, "validate_json.py"], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def test_validate_json_exit_codes(tmp_path):
    _copy_repo_subset(tmp_path)
    ok = _validate(tmp_path)
    assert ok.returncode == 0, ok.stdout + ok.stderr

    onto = tmp_path / "ontology" / "ontology.json"
    doc = json.loads(onto.read_text(encoding="utf-8"))
    doc.pop(next(iter(doc)))  # drop a required top-level key
    onto.write_text(json.dumps(doc), encoding="utf-8")
    bad = _validate(tmp_path)
    assert bad.returncode != 0 and "failed validation" in bad.stdout
    assert "Traceback" not in bad.stderr

    onto.write_text("{ not json", encoding="utf-8")
    assert _validate(tmp_path).returncode != 0


def test_gen_context_matches_committed_bundle():
    assert gen_context.build_bundle() == (REPO / "review_instructions.txt").read_bytes()


# ---------------------------------------------------------------------------
# run_review.py (everything except the real claude call)
# ---------------------------------------------------------------------------

def test_find_claude_rejects_batch_shim(monkeypatch):
    monkeypatch.setattr(run_review.shutil, "which", lambda _n: None)
    with pytest.raises(run_review.PipelineError, match="Missing command 'claude'"):
        run_review.find_claude()
    if os.name == "nt":
        monkeypatch.setattr(run_review.shutil, "which",
                            lambda _n: r"C:\npm\claude.CMD")
        with pytest.raises(run_review.PipelineError, match="batch shim"):
            run_review.find_claude()


def test_summarize_mirrors_jq():
    assert run_review.summarize('{"result": "hi"}')[0] == "hi"
    assert run_review.summarize('{"result": "", "x": 1}')[0] == ""
    assert run_review.summarize('{"result": null, "x": 1}')[0] == '{"result":null,"x":1}'
    assert run_review.summarize('{"structured_output": {"a": 1}}')[1] == {"a": 1}


def _run_pipeline(tmp_path, monkeypatch, envelope: dict, rc: int = 0,
                  argv=None, write_findings: bool = False):
    _copy_repo_subset(tmp_path)
    (tmp_path / "exports" / "demo-thomson-export-sch.json").write_text("{}", encoding="utf-8")
    (tmp_path / "exports" / "demo-thomson-export-brd.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(run_review, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_review, "find_claude", lambda: "claude-fake")
    monkeypatch.delenv("THOMSONLINT_MODEL", raising=False)
    monkeypatch.delenv("THOMSONLINT_BUDGET", raising=False)
    calls = []

    def runner(cmd, cwd, stdout):
        calls.append(cmd)
        stdout.write(json.dumps(envelope).encode("utf-8"))
        if write_findings:
            (tmp_path / "exports" / "demo-findings.json").write_text(
                json.dumps(envelope["structured_output"]), encoding="utf-8")
        return SimpleNamespace(returncode=rc)

    cwd = os.getcwd()
    try:
        result = run_review.main(argv or [], runner=runner)
    finally:
        os.chdir(cwd)
    return result, calls


def _sample_findings(project="demo"):
    doc = json.loads((REPO / "tests" / "sample_findings.json").read_text(encoding="utf-8"))
    doc["project_name"] = project
    return doc


def test_run_review_pipeline(tmp_path, monkeypatch, capsys):
    envelope = {"result": "Review done \u2713", "structured_output": _sample_findings()}
    rc, calls = _run_pipeline(tmp_path, monkeypatch, envelope)
    out = capsys.readouterr().out
    assert rc == 0, out
    cmd = calls[0]
    assert cmd[:3] == ["claude-fake", "--print", run_review.build_prompt(
        "demo", cmd[2].rsplit("review_date to '", 1)[1][:10])]
    def flag(name):
        return cmd[cmd.index(name) + 1]
    flags = {f: flag(f) for f in ("--allowedTools", "--model", "--output-format",
                                  "--json-schema", "--max-budget-usd")}
    assert flags["--allowedTools"] == run_review.ALLOWED_TOOLS
    assert flags["--model"] == "claude-opus-4-7"
    assert flags["--output-format"] == "json"
    assert json.loads(flags["--json-schema"]) == json.loads(
        (REPO / "tests" / "findings_schema.json").read_text(encoding="utf-8"))
    assert flags["--max-budget-usd"] == "3"
    assert "--no-session-persistence" in cmd
    assert "Review done" in out
    # Findings recovered from structured_output, validated, report rendered.
    findings = json.loads((tmp_path / "exports" / "demo-findings.json")
                          .read_text(encoding="utf-8"))
    assert findings["project_name"] == "demo"
    assert (tmp_path / "exports" / "demo-review.html").is_file()
    assert ((tmp_path / "review_instructions.txt").read_bytes()
            == (REPO / "review_instructions.txt").read_bytes())


def test_run_review_stops_on_invalid_findings(tmp_path, monkeypatch, capsys):
    bad = _sample_findings()
    del bad["issues"]
    envelope = {"result": "x", "structured_output": bad}
    with pytest.raises(SystemExit) as exc:
        _run_pipeline(tmp_path, monkeypatch, envelope)
    assert exc.value.code != 0
    assert not (tmp_path / "exports" / "demo-review.html").exists()


def test_run_review_claude_failure_and_detection(tmp_path, monkeypatch, capsys):
    rc, _ = _run_pipeline(tmp_path, monkeypatch, {"result": "x"}, rc=7)
    assert rc == 7
    rc, calls = _run_pipeline(tmp_path / "b", monkeypatch, {}, argv=["nope"])
    assert rc == 1 and not calls
    assert "Schematic not found: exports/nope-thomson-export-sch.json" in capsys.readouterr().out
