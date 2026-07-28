"""Fresh-process helper for configuring a controlling PTY before command execution."""

from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import termios


def main() -> None:
    """Become a session-leading PTY child, then replace this helper with the command."""
    if len(sys.argv) < 4:
        raise SystemExit("PTY child helper requires a slave fd, working directory, and command")

    slave_fd = int(sys.argv[1])
    cwd = sys.argv[2]
    command = sys.argv[3:]

    os.setsid()
    with contextlib.suppress(Exception):
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

    os.dup2(slave_fd, 0)
    os.dup2(slave_fd, 1)
    os.dup2(slave_fd, 2)
    if slave_fd > 2:
        os.close(slave_fd)

    os.chdir(cwd)
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()
