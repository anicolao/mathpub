from mathpub import __version__
from mathpub.cli import main


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out.strip() == f"mathpub {__version__}"
