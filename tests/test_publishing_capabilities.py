import json
import shlex

import pytest

from mathpub.capabilities import capability_data, framework_guide
from mathpub.cli import main, parser
from mathpub.config import find_project
from mathpub.publishing_capabilities import WORKFLOWS, publishing_manual
from mathpub.scaffold import init_project


def test_startup_and_json_share_all_publishing_workflows(tmp_path):
    init_project(tmp_path / "library")
    project = find_project(tmp_path / "library")
    guide = framework_guide(project)
    data = capability_data(project)["publishing"]
    assert len(data["workflows"]) == 9
    assert data["policy"] in guide
    assert data["print_goal"] in guide
    assert "print-ready PDFs for KDP" in data["print_goal"]
    assert len(data["print_pipeline"]) == 6
    for step in data["print_pipeline"]:
        assert step in guide
    cover = next(w for w in data["workflows"] if w["topic"] == "cover")
    assert "back cover + spine + front cover" in cover["requirements_and_boundaries"]
    assert "NOT an interior title page" in cover["requirements_and_boundaries"]
    assert "exact interior PDF hash" in cover["requirements_and_boundaries"]
    for workflow in data["workflows"]:
        assert workflow["when"] in guide
        assert workflow["requirements_and_boundaries"] in guide
        assert workflow["manual_command"] in guide
        for example in workflow["examples"]:
            assert example in guide
            parser().parse_args(shlex.split(example.split(" -- ", 1)[1]))
    assert "explicit upload authorization" in guide
    assert "do not run builds, audits or retailer sessions merely to orient yourself" in guide
    assert "--retry-uncertain requires explicit authorization" in guide


@pytest.mark.parametrize("topic", [row[0] for row in WORKFLOWS])
def test_topic_manual_available_from_an_authoring_library(topic, tmp_path, monkeypatch, capsys):
    init_project(tmp_path / "library")
    monkeypatch.chdir(tmp_path / "library")
    manual = publishing_manual(topic)
    assert manual.startswith("# ")
    assert main(["capabilities", "--topic", topic]) == 0
    assert manual.strip() in capsys.readouterr().out
    assert main(["agent-guide", "--topic", topic, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"] == {"topic": topic, "manual": manual}


def test_plain_startup_command_exposes_delivery_workflows(capsys):
    assert main(["capabilities"]) == 0
    output = capsys.readouterr().out
    assert "Publishing and delivery tools" in output
    assert "capabilities --topic kdp" in output
    assert main(["capabilities", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert len(data["publishing"]["workflows"]) == 9
