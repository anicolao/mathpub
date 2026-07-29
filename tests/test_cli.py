from mathpub import __version__, display_version
from mathpub.cli import main


def test_version(capsys, monkeypatch):
    monkeypatch.delenv("MATHPUB_BUILD_REVISION", raising=False)
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out.strip() == f"mathpub {__version__}"


def test_version_includes_nix_build_revision(capsys, monkeypatch):
    monkeypatch.setenv("MATHPUB_BUILD_REVISION", "8aafec7")
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert display_version() == "0.1.0 (8aafec7)"
    assert capsys.readouterr().out.strip() == "mathpub 0.1.0 (8aafec7)"
