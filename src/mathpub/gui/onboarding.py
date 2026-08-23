"""Agent and authoring-library onboarding for the interactive workspace."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from mathpub.config import ID_PATTERN
from mathpub.errors import MathpubError
from mathpub.scaffold import init_project

STARTER_PROMPT = (
    "Outline my first book. Ask about the audience, prerequisites, scope, sequence, and desired "
    "editions, then show me the proposed units and dependencies before writing the first section."
)
AGENT_BOOTSTRAP_PROMPT = (
    "Read AGENTS.md and run `nix run .#mathpub -- capabilities` before doing any work; the runtime "
    "contract is authoritative if an older repository file differs. Use the MathPub framework for "
    "every requested publication, first identify the requested document type, and operate the "
    "framework autonomously on the author's behalf. Do not build merely to orient yourself at "
    "startup. Let the workspace watcher handle edits; manual builds are incremental by default. "
    "The workspace batches generated-page review requests. When complete_task returns a pending "
    "review instead of accepting completion, use an image-viewing tool to inspect every named "
    "changed-page PNG, correct content, formatting, clipping, or diagram problems, and then call "
    "complete_task again. "
    "Never use `--full-rebuild` unless cached output appears wrong or corrupt, clean reproduction "
    "is explicitly required, or the author asks for it. When the requested work and validation "
    "are genuinely complete, call the `complete_task` tool before your final response "
    "so the author receives the visible summary and chime. Use the capability contract's CLI "
    "fallback only if that tool is unavailable."
)
AGENT_LAUNCH_COMMAND_ENV = "MATHPUB_WORKSPACE_AGENT_LAUNCH_COMMAND"
AGENT_LAUNCH_INPUT = f'eval "${AGENT_LAUNCH_COMMAND_ENV}"'
CODEX_LAUNCH_COMMAND_ENV = "MATHPUB_WORKSPACE_CODEX_LAUNCH_COMMAND"
CODEX_LAUNCH_INPUT = f'eval "${CODEX_LAUNCH_COMMAND_ENV}"'
ANTIGRAVITY_AGENT_ID = "antigravity"
CODEX_AGENT_ID = "codex"
DEFAULT_AGENT_COMMAND = (
    "nix",
    "run",
    "github:anicolao/nix-antigravity",
    "--",
    "--new-project",
    "--sandbox",
    "--dangerously-skip-permissions",
    "--prompt-interactive",
    AGENT_BOOTSTRAP_PROMPT,
)
DEFAULT_CODEX_COMMAND = (
    "bunx",
    "@openai/codex",
    "--yolo",
    "--no-alt-screen",
    "-c",
    'mcp_servers.mathpub-workspace.command="mathpub"',
    "-c",
    'mcp_servers.mathpub-workspace.args=["mcp"]',
    AGENT_BOOTSTRAP_PROMPT,
)
PROCESS_OUTPUT_LIMIT = 8_000
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
URL_CREDENTIAL_RE = re.compile(r"(https?://)[^/\s@]+@")
GITHUB_TOKEN_RE = re.compile(r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+\b")
SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(token|password|secret|authorization)(\s*[:=]\s*)\S+")
GIT_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
CLI_REVISION_RE = re.compile(r"\(([0-9a-f]{7,40})\)\s*$", re.IGNORECASE)


def _clean_process_output(value: object) -> str:
    if value is None:
        return ""
    text = value.decode(errors="replace") if isinstance(value, bytes) else str(value)
    text = ANSI_ESCAPE_RE.sub("", text)
    text = "".join(
        character for character in text if character in "\n\t" or character.isprintable()
    )
    text = URL_CREDENTIAL_RE.sub(r"\1[redacted]@", text)
    text = GITHUB_TOKEN_RE.sub("[redacted]", text)
    text = SECRET_ASSIGNMENT_RE.sub(r"\1\2[redacted]", text)
    text = text.strip()
    if len(text) > PROCESS_OUTPUT_LIMIT:
        text = f"[output truncated]\n{text[-PROCESS_OUTPUT_LIMIT:]}"
    return text


def _process_failure_details(
    error: OSError | subprocess.SubprocessError,
    *,
    stage: str,
    command: list[str] | None,
) -> dict[str, object]:
    details: dict[str, object] = {"stage": stage}
    error_command = getattr(error, "cmd", None)
    displayed_command = command if command is not None else error_command
    if isinstance(displayed_command, (list, tuple)):
        details["command"] = shlex.join(str(part) for part in displayed_command)
    elif displayed_command:
        details["command"] = _clean_process_output(displayed_command)

    return_code = getattr(error, "returncode", None)
    if return_code is not None:
        details["exit_status"] = return_code

    stdout = _clean_process_output(getattr(error, "stdout", None))
    stderr = _clean_process_output(getattr(error, "stderr", None))
    output_sections = []
    if stdout:
        output_sections.append(f"stdout:\n{stdout}")
    if stderr:
        output_sections.append(f"stderr:\n{stderr}")
    if output_sections:
        details["output"] = "\n\n".join(output_sections)
    elif isinstance(error, OSError):
        details["output"] = _clean_process_output(error)
    return details


@dataclass(frozen=True)
class AgentConfiguration:
    """One trusted, server-configured CLI agent launcher."""

    label: str
    command: tuple[str, ...]
    synchronize_mathpub: bool = False

    @classmethod
    def from_environment(cls) -> AgentConfiguration:
        raw_command = os.environ.get("MATHPUB_AGENT_COMMAND")
        if raw_command is None:
            command = DEFAULT_AGENT_COMMAND
        else:
            try:
                command = tuple(shlex.split(raw_command))
            except ValueError:
                command = ()
        return cls(
            label=os.environ.get("MATHPUB_AGENT_LABEL", "Antigravity"),
            command=command,
            synchronize_mathpub=raw_command is None,
        )

    @classmethod
    def codex_from_environment(cls) -> AgentConfiguration:
        raw_command = os.environ.get("MATHPUB_CODEX_COMMAND")
        if raw_command is None:
            command = DEFAULT_CODEX_COMMAND
        else:
            try:
                command = tuple(shlex.split(raw_command))
            except ValueError:
                command = ()
        return cls(
            label=os.environ.get("MATHPUB_CODEX_LABEL", "Codex"),
            command=command,
            synchronize_mathpub=raw_command is None,
        )

    @property
    def executable(self) -> str | None:
        if not self.command:
            return None
        candidate = Path(self.command[0]).expanduser()
        if candidate.is_absolute():
            return str(candidate) if candidate.is_file() else None
        return shutil.which(self.command[0])

    @property
    def available(self) -> bool:
        return self.executable is not None

    @property
    def shell_command(self) -> str | None:
        return shlex.join(self.command) if self.available else None

    def command_for(self, project_root: Path | None) -> tuple[str, ...] | None:
        """Return the agent command inside the project's pinned development shell."""
        if not self.command:
            return None
        command = self.command
        if project_root is not None and command == DEFAULT_AGENT_COMMAND:
            prompt_index = command.index("--prompt-interactive")
            command = (
                *command[:prompt_index],
                "--add-dir",
                str(project_root),
                *command[prompt_index:-1],
                (
                    f"The only authoring library for this session is {project_root}. "
                    "Work only inside that directory. Do not search the home directory, inspect "
                    "other repositories, or request access to paths outside the library. "
                    f"Start in {project_root}. {AGENT_BOOTSTRAP_PROMPT}"
                ),
            )
        elif project_root is not None and command == DEFAULT_CODEX_COMMAND:
            command = (
                *command[:-1],
                "--cd",
                str(project_root),
                (
                    f"The only authoring library for this session is {project_root}. "
                    "Work only inside that directory. Do not search the home directory, inspect "
                    "other repositories, or request access to paths outside the library. "
                    f"Start in {project_root}. {AGENT_BOOTSTRAP_PROMPT}"
                ),
            )
        if project_root is not None and (project_root / "flake.nix").is_file():
            if shutil.which("nix") is None:
                return None
            return (
                "nix",
                "develop",
                "--no-write-lock-file",
                "--no-warn-dirty",
                "--quiet",
                "--command",
                *command,
            )
        return command if self.available else None

    def shell_command_for(self, project_root: Path | None) -> str | None:
        command = self.command_for(project_root)
        return shlex.join(command) if command is not None else None

    def payload(self, project_root: Path | None = None) -> dict[str, object]:
        command = self.command_for(project_root)
        return {
            "label": self.label,
            "available": command is not None,
            "command": self.command[0] if self.command else None,
            "environment": (
                "nix develop"
                if project_root is not None and (project_root / "flake.nix").is_file()
                else None
            ),
        }


def synchronize_library_mathpub(
    project_root: Path,
    expected_revision: str,
) -> dict[str, object]:
    """Refresh a library's MathPub input when it differs from the GUI build."""
    expected_revision = expected_revision.strip()
    if GIT_REVISION_RE.fullmatch(expected_revision) is None:
        return {"skipped": True, "updated": False, "revision": None}

    nix = shutil.which("nix")
    if nix is None:
        raise MathpubError(
            "MP-GUI-023",
            "Nix is unavailable; cannot verify the library MathPub toolchain",
        )

    def cli_revision(*, stage: str, reference_lock_file: Path | None = None) -> str | None:
        version_command = [nix, "run"]
        if reference_lock_file is not None:
            version_command.extend(("--reference-lock-file", reference_lock_file.name))
        version_command.extend(
            (
                "--no-write-lock-file",
                "--no-warn-dirty",
                "--quiet",
                ".#mathpub",
                "--",
                "--version",
            )
        )
        try:
            result = subprocess.run(
                version_command,
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise MathpubError(
                "MP-GUI-023",
                "could not verify the library MathPub toolchain",
                details=_process_failure_details(
                    error,
                    stage=stage,
                    command=version_command,
                ),
            ) from error
        match = CLI_REVISION_RE.search(result.stdout.strip())
        return match.group(1).lower() if match is not None else None

    def revisions_match(actual: str | None) -> bool:
        if actual is None:
            return False
        expected = expected_revision.lower()
        return actual.startswith(expected) or expected.startswith(actual)

    previous_revision = cli_revision(stage="Checking the library MathPub version")
    if revisions_match(previous_revision):
        return {
            "skipped": False,
            "updated": False,
            "revision": previous_revision,
        }

    with tempfile.NamedTemporaryFile(
        dir=project_root,
        prefix=".mathpub-flake-lock-",
        suffix=".json",
        delete=False,
    ) as temporary_lock:
        updated_lock_file = Path(temporary_lock.name)
    updated_lock_file.unlink()
    update_command = [
        nix,
        "flake",
        "update",
        "--refresh",
        "--override-input",
        "mathpub",
        f"github:anicolao/mathpub/{expected_revision}",
        "--output-lock-file",
        updated_lock_file.name,
        "mathpub",
    ]
    try:
        subprocess.run(
            update_command,
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        revision = cli_revision(
            stage="Verifying the updated library MathPub version",
            reference_lock_file=updated_lock_file,
        )
        if not revisions_match(revision):
            raise MathpubError(
                "MP-GUI-023",
                "the library MathPub toolchain still does not match this GUI build",
                details={
                    "stage": "Verifying the updated library MathPub version",
                    "expected_revision": expected_revision,
                    "actual_revision": revision or "unavailable",
                },
            )
        os.replace(updated_lock_file, project_root / "flake.lock")
    except (OSError, subprocess.SubprocessError) as error:
        raise MathpubError(
            "MP-GUI-023",
            "could not update the library MathPub toolchain",
            details=_process_failure_details(
                error,
                stage="Updating the library MathPub input",
                command=update_command,
            ),
        ) from error
    finally:
        updated_lock_file.unlink(missing_ok=True)
    return {
        "skipped": False,
        "updated": True,
        "previous_revision": previous_revision,
        "revision": revision,
    }


def create_authoring_library(
    parent: str,
    name: str,
    *,
    mathpub_url: str = "github:anicolao/mathpub",
    lock_flake: bool = True,
) -> dict[str, object]:
    """Create a content-only local Git repository for many MathPub publications."""
    if not isinstance(parent, str) or not isinstance(name, str):
        raise MathpubError("MP-GUI-001", "library parent and name must be strings")
    if not ID_PATTERN.fullmatch(name):
        raise MathpubError(
            "MP-GUI-001",
            "library name must use lowercase letters, digits, dots, or hyphens",
        )

    parent_path = Path(parent).expanduser()
    if not parent_path.is_absolute():
        raise MathpubError("MP-GUI-001", "library parent must be an absolute path")
    parent_path = parent_path.resolve()
    if not parent_path.is_dir():
        raise MathpubError("MP-GUI-001", f"library parent does not exist: {parent_path}")

    target = parent_path / name
    if target.exists():
        raise MathpubError("MP-GUI-002", f"library directory already exists: {target}")

    stage = "Pinning the library toolchain"
    command: list[str] | None = None
    try:
        result = init_project(target, mathpub_url=mathpub_url)
        if lock_flake:
            nix = shutil.which("nix")
            if nix is None:
                raise MathpubError(
                    "MP-GUI-004", "Nix is unavailable; cannot pin the library toolchain"
                )
            command = [nix, "flake", "lock"]
            subprocess.run(
                command,
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        stage = "Initializing the private Git repository"
        git = shutil.which("git")
        if git is None:
            raise MathpubError("MP-GUI-003", "Git is unavailable; cannot initialize the library")
        command = [git, "init", "-b", "main"]
        subprocess.run(
            command,
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        command = [git, "add", "--intent-to-add", "--", "."]
        subprocess.run(
            command,
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except MathpubError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    except (OSError, subprocess.SubprocessError) as error:
        shutil.rmtree(target, ignore_errors=True)
        details = _process_failure_details(error, stage=stage, command=command)
        if stage == "Pinning the library toolchain":
            raise MathpubError(
                "MP-GUI-004",
                "could not pin the library toolchain",
                details=details,
            ) from error
        raise MathpubError(
            "MP-GUI-003",
            "could not initialize the private Git repository",
            details=details,
        ) from error

    return {
        **result,
        "name": name,
        "git_initialized": True,
        "flake_locked": lock_flake,
        "remote_created": False,
    }
