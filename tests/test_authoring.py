from __future__ import annotations

import json
from pathlib import Path

from mathpub.cli import main


def invoke(monkeypatch, capsys, root: Path, arguments: list[str]):
    monkeypatch.chdir(root)
    code = main([*arguments, "--json"])
    output = capsys.readouterr()
    return code, json.loads(output.out)


def test_init_and_agent_instructions(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    code = main(["init", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "ok"
    assert (project / "mathpub.toml").is_file()
    instructions = (project / "AGENTS.md").read_text()
    assert "never edit `build/`" in instructions

    code, payload = invoke(
        monkeypatch,
        capsys,
        project,
        ["new", "question", "physics.energy.ramp", "--kind", "numeric"],
    )
    assert code == 0
    assert payload["data"]["id"] == "physics.energy.ramp"
    question = project / "questions/physics/energy/ramp"
    assert {path.name for path in question.iterdir()} == {
        "question.toml",
        "generate.sage",
        "prompt.tex",
        "answer.tex",
        "solution.tex",
    }

    code, payload = invoke(
        monkeypatch, capsys, project, ["check", "question", "physics.energy.ramp"]
    )
    assert code == 0
    assert len(payload["data"]["checked"]) == 4


def test_discovery_is_structured_and_relative(tmp_path, monkeypatch, capsys):
    project = tmp_path / "course"
    assert main(["init", str(project)]) == 0
    capsys.readouterr()
    monkeypatch.chdir(project)
    assert main(["new", "question", "physics.fixed", "--kind", "fixed"]) == 0
    capsys.readouterr()
    code, payload = invoke(monkeypatch, capsys, project, ["list", "questions"])
    assert code == 0
    assert payload["schema"] == 1
    assert payload["data"][0]["path"] == "questions/physics/fixed"


def test_invalid_project_returns_stable_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["list", "questions", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["error"]["code"] == "MP-SRC-004"
