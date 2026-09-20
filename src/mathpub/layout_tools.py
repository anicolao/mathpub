"""Placement-preserving layout evidence and production-rendered specimens."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from mathpub.catalog import Catalog
from mathpub.config import ID_PATTERN, Project, schema_definition
from mathpub.errors import MathpubError
from mathpub.instance import instance_hash
from mathpub.releases import inside, sha256


def _instances(path: Path):
    data = path.read_bytes()
    manifest = json.loads(data)
    result = {}
    for collection in ("components", "questions"):
        for index, entry in enumerate(manifest.get(collection, [])):
            placement = entry.get("placement", f"question.{index}.{entry['id']}")
            if placement in result:
                raise ValueError("duplicate placement in manifest")
            instance_path = inside(path.parent, entry["instance"])
            instance = json.loads(instance_path.read_text())
            actual = instance_hash(
                {key: value for key, value in instance.items() if key != "sha256"}
            )
            if actual != entry["sha256"] or actual != instance["sha256"]:
                raise ValueError(f"instance hash mismatch at {placement}")
            result[placement] = {
                "id": entry["id"],
                "source": str(instance_path),
                "canonical": {key: instance.get(key, {}) for key in ("parameters", "derived")},
            }
    return sha256(data), result


def compare_invariants(before: Path, after: Path, evidence: list[Path] | None = None) -> dict:
    try:
        before_hash, a = _instances(before)
        after_hash, b = _instances(after)
        checks = []
        for placement in sorted(set(a) | set(b)):
            previous, current = a.get(placement), b.get(placement)
            passed = (
                previous is not None
                and current is not None
                and previous["id"] == current["id"]
                and previous["canonical"] == current["canonical"]
            )
            checks.append(
                {
                    "id": "canonical-instance",
                    "placement": placement,
                    "passed": passed,
                    "before": previous,
                    "after": current,
                    "note": "Canonical values must remain attached to the same placement.",
                }
            )
        for path in evidence or []:
            report = json.loads(path.read_text())
            jsonschema.validate(report, schema_definition("invariant-report"))
            if (
                report["before_manifest_sha256"] != before_hash
                or report["after_manifest_sha256"] != after_hash
            ):
                raise ValueError(
                    "library invariant report is stale or refers to different editions"
                )
            for check in report["checks"]:
                if check["placement"] not in set(a) | set(b):
                    raise ValueError("library invariant references an unknown placement")
            checks.extend(report["checks"])
        result = {
            "schema": 1,
            "before_manifest_sha256": before_hash,
            "after_manifest_sha256": after_hash,
            "checks": checks,
            "passed": all(check["passed"] for check in checks),
            "limitations": [
                "Display changes are permitted; domain equivalence needs library checks.",
                "Computational checks are evidence, not formal proofs.",
            ],
        }
        if not result["passed"]:
            raise MathpubError(
                "MP-INVARIANT-002", "layout invariant changed", details={"report": result}
            )
        return result
    except (OSError, ValueError, KeyError, TypeError, jsonschema.ValidationError) as error:
        raise MathpubError("MP-INVARIANT-001", f"invalid invariant evidence: {error}") from error


def specimen(
    project: Project,
    identifier: str,
    components: list[str],
    output: Path,
    *,
    style: str = "mathpub",
    projection: str = "student",
    seed: str = "2026",
) -> dict:
    from mathpub.gui.synctex import spatial_index
    from mathpub.publish import build

    if (
        not ID_PATTERN.fullmatch(identifier)
        or not components
        or len(set(components)) != len(components)
    ):
        raise MathpubError("MP-SPECIMEN-001", "specimen needs a valid ID and distinct components")
    output = output if output.is_absolute() else project.root / output
    if not output.resolve().is_relative_to(project.root.resolve()):
        raise MathpubError("MP-SPECIMEN-001", "specimen descriptor must stay inside the project")
    catalog = Catalog(project)
    entries = [catalog.get("component", name) for name in components]
    # A normal source descriptor, not a second renderer or a scaled screenshot sheet.
    lines = [
        "schema = 1",
        f"id = {json.dumps(identifier)}",
        'kind = "textbook"',
        'title = "Component Specimens"',
        'profile = "mathpub.exam"',
        f"style = {json.dumps(style)}",
        f"projections = [{json.dumps(projection)}]",
        "[[component_chapters]]",
        'id = "specimens"',
        'title = "Component Specimens"',
        "[[component_chapters.lessons]]",
        'id = "specimens"',
        'title = "Component Specimens"',
        'concepts = ["specimens"]',
    ]
    for index, entry in enumerate(entries, 1):
        lines.extend(
            [
                "[[component_chapters.lessons.blocks]]",
                f"include = {json.dumps(entry.metadata['id'])}",
                f"placement = {json.dumps(f'specimen.{index}.{entry.metadata["id"]}')}",
                "page_break_before = true",
            ]
        )
    try:
        with output.open("x") as source:
            source.write("\n".join(lines) + "\n")
        result = build(
            project, output, root_seed=seed, variant="specimen", projections=[projection]
        )
        pages = next(
            item["pages"] for item in result["outputs"] if item["projection"] == projection
        )
        inventory = [
            spatial_index(
                project.root,
                identifier,
                "specimen",
                projection,
                page,
                build_dir=project.config.get("build_dir", "build"),
            )
            for page in range(1, pages + 1)
        ]
        return {
            "build": result,
            "source": str(output),
            "root_seed": seed,
            "physical_inventory": inventory,
            "note": "Production rendering without scaling; print at actual size, not fit-to-page.",
        }
    except (OSError, ValueError) as error:
        raise MathpubError("MP-SPECIMEN-001", f"cannot create specimen: {error}") from error
