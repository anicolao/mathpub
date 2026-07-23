"""Pseudo-terminal (PTY) manager for embedding shell and CLI agents in mathpub workspace."""

from __future__ import annotations

import contextlib
import fcntl
import os
import pty
import struct
import termios


class PTYManager:
    """Manages a Unix pseudo-terminal (PTY) child process for embedded terminal emulation."""

    def __init__(self, command: list[str] | None = None, cwd: str | None = None) -> None:
        if command:
            self.command = command
        else:
            shell_bin = os.environ.get("SHELL", "/bin/bash")
            if "zsh" in shell_bin:
                self.command = [shell_bin, "-f", "-i"]
            elif "bash" in shell_bin:
                self.command = [shell_bin, "--noprofile", "--norc", "-i"]
            else:
                self.command = [shell_bin]

        self.cwd = cwd or os.getcwd()
        self.master_fd: int | None = None
        self.pid: int | None = None

    def start(self, rows: int = 24, cols: int = 80) -> None:
        """Spawn the child process with a dedicated master/slave PTY pair."""
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd

        self.set_size(rows, cols)

        pid = os.fork()
        if pid == 0:  # Child process
            os.close(master_fd)
            os.setsid()

            with contextlib.suppress(Exception):
                fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            os.chdir(self.cwd)
            env = dict(os.environ)
            env.pop("PROMPT_COMMAND", None)
            env.pop("ENV", None)
            env.pop("BASH_ENV", None)
            env["TERM"] = "xterm-256color"
            env["COLORTERM"] = "truecolor"
            env["PS1"] = "mathpub$ "
            env["PROMPT"] = "mathpub$ "
            env["ZDOTDIR"] = "/nonexistent"
            env["HISTFILE"] = "/dev/null"
            os.execvpe(self.command[0], self.command, env)
        else:  # Parent process
            os.close(slave_fd)
            self.pid = pid
            # Make master_fd non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def read(self, max_bytes: int = 4096) -> bytes:
        """Read output bytes from the PTY master_fd without blocking."""
        if self.master_fd is None:
            return b""
        try:
            return os.read(self.master_fd, max_bytes)
        except (OSError, ValueError):
            return b""

    def write(self, data: bytes) -> None:
        """Write user/agent input bytes to the PTY master_fd."""
        if self.master_fd is not None:
            with contextlib.suppress(OSError):
                os.write(self.master_fd, data)

    def set_size(self, rows: int, cols: int) -> None:
        """Update terminal dimensions via TIOCSWINSZ ioctl."""
        if self.master_fd is not None:
            with contextlib.suppress(Exception):
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def is_alive(self) -> bool:
        """Check if child process is still active."""
        if self.pid is None:
            return False
        try:
            pid, _ = os.waitpid(self.pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False

    def close(self) -> None:
        """Clean up PTY descriptors and terminate child process."""
        if self.master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = None
        if self.pid is not None and self.is_alive():
            with contextlib.suppress(OSError):
                os.kill(self.pid, 15)  # SIGTERM
                os.waitpid(self.pid, 0)
