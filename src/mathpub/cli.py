"""Command-line entry point for mathpub."""

from __future__ import annotations

import argparse
import itertools
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from mathpub import __version__
from mathpub.catalog import Catalog
from mathpub.config import find_project, load_toml, relative, schema_enum
from mathpub.errors import MathpubError
from mathpub.instance import instantiate, instantiate_component
from mathpub.output import emit
from mathpub.publish import build, reproduce
from mathpub.render import validate_fragment_source
from mathpub.scaffold import (
    COLLECTIONS,
    QUESTION_TEMPLATES,
    init_project,
    new_component,
    new_question,
)


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="as_json")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="mathpub", description=__doc__)
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = result.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a complete mathpub project")
    init.add_argument("directory", nargs="?", type=Path, default=Path.cwd())
    _json_flag(init)

    new = commands.add_parser("new", help="create authored source")
    new_types = new.add_subparsers(dest="new_type", required=True)
    question = new_types.add_parser("question")
    question.add_argument("identifier")
    question.add_argument("--concept", action="append", required=True, dest="concepts")
    question.add_argument("--template", choices=QUESTION_TEMPLATES, default="fixed")
    question.add_argument("--title")
    _json_flag(question)

    component = new_types.add_parser("component")
    component.add_argument("identifier")
    component.add_argument("--kind", choices=tuple(COLLECTIONS), required=True)
    component.add_argument("--concept", action="append", default=[], dest="concepts")
    component.add_argument("--template", choices=QUESTION_TEMPLATES, default="fixed")
    component.add_argument("--form", choices=("cohesive", "structured"), default="cohesive")
    component.add_argument("--title")
    _json_flag(component)

    list_parser = commands.add_parser("list", help="discover project content")
    list_parser.add_argument(
        "content", choices=("questions", "components", "publications", "profiles")
    )
    list_parser.add_argument("--kind", choices=schema_enum("component", "kind"))
    _json_flag(list_parser)

    show = commands.add_parser("show", help="inspect a catalog entry")
    show.add_argument("content", choices=("question", "component", "publication", "profile"))
    show.add_argument("identifier")
    _json_flag(show)

    inspect = commands.add_parser("inspect", help="inspect source or generated metadata")
    inspect.add_argument("content", choices=("publication", "manifest"))
    inspect.add_argument("path", type=Path)
    _json_flag(inspect)

    check = commands.add_parser("check", help="validate authored source")
    check.add_argument("content", choices=("project", "question", "component", "publication"))
    check.add_argument("target", nargs="?")
    check.add_argument("--seeds", type=int)
    check.add_argument("--exhaustive", action="store_true")
    _json_flag(check)

    preview = commands.add_parser("preview", help="render one question component in isolation")
    preview.add_argument("identifier")
    preview.add_argument("--seed", required=True)
    preview.add_argument(
        "--projection",
        action="append",
        choices=("student", "answers", "solutions", "validation"),
        help="projection to render; omit to render all four",
    )
    preview.add_argument("--style", choices=("mathpub", "workbook"), default="mathpub")
    preview.add_argument(
        "--font", choices=("concrete", "libertinus", "computer-modern"), default=None
    )
    preview.add_argument("--replace", action="store_true")
    _json_flag(preview)

    build_parser = commands.add_parser("build", help="build a publication edition")
    build_parser.add_argument("publication", type=Path)
    build_parser.add_argument("--seed", required=True)
    build_parser.add_argument("--variant", default="A")
    build_parser.add_argument(
        "--font", choices=("concrete", "libertinus", "computer-modern"), default=None
    )
    build_parser.add_argument(
        "--projection",
        action="append",
        choices=("student", "answers", "solutions", "validation", "parent"),
    )
    build_parser.add_argument("--replace", action="store_true")
    build_parser.add_argument("--require-clean", action="store_true")
    _json_flag(build_parser)

    variants = commands.add_parser("variants", help="build named variants")
    variants.add_argument("publication", type=Path)
    variants.add_argument("--seed", required=True)
    variants.add_argument("--count", required=True, type=int)
    variants.add_argument("--replace", action="store_true")
    variants.add_argument(
        "--font", choices=("concrete", "libertinus", "computer-modern"), default=None
    )
    _json_flag(variants)

    reproduce_parser = commands.add_parser("reproduce", help="rebuild from stored instances")
    reproduce_parser.add_argument("manifest", type=Path)
    reproduce_parser.add_argument("--replace", action="store_true")
    reproduce_parser.add_argument("--allow-different-toolchain", action="store_true")
    _json_flag(reproduce_parser)

    clean = commands.add_parser("clean", help="remove generated build output")
    clean.add_argument("--edition")
    _json_flag(clean)
    return result


def _entry_data(project, entry):
    result = entry.summary(project)
    result["metadata"] = entry.metadata
    return result


def _validate_files(project, entry) -> list[str]:
    checked: list[str] = []
    if entry.kind in {"question", "component"}:
        sources = (
            {key: entry.metadata.get(key) for key in ("prompt", "answer", "solution", "generator")}
            if entry.kind == "question"
            else {
                **entry.metadata.get("fragments", {}),
                "generator": entry.metadata.get("generator"),
            }
        )
        for key, filename in sources.items():
            if filename:
                path = entry.path / filename
                if not path.is_file():
                    raise MathpubError(
                        "MP-SRC-012", f"missing {key} for {entry.metadata['id']}: {path}"
                    )
                checked.append(relative(project, path))
                source = path.read_text(encoding="utf-8")
                if key != "generator":
                    mode = entry.metadata.get("fragment_modes", {}).get(key, "mixed-tex")
                    validate_fragment_source(source, mode, path)
                    forbidden = re.search(
                        r"\\(?:documentclass|begin\s*\{document\}|end\s*\{document\}|include|input|openin|openout)",
                        source,
                    )
                    if forbidden:
                        raise MathpubError(
                            "MP-TEX-008",
                            "forbidden TeX command in "
                            f"{relative(project, path)}: {forbidden.group()}",
                        )
                if key == "generator" and re.search(
                    r"(?<!ctx\.)\brandom\.|\b(?:numpy|np)\.random|\bset_random_seed\s*\(",
                    source,
                ):
                    raise MathpubError(
                        "MP-GEN-006",
                        f"use ctx.random or ctx.domain in {relative(project, path)}",
                    )
    return checked


def _variant_label(index: int) -> str:
    label = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def _require_clean(project) -> None:
    process = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project.root,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode or process.stdout.strip():
        raise MathpubError("MP-BUILD-003", "release build requires a clean Git tree", exit_code=3)


def run(args: argparse.Namespace) -> tuple[str, object]:
    if args.command == "init":
        return "init", init_project(args.directory)

    project = find_project()
    if args.command == "new":
        if args.new_type == "question":
            return "new question", new_question(
                project,
                args.identifier,
                args.template,
                args.concepts,
                title=args.title,
            )
        return "new component", new_component(
            project,
            args.identifier,
            args.kind,
            concepts=args.concepts,
            title=args.title,
            template=args.template,
            form=args.form,
        )

    catalog = Catalog(project)
    if args.command == "clean":
        build_root = project.root / project.config.get("build_dir", "build")
        target = build_root / args.edition if args.edition else build_root
        try:
            target.resolve().relative_to(build_root.resolve())
        except ValueError as error:
            raise MathpubError(
                "MP-SRC-005", f"edition escapes build directory: {target}"
            ) from error
        existed = target.exists()
        if existed:
            shutil.rmtree(target)
        return "clean", {"path": relative(project, target), "removed": existed}
    if args.command == "preview":
        entry = catalog.get("component", args.identifier)
        if entry.metadata.get("kind") != "question" and entry.kind != "question":
            raise MathpubError("MP-SRC-014", f"component is not a question: {args.identifier}")
        projections = args.projection or ["student", "answers", "solutions", "validation"]
        placement = "preview.question"
        preview_dir = project.root / project.config.get("build_dir", "build") / ".previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        source = preview_dir / f"{args.identifier}.toml"
        font = f"\nfont = {json.dumps(args.font)}" if args.font else ""
        source.write_text(
            f"""schema = 1
id = "preview.{args.identifier}"
kind = "textbook"
title = {json.dumps(f"Preview: {entry.metadata['title']}")}
profile = "mathpub.exam"
style = {json.dumps(args.style)}{font}
projections = {json.dumps(projections)}
[[component_chapters]]
id = "preview"
title = "Preview"
[[component_chapters.lessons]]
id = "question"
title = {json.dumps(entry.metadata["title"])}
concepts = [{json.dumps(args.identifier)}]
[[component_chapters.lessons.blocks]]
[component_chapters.lessons.blocks.problem_set]
id = "preview"
title = {json.dumps(entry.metadata["title"])}
show_title = false
[[component_chapters.lessons.blocks.problem_set.questions]]
id = {json.dumps(args.identifier)}
placement = {json.dumps(placement)}
""",
            encoding="utf-8",
        )
        result = build(
            project,
            source,
            root_seed=args.seed,
            variant="preview",
            replace=args.replace,
        )
        return "preview", {
            **result,
            "question": {
                "id": args.identifier,
                "source_model": "component" if entry.kind == "component" else "question",
                "placement": placement,
            },
        }
    if args.command == "build":
        if args.require_clean:
            _require_clean(project)
        return "build", build(
            project,
            args.publication,
            root_seed=args.seed,
            variant=args.variant,
            projections=args.projection,
            font_family=args.font,
            replace=args.replace,
        )
    if args.command == "variants":
        if args.count < 1:
            raise MathpubError("MP-CLI-003", "variant count must be positive", exit_code=2)
        editions = []
        for index in range(args.count):
            label = _variant_label(index)
            editions.append(
                build(
                    project,
                    args.publication,
                    root_seed=args.seed,
                    variant=label,
                    font_family=args.font,
                    replace=args.replace,
                )
            )
        return "variants", editions
    if args.command == "reproduce":
        path = args.manifest if args.manifest.is_absolute() else project.root / args.manifest
        return "reproduce", reproduce(
            project,
            path,
            replace=args.replace,
            allow_different_toolchain=args.allow_different_toolchain,
        )
    if args.command == "list":
        data = [entry.summary(project) for entry in catalog.entries(args.content).values()]
        if args.kind:
            if args.content != "components":
                raise MathpubError("MP-CLI-004", "--kind is only valid with list components")
            data = [entry for entry in data if entry["kind"] == args.kind]
        return f"list {args.content}", data
    if args.command == "show":
        entry = catalog.get(args.content, args.identifier)
        return f"show {args.content}", _entry_data(project, entry)
    if args.command == "inspect":
        path = args.path if args.path.is_absolute() else project.root / args.path
        if args.content == "manifest":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise MathpubError("MP-SRC-013", f"invalid manifest {path}: {error}") from error
        else:
            data = load_toml(path, "publication")
        return f"inspect {args.content}", {"path": relative(project, path), "metadata": data}
    if args.command == "check":
        if args.content in {"question", "component"}:
            if not args.target:
                raise MathpubError(
                    "MP-CLI-001", f"check {args.content} requires an ID", exit_code=2
                )
            entry = catalog.get(args.content, args.target)
            checked = _validate_files(project, entry)
            if args.exhaustive and args.content == "question":
                domains = entry.metadata.get("testing", {}).get("exhaustive_domains", [])
                if not domains:
                    raise MathpubError(
                        "MP-GEN-007", f"no finite exhaustive domain declared for {args.target}"
                    )
                reports = []
                for domain in domains:
                    parameters = domain["parameters"]
                    names = sorted(parameters)
                    instances = []
                    for values in itertools.product(*(parameters[name] for name in names)):
                        overrides = dict(zip(names, values, strict=True))
                        instances.append(
                            instantiate(entry, "exhaustive", domain["name"], overrides=overrides)
                        )
                    reports.append(
                        {
                            "name": domain["name"],
                            "evidence": "exhaustive-check",
                            "total": len(instances),
                            "accepted": len(instances),
                            "rejected": 0,
                            "instance_hashes": [item["sha256"] for item in instances],
                        }
                    )
                return "check question", {
                    "id": args.target,
                    "checked": checked,
                    "verification": reports,
                }
            seeds = args.seeds or 1
            instances = []
            for seed in range(seeds):
                if args.content == "component":
                    first = instantiate_component(entry, str(seed), "check", "check")
                    second = instantiate_component(entry, str(seed), "check", "check")
                else:
                    first = instantiate(entry, str(seed), "check")
                    second = instantiate(entry, str(seed), "check")
                if first != second:
                    raise MathpubError(
                        "MP-GEN-005", f"non-deterministic generator: {args.target}", exit_code=5
                    )
                instances.append(first)
            return f"check {args.content}", {
                "id": args.target,
                "checked": checked,
                "verification": "sampled-property-test",
                "instances": [
                    {"sha256": instance["sha256"], "checks": instance["checks"]}
                    for instance in instances
                ],
            }
        if args.content == "publication":
            if not args.target:
                raise MathpubError("MP-CLI-002", "check publication requires a path", exit_code=2)
            path = Path(args.target)
            path = path if path.is_absolute() else project.root / path
            publication = load_toml(path, "publication")
            for section in publication.get("sections", []):
                for question in section["questions"]:
                    catalog.get("question", question["id"])
            for chapter in publication.get("chapters", []):
                for lesson in chapter["lessons"]:
                    for key in (
                        "content",
                        "exercises",
                        "self_assessment",
                        "answers",
                        "solutions",
                        "validation",
                    ):
                        if source := lesson.get(key):
                            lesson_path = (path.parent / source).resolve()
                            try:
                                lesson_path.relative_to(project.root)
                            except ValueError as error:
                                raise MathpubError(
                                    "MP-SRC-005", f"lesson source escapes project root: {source}"
                                ) from error
                            if not lesson_path.is_file():
                                raise MathpubError(
                                    "MP-SRC-012", f"missing lesson source: {lesson_path}"
                                )
                if practice := chapter.get("practice"):
                    for key in (
                        "exercises",
                        "self_assessment",
                        "answers",
                        "solutions",
                        "validation",
                    ):
                        if source := practice.get(key):
                            practice_path = (path.parent / source).resolve()
                            try:
                                practice_path.relative_to(project.root)
                            except ValueError as error:
                                raise MathpubError(
                                    "MP-SRC-005",
                                    f"unit-practice source escapes project root: {source}",
                                ) from error
                            if not practice_path.is_file():
                                raise MathpubError(
                                    "MP-SRC-012",
                                    f"missing unit-practice source: {practice_path}",
                                )
            placements: set[str] = set()
            for chapter in publication.get("component_chapters", []):
                for lesson in chapter["lessons"]:
                    for component_id in (
                        *lesson["concepts"],
                        *lesson.get("objectives", []),
                    ):
                        catalog.get("component", component_id)
                    for block in lesson["blocks"]:
                        references = []
                        if component_id := block.get("include"):
                            references.append((component_id, block["placement"]))
                        problem_set = block.get("problem_set", {})
                        problem_parts = problem_set.get("parts") or [problem_set]
                        references.extend(
                            (question["id"], question["placement"])
                            for part in problem_parts
                            for question in part.get("questions", [])
                        )
                        for component_id, placement in references:
                            catalog.get("component", component_id)
                            if placement in placements:
                                raise MathpubError(
                                    "MP-SRC-013", f"duplicate component placement: {placement}"
                                )
                            placements.add(placement)
            return "check publication", {"id": publication["id"], "path": relative(project, path)}
        for entry in catalog.questions.values():
            _validate_files(project, entry)
        for entry in catalog.components.values():
            _validate_files(project, entry)
        return "check project", {
            "project": project.config["project"],
            "questions": len(catalog.questions),
            "components": len(catalog.components),
            "publications": len(catalog.publications),
            "profiles": len(catalog.profiles),
        }
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        command, data = run(arguments)
        emit(command, data, as_json=arguments.as_json)
        return 0
    except MathpubError as error:
        if getattr(arguments, "as_json", False):
            error_payload = {"code": error.code, "message": error.message}
            if error.details:
                error_payload["details"] = error.details
            print(
                json.dumps(
                    {
                        "schema": 1,
                        "status": "error",
                        "error": error_payload,
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"error[{error.code}]: {error.message}", file=sys.stderr)
        return error.exit_code
