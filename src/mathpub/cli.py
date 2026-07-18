"""Command-line entry point for mathpub."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mathpub import __version__
from mathpub.catalog import Catalog
from mathpub.config import find_project, load_toml, relative
from mathpub.errors import MathpubError
from mathpub.output import emit
from mathpub.scaffold import init_project, new_question


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
    question.add_argument(
        "--kind", choices=("fixed", "numeric", "symbolic", "tikz"), default="fixed"
    )
    _json_flag(question)

    list_parser = commands.add_parser("list", help="discover project content")
    list_parser.add_argument("content", choices=("questions", "publications", "profiles"))
    _json_flag(list_parser)

    show = commands.add_parser("show", help="inspect a catalog entry")
    show.add_argument("content", choices=("question", "publication", "profile"))
    show.add_argument("identifier")
    _json_flag(show)

    inspect = commands.add_parser("inspect", help="inspect source or generated metadata")
    inspect.add_argument("content", choices=("publication", "manifest"))
    inspect.add_argument("path", type=Path)
    _json_flag(inspect)

    check = commands.add_parser("check", help="validate authored source")
    check.add_argument("content", choices=("project", "question", "publication"))
    check.add_argument("target", nargs="?")
    check.add_argument("--seeds", type=int)
    check.add_argument("--exhaustive", action="store_true")
    _json_flag(check)
    return result


def _entry_data(project, entry):
    result = entry.summary(project)
    result["metadata"] = entry.metadata
    return result


def _validate_files(project, entry) -> list[str]:
    checked: list[str] = []
    if entry.kind == "question":
        for key in ("prompt", "answer", "solution", "generator"):
            if filename := entry.metadata.get(key):
                path = entry.path / filename
                if not path.is_file():
                    raise MathpubError(
                        "MP-SRC-012", f"missing {key} for {entry.metadata['id']}: {path}"
                    )
                checked.append(relative(project, path))
    return checked


def run(args: argparse.Namespace) -> tuple[str, object]:
    if args.command == "init":
        return "init", init_project(args.directory)

    project = find_project()
    if args.command == "new":
        return "new question", new_question(project, args.identifier, args.kind)

    catalog = Catalog(project)
    if args.command == "list":
        data = [entry.summary(project) for entry in catalog.entries(args.content).values()]
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
        if args.content == "question":
            if not args.target:
                raise MathpubError(
                    "MP-CLI-001", "check question requires a question ID", exit_code=2
                )
            entry = catalog.get("question", args.target)
            checked = _validate_files(project, entry)
            return "check question", {"id": args.target, "checked": checked}
        if args.content == "publication":
            if not args.target:
                raise MathpubError("MP-CLI-002", "check publication requires a path", exit_code=2)
            path = Path(args.target)
            path = path if path.is_absolute() else project.root / path
            publication = load_toml(path, "publication")
            for section in publication["sections"]:
                for question in section["questions"]:
                    catalog.get("question", question["id"])
            return "check publication", {"id": publication["id"], "path": relative(project, path)}
        for entry in catalog.questions.values():
            _validate_files(project, entry)
        return "check project", {
            "project": project.config["project"],
            "questions": len(catalog.questions),
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
            print(
                json.dumps(
                    {
                        "schema": 1,
                        "status": "error",
                        "error": {"code": error.code, "message": error.message},
                    },
                    sort_keys=True,
                )
            )
        else:
            print(f"error[{error.code}]: {error.message}", file=sys.stderr)
        return error.exit_code
