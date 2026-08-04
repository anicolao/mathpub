"""Safe import and Git commit of author-selected reference files."""

from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from mathpub.config import Project
from mathpub.errors import MathpubError
from mathpub.gui.onboarding import _clean_process_output

REFERENCE_IMPORT_LIMIT = 50 * 1024 * 1024
REFERENCE_NAME_LIMIT = 255


def _reference_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise MathpubError("MP-GUI-015", "reference filename must be a non-empty string")
    if (
        value in {".", ".."}
        or value != Path(value).name
        or "/" in value
        or "\\" in value
        or any(character == "\x00" or not character.isprintable() for character in value)
        or len(value.encode("utf-8")) > REFERENCE_NAME_LIMIT
    ):
        raise MathpubError("MP-GUI-015", "reference filename is invalid")
    return value


def _git_failure(
    message: str,
    command: list[str],
    result: subprocess.CompletedProcess[str] | None = None,
) -> MathpubError:
    details: dict[str, object] = {"command": shlex.join(command)}
    if result is not None:
        details["exit_status"] = result.returncode
        output = _clean_process_output(result.stderr or result.stdout)
        if output:
            details["output"] = output
    return MathpubError("MP-GUI-017", message, details=details)


def _git_run(
    git: str,
    project: Project,
    arguments: list[str],
    *,
    check: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [git, "-C", str(project.root), *arguments]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise _git_failure(f"could not run Git: {error}", command) from error
    if check and result.returncode != 0:
        raise _git_failure("Git could not commit the imported reference", command, result)
    return result


def _commit_environment(git: str, project: Project) -> dict[str, str]:
    environment = os.environ.copy()
    name = _git_run(git, project, ["config", "--get", "user.name"], check=False).stdout.strip()
    email = _git_run(git, project, ["config", "--get", "user.email"], check=False).stdout.strip()
    if not name:
        environment["GIT_AUTHOR_NAME"] = "MathPub Reference Import"
        environment["GIT_COMMITTER_NAME"] = "MathPub Reference Import"
    if not email:
        environment["GIT_AUTHOR_EMAIL"] = "reference-import@mathpub.local"
        environment["GIT_COMMITTER_EMAIL"] = "reference-import@mathpub.local"
    return environment


def _atomic_create(path: Path, content: bytes) -> None:
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".mathpub-import",
            dir=path.parent,
        )
    except OSError as error:
        raise MathpubError("MP-GUI-018", f"could not create imported reference: {error}") from error
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(0o644)
        os.link(temporary_path, path)
    except FileExistsError as error:
        raise MathpubError(
            "MP-GUI-016", f"reference already exists: reference/{path.name}"
        ) from error
    except OSError as error:
        raise MathpubError("MP-GUI-018", f"could not copy imported reference: {error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def import_reference(project: Project, filename: object, content: bytes) -> dict[str, object]:
    """Atomically copy and commit one reference without including unrelated changes."""
    name = _reference_name(filename)
    if not isinstance(content, bytes):
        raise MathpubError("MP-GUI-015", "reference content must be bytes")
    if not content:
        raise MathpubError("MP-GUI-015", "reference file is empty")
    if len(content) > REFERENCE_IMPORT_LIMIT:
        raise MathpubError(
            "MP-GUI-015",
            f"reference exceeds the {REFERENCE_IMPORT_LIMIT}-byte import limit",
        )

    root = project.root.resolve()
    reference_path = root / "reference"
    if reference_path.is_symlink():
        raise MathpubError("MP-GUI-015", "reference directory cannot be a symbolic link")
    try:
        reference_path.mkdir(exist_ok=True)
    except OSError as error:
        raise MathpubError(
            "MP-GUI-018", f"could not create reference directory: {error}"
        ) from error
    reference_root = reference_path.resolve()
    if not reference_root.is_relative_to(root):
        raise MathpubError("MP-GUI-015", "reference directory escapes the authoring library")

    destination = (reference_root / name).resolve()
    if not destination.is_relative_to(reference_root):
        raise MathpubError("MP-GUI-015", "reference path escapes the reference directory")
    relative = destination.relative_to(root).as_posix()
    if destination.exists():
        raise MathpubError("MP-GUI-016", f"reference already exists: {relative}")

    git = shutil.which("git")
    if git is None:
        raise MathpubError("MP-GUI-017", "Git is unavailable; the reference was not imported")
    repository = _git_run(git, project, ["rev-parse", "--show-toplevel"])
    if Path(repository.stdout.strip()).resolve() != root:
        raise MathpubError(
            "MP-GUI-017",
            "the MathPub project root must also be the Git repository root",
        )

    _atomic_create(destination, content)
    intent_added = False
    try:
        _git_run(git, project, ["add", "--intent-to-add", "--force", "--", relative])
        intent_added = True
        commit_message = f"Import reference: {relative}"
        _git_run(
            git,
            project,
            ["commit", "--only", "-m", commit_message, "--", relative],
            environment=_commit_environment(git, project),
        )
        commit = _git_run(git, project, ["rev-parse", "HEAD"]).stdout.strip()
    except MathpubError:
        destination.unlink(missing_ok=True)
        if intent_added:
            _git_run(
                git,
                project,
                ["rm", "--cached", "--force", "--", relative],
                check=False,
            )
        with contextlib.suppress(OSError):
            reference_root.rmdir()
        raise

    return {
        "path": relative,
        "name": name,
        "size": len(content),
        "commit": commit,
        "message": commit_message,
    }
