"""Command-line bridge (--list-tools / --call) used by assistants that run commands instead of MCP."""

from __future__ import annotations

import json

import pytest

from nms_direct_link import server


def _run(capsys, *argv):
    with pytest.raises(SystemExit) as exc:
        server.main(list(argv))
    out = capsys.readouterr()
    return exc.value.code, out.out, out.err


def test_list_tools(capsys):
    code, out, _ = _run(capsys, "--list-tools")
    assert code == 0 and "nms_get_player_state" in out and len(out.strip().splitlines()) == 37


def test_call_tool_json_and_short_name(capsys, env_save_dir):
    server.store._snapshot = None
    server.store._snapshot_key = None
    code, out, _ = _run(capsys, "--call", "get_player_state", "--args", '{"response_format": "json"}')
    assert code == 0 and json.loads(out)["currencies"]["nanites"] == 250
    code, out, _ = _run(capsys, "--call", "nms_plan_nanites", "--args", '{"target": 5000}')
    assert code == 0 and "gap 4,750" in out


def test_call_errors(capsys):
    code, _, err = _run(capsys, "--call", "nope")
    assert code == 2 and "unknown tool" in err
    code, _, err = _run(capsys, "--call", "explain", "--args", "{bad")
    assert code == 2 and "not valid JSON" in err
    code, out, err = _run(capsys, "--call", "explain", "--args", '{"bogus": 1}')
    assert code == 2 and err.startswith("Error: invalid parameters for nms_explain") and len(err) < 400 and out == ""
