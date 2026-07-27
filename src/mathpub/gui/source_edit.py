"""Safe, revision-aware editing of authored TeX fragments."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from mathpub.config import Project
from mathpub.errors import MathpubError
from mathpub.gui.onboarding import _clean_process_output

SOURCE_EDIT_LIMIT = 256 * 1024
SOURCE_PATH_LIMIT = 500
SOURCE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _revision(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _editable_source(project: Project, source: object) -> tuple[Path, str]:
    if (
        not isinstance(source, str)
        or not source
        or len(source) > SOURCE_PATH_LIMIT
        or not SOURCE_PATH_RE.fullmatch(source)
    ):
        raise MathpubError("MP-GUI-010", "editable source path is invalid")
    relative = Path(source)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".tex":
        raise MathpubError("MP-GUI-010", "only project-relative TeX sources can be edited")

    source_path = (project.root / relative).resolve()
    authored_roots = (
        *project.question_roots,
        *project.component_roots,
        *project.publication_roots,
    )
    if not any(source_path.is_relative_to(root.resolve()) for root in authored_roots):
        raise MathpubError("MP-GUI-010", "source is outside the authored-content roots")
    if not source_path.is_file():
        raise MathpubError("MP-GUI-011", f"TeX source does not exist: {source}")
    return source_path, source_path.relative_to(project.root).as_posix()


def _read_source(source_path: Path) -> tuple[bytes, str]:
    try:
        content = source_path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MathpubError(
            "MP-GUI-011", f"could not read TeX source: {source_path.name}"
        ) from error
    if len(content) > SOURCE_EDIT_LIMIT:
        raise MathpubError(
            "MP-GUI-010",
            f"TeX source is too large for quick editing ({len(content)} bytes)",
        )
    return content, text


def load_tex_source(project: Project, source: object) -> dict[str, object]:
    """Load one authored TeX source and its optimistic-lock revision."""
    source_path, relative = _editable_source(project, source)
    content, text = _read_source(source_path)
    return {
        "path": relative,
        "content": text,
        "revision": _revision(content),
    }


def _atomic_write(source_path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source_path.name}.",
        suffix=".mathpub-edit",
        dir=source_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, source_path)
    finally:
        temporary_path.unlink(missing_ok=True)


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
    return MathpubError("MP-GUI-013", message, details=details)


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
        raise _git_failure("Git could not commit the quick edit", command, result)
    return result


def _commit_environment(git: str, project: Project) -> dict[str, str]:
    environment = os.environ.copy()
    name = _git_run(git, project, ["config", "--get", "user.name"], check=False).stdout.strip()
    email = _git_run(git, project, ["config", "--get", "user.email"], check=False).stdout.strip()
    if not name:
        environment["GIT_AUTHOR_NAME"] = "MathPub Quick Edit"
        environment["GIT_COMMITTER_NAME"] = "MathPub Quick Edit"
    if not email:
        environment["GIT_AUTHOR_EMAIL"] = "quick-edit@mathpub.local"
        environment["GIT_COMMITTER_EMAIL"] = "quick-edit@mathpub.local"
    return environment


def save_tex_source(
    project: Project,
    source: object,
    content: object,
    revision: object,
) -> dict[str, object]:
    """Atomically save and commit exactly one revision-matched TeX source."""
    source_path, relative = _editable_source(project, source)
    if not isinstance(content, str) or not isinstance(revision, str):
        raise MathpubError("MP-GUI-010", "source content and revision must be strings")
    if "\x00" in content:
        raise MathpubError("MP-GUI-010", "TeX source cannot contain NUL characters")

    new_content = content.encode("utf-8")
    if len(new_content) > SOURCE_EDIT_LIMIT:
        raise MathpubError(
            "MP-GUI-010",
            f"TeX source exceeds the {SOURCE_EDIT_LIMIT}-byte quick-edit limit",
        )

    original_content, _ = _read_source(source_path)
    if _revision(original_content) != revision:
        raise MathpubError(
            "MP-GUI-012",
            "source changed after it was opened; reload before saving",
        )
    if new_content == original_content:
        raise MathpubError("MP-GUI-014", "there are no changes to save")

    git = shutil.which("git")
    if git is None:
        raise MathpubError("MP-GUI-013", "Git is unavailable; the edit was not saved")
    repository = _git_run(git, project, ["rev-parse", "--show-toplevel"])
    if Path(repository.stdout.strip()).resolve() != project.root.resolve():
        raise MathpubError(
            "MP-GUI-013",
            "the MathPub project root must also be the Git repository root",
        )

    tracked = (
        _git_run(
            git,
            project,
            ["ls-files", "--error-unmatch", "--", relative],
            check=False,
        ).returncode
        == 0
    )
    mode = stat.S_IMODE(source_path.stat().st_mode)
    _atomic_write(source_path, new_content, mode)
    intent_added = False
    try:
        if not tracked:
            _git_run(git, project, ["add", "--intent-to-add", "--", relative])
            intent_added = True
        commit_message = f"Quick edit: {relative}"
        _git_run(
            git,
            project,
            ["commit", "--only", "-m", commit_message, "--", relative],
            environment=_commit_environment(git, project),
        )
        commit = _git_run(git, project, ["rev-parse", "HEAD"]).stdout.strip()
    except MathpubError:
        _atomic_write(source_path, original_content, mode)
        if intent_added:
            _git_run(
                git,
                project,
                ["rm", "--cached", "--force", "--", relative],
                check=False,
            )
        raise

    return {
        "path": relative,
        "revision": _revision(new_content),
        "commit": commit,
        "message": commit_message,
    }
