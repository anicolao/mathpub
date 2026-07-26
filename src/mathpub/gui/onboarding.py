"""Agent and authoring-library onboarding for the interactive workspace."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mathpub.config import ID_PATTERN
from mathpub.errors import MathpubError
from mathpub.scaffold import init_project

STARTER_PROMPT = (
    "Outline my first book. Ask about the audience, prerequisites, scope, sequence, and desired "
    "editions, then show me the proposed units and dependencies before writing the first section."
)


@dataclass(frozen=True)
class AgentConfiguration:
    """One trusted, server-configured CLI agent launcher."""

    label: str
    command: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> AgentConfiguration:
        raw_command = os.environ.get(
            "MATHPUB_AGENT_COMMAND",
            "nix run github:anicolao/nix-antigravity",
        )
        try:
            command = tuple(shlex.split(raw_command))
        except ValueError:
            command = ()
        return cls(
            label=os.environ.get("MATHPUB_AGENT_LABEL", "Antigravity"),
            command=command,
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
                *self.command,
            )
        return self.command if self.available else None

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

    stage = "lock"
    try:
        result = init_project(target, mathpub_url=mathpub_url)
        if lock_flake:
            nix = shutil.which("nix")
            if nix is None:
                raise MathpubError(
                    "MP-GUI-004", "Nix is unavailable; cannot pin the library toolchain"
                )
            subprocess.run(
                [nix, "flake", "lock"],
                cwd=target,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        stage = "git"
        git = shutil.which("git")
        if git is None:
            raise MathpubError("MP-GUI-003", "Git is unavailable; cannot initialize the library")
        subprocess.run(
            [git, "init", "-b", "main"],
            cwd=target,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(
            [git, "add", "--intent-to-add", "--", "."],
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
        if stage == "lock":
            raise MathpubError(
                "MP-GUI-004",
                f"could not pin the library toolchain: {error}",
            ) from error
        raise MathpubError(
            "MP-GUI-003",
            f"could not initialize the private Git repository: {error}",
        ) from error

    return {
        **result,
        "name": name,
        "git_initialized": True,
        "flake_locked": lock_flake,
        "remote_created": False,
    }
