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
from mathpub.instance import canonical_json, instance_hash, instantiate
from mathpub.render import compile_pdf, document_tex, question_tex


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_hash(entry: Entry) -> str:
    digest = hashlib.sha256()
    paths = [entry.path / "question.toml"]
    for key in ("generator", "prompt", "answer", "solution"):
        if name := entry.metadata.get(key):
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


def build(
    project: Project,
    publication_source: str | Path,
    *,
    root_seed: str,
    variant: str,
    projections: list[str] | None = None,
    replace: bool = False,
    stored_instances: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    publication_path = _publication_path(project, publication_source)
    publication = load_toml(publication_path, "publication")
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
        for section in publication["sections"]:
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
        outputs = []
        for projection in selected:
            rendered = [
                question_tex(entry, instance, projection, selection.get("points"))
                for entry, instance, selection in ordered
            ]
            stem = f"{publication['id']}-{variant}-{projection}"
            tex_path = tex_dir / f"{stem}.tex"
            tex_path.write_text(document_tex(publication, projection, rendered), encoding="utf-8")
            pdf_path, log_path = compile_pdf(tex_path, temporary)
            final_pdf = temporary / f"{stem}.pdf"
            if pdf_path != final_pdf:
                pdf_path.replace(final_pdf)
            log_path.replace(log_dir / log_path.name)
            outputs.append(
                {
                    "projection": projection,
                    "path": final_pdf.name,
                    **_inspect_pdf(final_pdf, publication["title"]),
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
            "rng_algorithm": "pcg64-v1",
            "source": {
                **_git_source(project),
                "publication_sha256": _file_hash(publication_path),
                "question_sources": {
                    entry.metadata["id"]: _source_hash(entry) for entry, _, _ in ordered
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
            "outputs": outputs,
        }
        (temporary / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        failure = destination.parent / f"failed-{temporary.name.removeprefix('.tmp-')}"
        if temporary.exists():
            os.replace(temporary, failure)
        raise
    return {
        "edition": relative(project, destination),
        "manifest": relative(project, destination / "manifest.json"),
        "outputs": outputs,
    }


def reproduce(project: Project, manifest_path: Path, *, replace: bool = False) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = manifest_path.parent
    instances = {}
    for question in manifest["questions"]:
        instance = json.loads((base / question["instance"]).read_text(encoding="utf-8"))
        instances[question["id"]] = instance
    return build(
        project,
        manifest["publication_path"],
        root_seed=manifest["root_seed"],
        variant=manifest["variant"],
        projections=[output["projection"] for output in manifest["outputs"]],
        replace=replace,
        stored_instances=instances,
    )
