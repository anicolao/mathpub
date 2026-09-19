import json

import pytest

from mathpub.config import find_project
from mathpub.errors import MathpubError
from mathpub.instance import instance_hash
from mathpub.layout_tools import compare_invariants, specimen
from mathpub.scaffold import init_project, new_component


def manifest(tmp_path, name, placements):
    folder = tmp_path / name
    folder.mkdir()
    entries = []
    for placement, parameter in placements.items():
        instance = {"parameters": {"answer": parameter}, "derived": {}, "display": {"color": name}}
        instance["sha256"] = instance_hash(instance)
        (folder / f"{placement}.json").write_text(json.dumps(instance))
        entries.append(
            {
                "placement": placement,
                "id": "same-component",
                "instance": f"{placement}.json",
                "sha256": instance["sha256"],
            }
        )
    path = folder / "manifest.json"
    path.write_text(json.dumps({"components": entries}))
    return path


def test_layout_changes_may_change_display_but_cannot_swap_answers(tmp_path):
    before = manifest(tmp_path, "before", {"one": 1, "two": 2})
    same = manifest(tmp_path, "same", {"one": 1, "two": 2})
    assert compare_invariants(before, same)["passed"]
    swapped = manifest(tmp_path, "swapped", {"one": 2, "two": 1})
    with pytest.raises(MathpubError, match="invariant changed"):
        compare_invariants(before, swapped)


def test_library_evidence_is_bound_to_manifests_and_placements(tmp_path):
    before = manifest(tmp_path, "before", {"one": 1})
    after = manifest(tmp_path, "after", {"one": 1})
    report = compare_invariants(before, after)
    evidence = {
        key: report[key] for key in ("schema", "before_manifest_sha256", "after_manifest_sha256")
    }
    evidence["checks"] = [
        {
            "id": "diagram-size",
            "placement": "one",
            "passed": False,
            "note": "Measured diagram was too small.",
            "measured": 20,
            "expected": 30,
        }
    ]
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence))
    with pytest.raises(MathpubError, match="invariant changed"):
        compare_invariants(before, after, [path])
    evidence["before_manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(evidence))
    with pytest.raises(MathpubError, match="stale"):
        compare_invariants(before, after, [path])


def test_specimens_use_normal_renderer_and_source_mapped_inventory(tmp_path):
    root = tmp_path / "library"
    init_project(root)
    project = find_project(root)
    new_component(
        project,
        "example.figure",
        "example",
        title="A synthetic example",
        concepts=["synthetic.concept"],
    )
    result = specimen(
        project,
        "example.specimen",
        ["example.figure"],
        root / "publications/specimen.toml",
        style="anna",
        seed="2026",
    )
    assert result["root_seed"] == "2026"
    assert result["physical_inventory"]
