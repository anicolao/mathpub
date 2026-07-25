"""Native Tauri workspace smoke test driven through tauri-driver on Linux."""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.helpers.gui_step_helper import GUIStepHelper

DRIVER_URL = "http://127.0.0.1:4444"
DRIVER_PORTS = (4444, 4445)
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


class WebDriverClient:
    def __init__(self, application: Path) -> None:
        response = self._request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "wry",
                        "tauri:options": {"application": str(application)},
                    }
                }
            },
        )
        value = response.get("value", response)
        self.session_id = response.get("sessionId") or value.get("sessionId")
        if not self.session_id:
            raise AssertionError(f"tauri-driver did not return a session ID: {response}")

    @staticmethod
    def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{DRIVER_URL}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise AssertionError(f"WebDriver {method} {path} failed: {detail}") from error
        return json.loads(raw) if raw else {}

    def find_text(self, selector: str) -> str:
        response = self._request(
            "POST",
            f"/session/{self.session_id}/element",
            {"using": "css selector", "value": selector},
        )
        element = response["value"][ELEMENT_KEY]
        text = self._request(
            "GET",
            f"/session/{self.session_id}/element/{element}/text",
        )
        return str(text["value"])

    def execute(self, script: str) -> Any:
        response = self._request(
            "POST",
            f"/session/{self.session_id}/execute/sync",
            {"script": script, "args": []},
        )
        return response["value"]

    def screenshot(self) -> bytes:
        response = self._request("GET", f"/session/{self.session_id}/screenshot")
        return base64.b64decode(response["value"])

    def close(self) -> None:
        self._request("DELETE", f"/session/{self.session_id}")


def _wait_for_driver(process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"tauri-driver exited during startup with {process.returncode}")
        try:
            for port in DRIVER_PORTS:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    pass
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("timed out waiting for tauri-driver")


def _wait_for_text(
    client: WebDriverClient,
    selector: str,
    expected: str,
    *,
    contains: bool = False,
) -> None:
    deadline = time.monotonic() + 30
    last_text = None
    while time.monotonic() < deadline:
        try:
            last_text = client.find_text(selector)
            matches = expected in last_text if contains else last_text == expected
            if matches:
                return
        except (AssertionError, KeyError):
            pass
        time.sleep(0.1)
    raise AssertionError(f"{selector} did not render {expected!r}; last text was {last_text!r}")


def _wait_for_preview(client: WebDriverClient) -> dict[str, int]:
    deadline = time.monotonic() + 30
    dimensions = None
    while time.monotonic() < deadline:
        dimensions = client.execute(
            """
            return {
              width: window.innerWidth,
              height: window.innerHeight,
              previewWidth: document.getElementById('pdf-preview')?.naturalWidth || 0
            };
            """
        )
        if (
            dimensions["width"] >= 960
            and dimensions["height"] >= 600
            and dimensions["previewWidth"] > 0
        ):
            return dimensions
        time.sleep(0.1)
    raise AssertionError(f"native workspace preview did not render: {dimensions!r}")


def test_packaged_tauri_workspace_launches_and_renders():
    application_value = os.environ.get("MATHPUB_GUI_BINARY")
    driver_value = os.environ.get("TAURI_DRIVER_BINARY")
    if not application_value or not driver_value:
        pytest.skip("run with nix run .#mathpub-gui-e2e on Linux")

    application = Path(application_value)
    driver_binary = Path(driver_value)
    assert application.is_file()
    assert application.name == "MathPub"
    assert driver_binary.is_file()

    driver_process = subprocess.Popen([str(driver_binary)])
    client = None
    try:
        _wait_for_driver(driver_process)
        client = WebDriverClient(application)

        _wait_for_text(client, ".logo", "mathpub")
        _wait_for_text(client, ".subtitle", "Interactive Workspace", contains=True)
        _wait_for_text(client, "#status-terminal", "PTY Connected")
        dimensions = _wait_for_preview(client)

        artifact = Path(
            os.environ.get(
                "MATHPUB_GUI_NATIVE_SCREENSHOT",
                "build/e2e/tauri-driver.png",
            )
        )
        screenshot_size = GUIStepHelper.verify_native_capture(client.screenshot(), artifact)
        assert screenshot_size[0] >= dimensions["width"]
        assert screenshot_size[1] >= dimensions["height"]
    finally:
        try:
            if client is not None:
                client.close()
        finally:
            driver_process.terminate()
            try:
                driver_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                driver_process.kill()
                driver_process.wait(timeout=10)
