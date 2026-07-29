"""mathpub: reproducible mathematical worksheet publishing."""

import os

__version__ = "0.1.0"


def display_version() -> str:
    """Return the package version with reproducible Nix build identity when available."""
    revision = os.environ.get("MATHPUB_BUILD_REVISION", "").strip()
    return f"{__version__} ({revision})" if revision else __version__
