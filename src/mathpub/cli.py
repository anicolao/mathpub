"""Command-line entry point for mathpub."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from mathpub import __version__


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="mathpub", description=__doc__)
    result.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser().parse_args(argv)
    return 0
