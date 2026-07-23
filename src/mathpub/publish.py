"""Build publications atomically from immutable question instances."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from mathpub import __version__
from mathpub.catalog import Catalog, Entry
from mathpub.config import Project, load_toml, relative
from mathpub.errors import MathpubError
from mathpub.instance import (
    canonical_json,
    instance_hash,
    instantiate,
    instantiate_component,
)
from mathpub.render import (
    SOURCE_BEGIN,
    SOURCE_END,
    compile_pdf,
    component_tex,
    document_tex,
    question_tex,
    textbook_tex,
)


def _generated_source_map(project: Project, tex_path: Path, source: str) -> list[dict[str, Any]]:
    """Map marked generated line ranges back to authored component fragments."""
    entries: list[dict[str, Any]] = []
    active: dict[str, Any] | None = None
    for line_number, line in enumerate(source.splitlines(), start=1):
        if line.startswith(SOURCE_BEGIN):
            if active is not None:
                raise MathpubError("MP-TEX-011", "nested generated source markers")
            active = json.loads(line.removeprefix(SOURCE_BEGIN))
            active["generated_start_line"] = line_number + 1
            active["generated_source"] = relative(project, tex_path)
            active["authored_source"] = relative(project, Path(active["authored_source"]))
        elif line == SOURCE_END:
            if active is None:
                raise MathpubError("MP-TEX-011", "unmatched generated source marker")
            active["generated_end_line"] = line_number - 1
            entries.append(active)
            active = None
    if active is not None:
        raise MathpubError("MP-TEX-011", "unterminated generated source marker")
    return entries


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_hash(entry: Entry) -> str:
    if entry.kind == "component":
        digest = hashlib.sha256()
        paths = [entry.path / "component.toml"]
        if generator := entry.metadata.get("generator"):
            paths.append(entry.path / generator)
        for name in entry.metadata.get("fragments", {}).values():
            paths.append(entry.path / name)
        for path in sorted(paths):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()
    digest = hashlib.sha256()
    paths = [entry.path / "question.toml"]
    for key in ("generator", "prompt", "answer", "solution"):
        if name := entry.metadata.get(key):
            paths.append(entry.path / name)
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _component_source_hash(entry: Entry) -> str:
    if entry.kind == "question":
        return _source_hash(entry)
    digest = hashlib.sha256()
    paths = [entry.path / "component.toml"]
    if generator := entry.metadata.get("generator"):
        paths.append(entry.path / generator)
    for name in entry.metadata.get("fragments", {}).values():
        paths.append(entry.path / name)
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_source(project: Project) -> dict[str, Any]:
    def git(*arguments: str) -> str:
        process = subprocess.run(
            ["git", *arguments], cwd=project.root, capture_output=True, text=True, check=False
        )
        return process.stdout.strip() if process.returncode == 0 else ""

    return {"git_commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def _toolchain() -> dict[str, str]:
    def version(*command: str) -> str:
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        output = process.stdout or process.stderr
        return output.splitlines()[0].strip() if output else "unknown"

    return {
        "mathpub": __version__,
        "sagemath": version("sage", "--version"),
        "lualatex": version("lualatex", "--version"),
    }


def _inspect_pdf(path: Path, title: str) -> dict[str, Any]:
    reader = PdfReader(path)
    if not reader.pages:
        raise MathpubError("MP-PDF-001", f"PDF has no pages: {path}", exit_code=7)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if title not in text:
        raise MathpubError("MP-PDF-002", f"PDF does not contain its title: {path}", exit_code=7)
    return {"pages": len(reader.pages), "sha256": _file_hash(path)}


def _publication_path(project: Project, source: str | Path) -> Path:
    path = Path(source)
    if not path.is_absolute():
        path = project.root / path
    return path.resolve()


def _lesson_path(project: Project, publication_path: Path, source: str) -> Path:
    path = (publication_path.parent / source).resolve()
    try:
        path.relative_to(project.root)
    except ValueError as error:
        raise MathpubError("MP-SRC-005", f"lesson source escapes project root: {source}") from error
    if not path.is_file():
        raise MathpubError("MP-SRC-012", f"missing lesson source: {path}")
    return path


def _textbook_chapters(
    project: Project, publication_path: Path, publication: dict[str, Any], projection: str
) -> list[str]:
    rendered = []
    for chapter in publication["chapters"]:
        pieces = [rf"\chapter{{{chapter['title']}}}"]
        if introduction := chapter.get("introduction"):
            pieces.append(introduction)
        for lesson in chapter["lessons"]:
            pieces.append(rf"\section{{{lesson['title']}}}")
            objectives = lesson.get("objectives", [])
            if objectives:
                items = "\n".join(rf"\item {objective}" for objective in objectives)
                pieces.append(
                    rf"\subsection*{{Learning objectives}}\begin{{itemize}}{items}\end{{itemize}}"
                )
            for key in ("content", "exercises"):
                pieces.append(_lesson_path(project, publication_path, lesson[key]).read_text())
            if source := lesson.get("self_assessment"):
                pieces.append(_lesson_path(project, publication_path, source).read_text())
            if projection == "answers":
                pieces.append(
                    _lesson_path(project, publication_path, lesson["answers"]).read_text()
                )
            elif projection in {"solutions", "validation"}:
                pieces.append(
                    _lesson_path(project, publication_path, lesson["solutions"]).read_text()
                )
            if projection == "validation":
                if source := lesson.get("validation"):
                    pieces.append(_lesson_path(project, publication_path, source).read_text())
                else:
                    pieces.append(
                        r"\paragraph{Validation boundary.} Reviewed fixed content; "
                        r"no executable checks are declared."
                    )
        if practice := chapter.get("practice"):
            pieces.append(rf"\section{{{practice['title']}}}")
            for key in ("exercises", "self_assessment"):
                pieces.append(_lesson_path(project, publication_path, practice[key]).read_text())
            if projection == "answers":
                pieces.append(
                    _lesson_path(project, publication_path, practice["answers"]).read_text()
                )
            elif projection in {"solutions", "validation"}:
                pieces.append(
                    _lesson_path(project, publication_path, practice["solutions"]).read_text()
                )
            if projection == "validation" and (source := practice.get("validation")):
                pieces.append(_lesson_path(project, publication_path, source).read_text())
        rendered.append("\n".join(pieces))
    return rendered


def _related_components(catalog: Catalog, kind: str, concepts: list[str]) -> list[Entry]:
    selected = set(concepts)
    return [
        entry
        for entry in catalog.components.values()
        if entry.metadata["kind"] == kind
        and selected.intersection(entry.metadata.get("concepts", []))
    ]


def _problem_parts(problem_set: dict[str, Any]) -> list[dict[str, Any]]:
    """Return explicit problem parts, or one untitled compatibility part."""
    if parts := problem_set.get("parts"):
        return parts
    return [{"id": "questions", "title": "", "questions": problem_set["questions"]}]


def _problem_questions(problem_set: dict[str, Any]) -> list[dict[str, Any]]:
    return [question for part in _problem_parts(problem_set) for question in part["questions"]]


def _directions_tex(source: dict[str, Any], *, italic: bool = False) -> str:
    """Render directions, preserving semantic lead labels and paragraph boundaries."""
    if lines := source.get("direction_lines"):
        rendered = []
        for line in lines:
            label = rf"\textbf{{{line['label']}}} " if line.get("label") else ""
            text = rf"\textit{{{line['text']}}}" if italic else line["text"]
            rendered.append(rf"\noindent {label}{text}\par")
        return "\n".join(rendered)
    directions = source.get("directions", "")
    return rf"\noindent\textit{{{directions}}}" if italic and directions else directions


def _component_placement_specs(
    catalog: Catalog, publication: dict[str, Any]
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(component_id: str, placement: str, overrides=None) -> None:
        if placement in seen:
            raise MathpubError("MP-SRC-013", f"duplicate component placement: {placement}")
        entry = catalog.get("component", component_id)
        seen.add(placement)
        specs.append(
            {
                "entry": entry,
                "placement": placement,
                "overrides": overrides or {},
            }
        )

    for chapter in publication.get("component_chapters", []):
        for lesson in chapter["lessons"]:
            for block_index, block in enumerate(lesson["blocks"], start=1):
                prefix = f"{chapter['id']}.{lesson['id']}.block-{block_index}"
                if block.get("heading"):
                    continue
                if component_id := block.get("include"):
                    add(component_id, block["placement"], block.get("overrides"))
                elif derived := block.get("derive"):
                    if derived == "objectives":
                        component_ids = lesson.get("objectives", [])
                    elif derived == "concept-summary":
                        component_ids = lesson["concepts"]
                    elif derived == "common-errors":
                        component_ids = [
                            entry.metadata["id"]
                            for entry in _related_components(
                                catalog, "misconception", lesson["concepts"]
                            )
                        ]
                    else:
                        component_ids = [
                            entry.metadata["id"]
                            for entry in _related_components(
                                catalog, "teaching-tip", lesson["concepts"]
                            )
                        ]
                    for item_index, component_id in enumerate(component_ids, start=1):
                        add(component_id, f"{prefix}.{derived}-{item_index}")
                elif problem_set := block.get("problem_set"):
                    for question in _problem_questions(problem_set):
                        add(question["id"], question["placement"], question.get("overrides"))
                    if self_assessment := problem_set.get("self_assessment"):
                        add(
                            self_assessment,
                            problem_set["self_assessment_placement"],
                        )
    return specs


def _component_book_chapters(
    catalog: Catalog,
    publication: dict[str, Any],
    projection: str,
    instances: dict[str, dict[str, Any]],
) -> list[str]:
    def render(
        placement: str,
        projection_name: str,
        phase: str = "body",
        *,
        workspace: str | None = None,
        response: str = "workspace",
        emphasize_answer: bool = False,
    ) -> str:
        instance = instances[placement]
        entry = catalog.get("component", instance["component_id"])
        return component_tex(
            entry,
            instance,
            projection_name,
            phase=phase,
            workspace=workspace,
            response=response,
            style=publication.get("style", "mathpub"),
            emphasize_answer=emphasize_answer,
        )

    rendered_chapters = []
    for chapter in publication["component_chapters"]:
        anna_style = publication.get("style") == "anna"
        chapter_parts = [] if anna_style else [rf"\chapter{{{chapter['title']}}}"]
        if introduction := chapter.get("introduction"):
            chapter_parts.append(introduction)
        for lesson in chapter["lessons"]:
            if anna_style:
                if heading := lesson.get("heading"):
                    chapter_parts.append(rf"\annapractice{{{heading}}}{{{lesson['title']}}}")
                else:
                    chapter_parts.append(
                        rf"\annachapter{{{lesson.get('number', lesson['id'])}}}"
                        rf"{{{lesson['title']}}}"
                    )
            else:
                chapter_parts.append(rf"\section{{{lesson['title']}}}")
            for block_index, block in enumerate(lesson["blocks"], start=1):
                prefix = f"{chapter['id']}.{lesson['id']}.block-{block_index}"
                if heading := block.get("heading"):
                    if block.get("page_break_before"):
                        chapter_parts.append(r"\clearpage")
                    chapter_parts.append(rf"\subsection*{{{heading}}}")
                    continue
                if block.get("include"):
                    audience = block.get("audience")
                    if audience == "parent" and projection != "parent":
                        continue
                    if block.get("page_break_before"):
                        chapter_parts.append(r"\clearpage")
                    chapter_parts.append(render(block["placement"], projection))
                    continue
                if derived := block.get("derive"):
                    if derived == "objectives":
                        component_ids = lesson.get("objectives", [])
                        title = block.get("title", "What You Will Learn")
                        phase = "list-item"
                    elif derived == "concept-summary":
                        component_ids = lesson["concepts"]
                        title = block.get("title", "Summary")
                        phase = "summary"
                    elif derived == "common-errors":
                        component_ids = [
                            entry.metadata["id"]
                            for entry in _related_components(
                                catalog, "misconception", lesson["concepts"]
                            )
                        ]
                        title = block.get("title", "Common Mistakes to Avoid")
                        phase = "list-item"
                    else:
                        if block.get("audience") == "parent" and projection != "parent":
                            continue
                        component_ids = [
                            entry.metadata["id"]
                            for entry in _related_components(
                                catalog, "teaching-tip", lesson["concepts"]
                            )
                        ]
                        title = block.get(
                            "title", "Teaching Tips for Tutors and Homeschool Parents"
                        )
                        phase = "list-item"
                    items = [
                        render(f"{prefix}.{derived}-{index}", projection, phase)
                        for index, _ in enumerate(component_ids, start=1)
                    ]
                    if derived in {"objectives", "common-errors", "teaching-tips"}:
                        body = "\n".join(
                            (
                                rf"\subsection*{{{title}}}",
                                r"\begin{itemize}",
                                *items,
                                r"\end{itemize}",
                            )
                        )
                    elif anna_style:
                        body = "\n".join(
                            (
                                rf"\begin{{annasummary}}{{{title}}}",
                                *items,
                                r"\end{annasummary}",
                            )
                        )
                    else:
                        body = "\n".join((rf"\subsection*{{{title}}}", *items))
                    chapter_parts.append(body)
                    continue
                problem_set = block["problem_set"]
                parts = [r"\clearpage"] if problem_set.get("page_break_before") else []
                if anna_style and problem_set.get("show_title", True):
                    parts.append(
                        rf"\annaproblemset{{{problem_set.get('number', '')}}}"
                        rf"{{{problem_set['title']}}}"
                    )
                    if directions := _directions_tex(problem_set):
                        parts.append(rf"\begin{{annadirections}}{directions}\end{{annadirections}}")
                elif not anna_style:
                    parts.extend(
                        (
                            rf"\subsection*{{{problem_set['title']}}}",
                            _directions_tex(problem_set),
                        )
                    )
                for part_index, problem_part in enumerate(_problem_parts(problem_set)):
                    if problem_part.get("page_break_before"):
                        parts.append(r"\clearpage")
                    if problem_part.get("title"):
                        parts.append(rf"\problempart{{{problem_part['title']}}}")
                    if part_directions := _directions_tex(problem_part, italic=anna_style):
                        parts.append(part_directions)
                    enumeration = (
                        r"\begin{enumerate}[leftmargin=*,label=\arabic*.,series=problemset]"
                        if part_index == 0
                        else r"\begin{enumerate}[leftmargin=*,label=\arabic*.,resume=problemset]"
                    )
                    parts.append(enumeration)
                    for question in problem_part["questions"]:
                        if question.get("page_break_before"):
                            parts.append(r"\clearpage")
                        parts.append(
                            render(
                                question["placement"],
                                projection,
                                "prompt",
                                workspace=problem_part.get("workspace", question.get("workspace")),
                                response=question.get(
                                    "response", problem_part.get("response", "workspace")
                                ),
                            )
                        )
                    parts.append(r"\end{enumerate}")
                if problem_set.get("self_assessment"):
                    if problem_set.get("self_assessment_page_break_before"):
                        parts.append(r"\clearpage")
                    parts.append(render(problem_set["self_assessment_placement"], projection))
                if projection in {"answers", "solutions", "validation", "parent"}:
                    phase = "answer" if projection == "answers" else projection
                    if problem_set.get("answer_page_break_before", anna_style):
                        parts.append(r"\clearpage")
                    answer_title = problem_set.get("answer_title", problem_set["title"])
                    parts.append(rf"\answerkeytitle{{{answer_title}}}")
                    for part_index, problem_part in enumerate(_problem_parts(problem_set)):
                        if problem_part.get("answer_page_break_before"):
                            parts.append(r"\clearpage")
                        if problem_part.get("title"):
                            answer_part_title = problem_part.get(
                                "answer_title", problem_part["title"]
                            )
                            parts.append(rf"\problempart{{{answer_part_title}}}")
                        enumeration = (
                            r"\begin{enumerate}[leftmargin=*,label=\arabic*.,series=answerset]"
                            if part_index == 0
                            else r"\begin{enumerate}[leftmargin=*,label=\arabic*.,resume=answerset]"
                        )
                        parts.append(enumeration)
                        parts.extend(
                            render(
                                question["placement"],
                                projection,
                                phase,
                                emphasize_answer=question.get(
                                    "emphasize_answer",
                                    problem_part.get("emphasize_answers", False),
                                ),
                            )
                            for question in problem_part["questions"]
                        )
                        parts.append(r"\end{enumerate}")
                parts.append("\n")
                chapter_parts.append("\n".join(parts))
        rendered_chapters.append("\n".join(chapter_parts))
    return rendered_chapters


def build(
    project: Project,
    publication_source: str | Path,
    *,
    root_seed: str,
    variant: str,
    projections: list[str] | None = None,
    font_family: str | None = None,
    replace: bool = False,
    stored_instances: dict[str, dict[str, Any]] | None = None,
    stored_component_instances: dict[str, dict[str, Any]] | None = None,
    reproduction_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    publication_path = _publication_path(project, publication_source)
    publication = load_toml(publication_path, "publication")
    anna_style = publication.get("style") == "anna"
    selected_font = font_family or (
        "computer-modern" if anna_style else publication.get("font", "libertinus")
    )
    if selected_font not in {"concrete", "libertinus", "computer-modern"}:
        raise MathpubError("MP-TEX-010", f"unknown font family: {selected_font}", exit_code=3)
    tex_engine = "pdflatex" if selected_font == "computer-modern" else "lualatex"
    catalog = Catalog(project)
    selected = projections or publication.get("projections", ["student", "solutions"])
    build_root = project.root / project.config.get("build_dir", "build")
    destination = build_root / publication["id"] / variant
    if destination.exists():
        if not replace:
            raise MathpubError("MP-BUILD-001", f"edition already exists: {destination}")
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".tmp-", dir=destination.parent))
    try:
        instance_dir = temporary / "instances"
        tex_dir = temporary / "generated-tex"
        log_dir = temporary / "logs"
        for directory in (instance_dir, tex_dir, log_dir):
            directory.mkdir()
        ordered: list[tuple[Entry, dict[str, Any], dict[str, Any]]] = []
        for section in publication.get("sections", []):
            for selection in section["questions"]:
                entry = catalog.get("question", selection["id"])
                instance = (stored_instances or {}).get(entry.metadata["id"])
                if instance is None:
                    instance = instantiate(entry, root_seed, variant)
                expected = instance.get("sha256")
                unhashed = {key: value for key, value in instance.items() if key != "sha256"}
                if expected != instance_hash(unhashed):
                    raise MathpubError(
                        "MP-BUILD-002",
                        f"instance hash mismatch: {entry.metadata['id']}",
                        exit_code=8,
                    )
                (instance_dir / f"{entry.metadata['id']}.json").write_text(
                    canonical_json(instance), encoding="utf-8"
                )
                ordered.append((entry, instance, selection))
        component_ordered: list[tuple[Entry, dict[str, Any], dict[str, Any]]] = []
        component_instances: dict[str, dict[str, Any]] = {}
        for spec in _component_placement_specs(catalog, publication):
            entry = spec["entry"]
            placement = spec["placement"]
            instance = (stored_component_instances or {}).get(placement)
            if instance is None:
                instance = instantiate_component(
                    entry,
                    root_seed,
                    variant,
                    placement,
                    overrides=spec["overrides"],
                )
            expected = instance.get("sha256")
            unhashed = {key: value for key, value in instance.items() if key != "sha256"}
            if expected != instance_hash(unhashed):
                raise MathpubError(
                    "MP-BUILD-002",
                    f"instance hash mismatch: {entry.metadata['id']} at {placement}",
                    exit_code=8,
                )
            (instance_dir / f"{placement}.json").write_text(
                canonical_json(instance), encoding="utf-8"
            )
            component_instances[placement] = instance
            component_ordered.append((entry, instance, spec))
        outputs = []
        generated_source_maps: dict[str, list[dict[str, Any]]] = {}
        for projection in selected:
            rendered = [
                question_tex(entry, instance, projection, selection.get("points"))
                for entry, instance, selection in ordered
            ]
            stem = f"{publication['id']}-{variant}-{projection}"
            tex_path = tex_dir / f"{stem}.tex"
            if publication["kind"] == "textbook":
                chapters = (
                    _component_book_chapters(catalog, publication, projection, component_instances)
                    if publication.get("component_chapters")
                    else _textbook_chapters(project, publication_path, publication, projection)
                )
                source = textbook_tex(
                    publication,
                    projection,
                    chapters,
                    selected_font,
                )
            else:
                source = document_tex(publication, projection, rendered, selected_font)
            tex_path.write_text(source, encoding="utf-8")
            source_map = _generated_source_map(project, tex_path, source)
            generated_source_maps[projection] = source_map
            source_map_path = tex_dir / "source-map.json"
            source_map_path.write_text(
                canonical_json({"schema": 1, "projections": generated_source_maps}),
                encoding="utf-8",
            )
            pdf_path, log_path = compile_pdf(
                tex_path,
                temporary,
                selected_font,
                tex_engine=tex_engine,
                projection=projection,
                source_map=source_map,
                generated_source=relative(project, tex_path),
                source_map_file=relative(project, source_map_path),
            )
            final_pdf = temporary / f"{stem}.pdf"
            if pdf_path != final_pdf:
                pdf_path.replace(final_pdf)
            synctex_path = temporary / f"{stem}.synctex.gz"
            if not synctex_path.is_file():
                raise MathpubError(
                    "MP-TEX-012",
                    f"TeX engine did not produce SyncTeX data for {projection}",
                    exit_code=6,
                )
            log_path.replace(log_dir / log_path.name)
            outputs.append(
                {
                    "projection": projection,
                    "path": final_pdf.name,
                    "synctex": synctex_path.name,
                    **_inspect_pdf(
                        final_pdf,
                        publication["component_chapters"][0]["lessons"][0]["title"]
                        if publication.get("style") == "anna"
                        else publication["title"],
                    ),
                }
            )
        manifest = {
            "schema": 1,
            "mathpub_version": __version__,
            "project": project.config["project"],
            "publication_id": publication["id"],
            "publication_path": relative(project, publication_path),
            "publication_kind": publication["kind"],
            "variant": variant,
            "root_seed": str(root_seed),
            "font_family": selected_font,
            "tex_engine": tex_engine,
            "rng_algorithm": "pcg64-v1",
            "toolchain": _toolchain(),
            "source": {
                **_git_source(project),
                "publication_sha256": _file_hash(publication_path),
                "question_sources": {
                    entry.metadata["id"]: _source_hash(entry) for entry, _, _ in ordered
                },
                "component_sources": {
                    entry.metadata["id"]: _component_source_hash(entry)
                    for entry, _, _ in component_ordered
                },
                "lesson_sources": {
                    lesson["id"]: {
                        key: _file_hash(_lesson_path(project, publication_path, lesson[key]))
                        for key in (
                            "content",
                            "exercises",
                            "self_assessment",
                            "answers",
                            "solutions",
                            "validation",
                        )
                        if lesson.get(key)
                    }
                    for chapter in publication.get("chapters", [])
                    for lesson in chapter["lessons"]
                },
                "unit_practice_sources": {
                    practice["id"]: {
                        key: _file_hash(_lesson_path(project, publication_path, practice[key]))
                        for key in (
                            "exercises",
                            "self_assessment",
                            "answers",
                            "solutions",
                            "validation",
                        )
                        if practice.get(key)
                    }
                    for chapter in publication.get("chapters", [])
                    if (practice := chapter.get("practice"))
                },
                "flake_lock_sha256": _file_hash(project.root / "flake.lock")
                if (project.root / "flake.lock").is_file()
                else None,
            },
            "questions": [
                {
                    "id": entry.metadata["id"],
                    "instance": f"instances/{entry.metadata['id']}.json",
                    "sha256": instance["sha256"],
                    "checks": instance["checks"],
                }
                for entry, instance, _ in ordered
            ],
            "components": [
                {
                    "id": entry.metadata["id"],
                    "kind": entry.metadata.get("kind", "question"),
                    "placement": spec["placement"],
                    "instance": f"instances/{spec['placement']}.json",
                    "sha256": instance["sha256"],
                    "checks": instance["checks"],
                }
                for entry, instance, spec in component_ordered
            ],
            "outputs": outputs,
        }
        if reproduction_override is not None:
            manifest["reproduction_override"] = reproduction_override
        (temporary / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        os.replace(temporary, destination)
    except Exception as error:
        failure = destination.parent / f"failed-{temporary.name.removeprefix('.tmp-')}"
        if temporary.exists():
            os.replace(temporary, failure)
        if isinstance(error, MathpubError):
            for key in ("log", "generated_source", "source_map"):
                if value := error.details.get(key):
                    old_path = Path(value)
                    if not old_path.is_absolute():
                        old_path = project.root / old_path
                    try:
                        failure_path = failure / old_path.relative_to(temporary)
                    except ValueError:
                        continue
                    if key == "log" and failure_path.parent == failure and failure_path.exists():
                        persistent_log = failure / "logs" / failure_path.name
                        failure_path.replace(persistent_log)
                        failure_path = persistent_log
                    replacement = relative(project, failure_path)
                    error.message = error.message.replace(str(value), replacement)
                    error.details[key] = replacement
        raise
    return {
        "edition": relative(project, destination),
        "manifest": relative(project, destination / "manifest.json"),
        "outputs": outputs,
    }


def reproduce(
    project: Project,
    manifest_path: Path,
    *,
    replace: bool = False,
    allow_different_toolchain: bool = False,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    publication_path = _publication_path(project, manifest["publication_path"])
    publication = load_toml(publication_path, "publication")
    catalog = Catalog(project)
    current_source = {
        "publication_sha256": _file_hash(publication_path),
        "question_sources": {
            question["id"]: _source_hash(catalog.get("question", question["id"]))
            for question in manifest["questions"]
        },
        "component_sources": {
            component["id"]: _component_source_hash(catalog.get("component", component["id"]))
            for component in manifest.get("components", [])
        },
        "lesson_sources": {
            lesson["id"]: {
                key: _file_hash(_lesson_path(project, publication_path, lesson[key]))
                for key in (
                    "content",
                    "exercises",
                    "self_assessment",
                    "answers",
                    "solutions",
                    "validation",
                )
                if lesson.get(key)
            }
            for chapter in publication.get("chapters", [])
            for lesson in chapter["lessons"]
        },
        "unit_practice_sources": {
            practice["id"]: {
                key: _file_hash(_lesson_path(project, publication_path, practice[key]))
                for key in (
                    "exercises",
                    "self_assessment",
                    "answers",
                    "solutions",
                    "validation",
                )
                if practice.get(key)
            }
            for chapter in publication.get("chapters", [])
            if (practice := chapter.get("practice"))
        },
        "flake_lock_sha256": _file_hash(project.root / "flake.lock")
        if (project.root / "flake.lock").is_file()
        else None,
    }
    mismatches = {}
    for key, value in current_source.items():
        if manifest["source"].get(key) != value:
            mismatches[f"source.{key}"] = {
                "expected": manifest["source"].get(key),
                "actual": value,
            }
    current_toolchain = _toolchain()
    if manifest.get("toolchain") != current_toolchain:
        mismatches["toolchain"] = {
            "expected": manifest.get("toolchain"),
            "actual": current_toolchain,
        }
    if mismatches and not allow_different_toolchain:
        raise MathpubError(
            "MP-REPRO-001",
            f"source or toolchain differs from manifest: {', '.join(mismatches)}",
            exit_code=8,
        )
    instances = {}
    for question in manifest["questions"]:
        instance = json.loads((base / question["instance"]).read_text(encoding="utf-8"))
        instances[question["id"]] = instance
    component_instances = {}
    for component in manifest.get("components", []):
        instance = json.loads((base / component["instance"]).read_text(encoding="utf-8"))
        component_instances[component["placement"]] = instance
    return build(
        project,
        manifest["publication_path"],
        root_seed=manifest["root_seed"],
        variant=manifest["variant"],
        projections=[output["projection"] for output in manifest["outputs"]],
        font_family=manifest.get("font_family", "concrete"),
        replace=replace,
        stored_instances=instances,
        stored_component_instances=component_instances,
        reproduction_override={"allowed": True, "mismatches": mismatches} if mismatches else None,
    )
