from __future__ import annotations

from pathlib import Path

from mathpub.catalog import Catalog
from mathpub.config import find_project
from mathpub.instance import instantiate
from mathpub.render import expand


def _example(identifier: str):
    project = find_project(Path(__file__).resolve())
    entry = Catalog(project).get("question", identifier)
    instance = instantiate(entry, "2026", "validation-test")
    prompt = expand((entry.path / entry.metadata["prompt"]).read_text(), instance, identifier)
    return instance, prompt


def test_k_rampy_checks_physics_and_scale_geometry():
    instance, prompt = _example("physics.energy.k-rampy")
    checks = {check["id"]: check for check in instance["checks"]}
    assert checks.keys() >= {
        "energy-conservation",
        "diagram-length-scale",
        "diagram-angle",
    }
    assert all(check["status"] == "passed" for check in checks.values())
    assert "end angle=" + instance["display"]["angle_number"]["tex"] in prompt
    assert instance["display"]["diagram_run"]["tex"] in prompt
    assert instance["display"]["diagram_rise"]["tex"] in prompt
    assert "Diagram to scale" in prompt
    assert "\\mpvalue" not in prompt


def test_snowball_checks_trajectory_and_scale_geometry():
    instance, prompt = _example("physics.projectiles.snowball")
    checks = {check["id"]: check for check in instance["checks"]}
    assert checks.keys() >= {
        "trajectory-lands-on-ground",
        "horizontal-motion",
        "diagram-launch-angle",
        "diagram-impact-scale",
    }
    assert all(check["status"] == "passed" for check in checks.values())
    assert "end angle=-" + instance["display"]["roof_angle_number"]["tex"] in prompt
    assert instance["display"]["trajectory_coordinates"]["tex"] in prompt
    assert instance["display"]["impact_x"]["tex"] in prompt
    assert "in both axes" in prompt
    assert "\\mpvalue" not in prompt
