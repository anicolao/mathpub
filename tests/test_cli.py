import json

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


def test_complete_delivers_html_to_the_active_workspace(capsys, monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"delivered": true}'

    def open_request(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setenv(
        "MATHPUB_WORKSPACE_COMPLETION_URL",
        "http://127.0.0.1:8765/api/agent/completed",
    )
    monkeypatch.setenv("MATHPUB_WORKSPACE_COMPLETION_TOKEN", "completion-secret")
    monkeypatch.setattr("mathpub.completion.urllib.request.urlopen", open_request)

    html = "<h3>Lesson ready</h3><p>Validated the student edition.</p>"
    assert main(["complete", "--html", html, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"] == {"delivered": True, "summary_bytes": len(html)}
    request, timeout = requests[0]
    assert timeout == 5
    assert request.get_header("Authorization") == "Bearer completion-secret"
    assert json.loads(request.data) == {"html": html}


def test_complete_requires_a_gui_launched_agent(capsys, monkeypatch):
    monkeypatch.delenv("MATHPUB_WORKSPACE_COMPLETION_URL", raising=False)
    monkeypatch.delenv("MATHPUB_WORKSPACE_COMPLETION_TOKEN", raising=False)

    assert main(["complete", "--html", "<p>Done.</p>", "--json"]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "MP-GUI-019"
    assert "launched by the MathPub workspace" in payload["error"]["message"]
