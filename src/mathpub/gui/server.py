"""Asyncio HTTP & WebSocket server for the mathpub interactive workspace GUI."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import mimetypes
import re
import shlex
import struct
import subprocess
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mathpub import display_version
from mathpub.config import Project, find_project
from mathpub.errors import MathpubError
from mathpub.gui.libraries import LibraryHistory, open_authoring_library
from mathpub.gui.onboarding import (
    STARTER_PROMPT,
    AgentConfiguration,
    create_authoring_library,
)
from mathpub.gui.source_edit import SOURCE_EDIT_LIMIT, load_tex_source, save_tex_source
from mathpub.gui.synctex import SyncTeXError, spatial_index
from mathpub.gui.terminal import PTYManager
from mathpub.gui.watch import IncrementalPreviewWatcher

STATIC_DIR = Path(__file__).parent / "static"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
HTTP_REASONS = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    413: "Content Too Large",
    500: "Internal Server Error",
}
FEEDBACK_LIMIT = 2000
REQUEST_BODY_LIMIT = 16_384
SOURCE_REQUEST_BODY_LIMIT = SOURCE_EDIT_LIMIT * 2 + 16_384
# Two device pixels per 96-DPI CSS reference pixel keeps previews sharp on HiDPI displays.
PDF_PREVIEW_DPI = 192


def _websocket_accept_key(sec_key: str) -> str:
    combined = (sec_key + WS_GUID).encode()
    return base64.b64encode(hashlib.sha1(combined).digest()).decode()


def _decode_ws_frame(data: bytes) -> tuple[int, str | bytes] | None:
    if len(data) < 2:
        return None
    byte1, byte2 = data[0], data[1]
    opcode = byte1 & 0x0F
    is_masked = bool(byte2 & 0x80)
    payload_len = byte2 & 0x7F

    offset = 2
    if payload_len == 126:
        if len(data) < 4:
            return None
        payload_len = struct.unpack("!H", data[2:4])[0]
        offset = 4
    elif payload_len == 127:
        if len(data) < 10:
            return None
        payload_len = struct.unpack("!Q", data[2:10])[0]
        offset = 10

    if is_masked:
        if len(data) < offset + 4:
            return None
        masks = data[offset : offset + 4]
        offset += 4
        raw_payload = data[offset : offset + payload_len]
        payload = bytes(b ^ masks[i % 4] for i, b in enumerate(raw_payload))
    else:
        payload = data[offset : offset + payload_len]

    if opcode == 0x1:  # Text frame
        return opcode, payload.decode(errors="replace")
    return opcode, payload


def _encode_ws_frame(data: str | bytes, opcode: int = 0x1) -> bytes:
    payload = data.encode() if isinstance(data, str) else data
    length = len(payload)

    header = bytearray()
    header.append(0x80 | opcode)  # FIN bit + opcode

    if length <= 125:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))

    return bytes(header) + payload


def _close_writer(writer: asyncio.StreamWriter) -> None:
    with contextlib.suppress(Exception):
        writer.close()


def _json_response(status: int, payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, sort_keys=True).encode()
    reason = HTTP_REASONS[status]
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode() + body


def _open_pdf_in_preview(pdf_path: Path) -> None:
    """Ask macOS Launch Services to open one PDF in Preview."""
    subprocess.run(
        ["/usr/bin/open", "-a", "Preview", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _default_native_preview_opener() -> Callable[[Path], None] | None:
    if sys.platform == "darwin" and Path("/usr/bin/open").is_file():
        return _open_pdf_in_preview
    return None


def _feedback_prompt(message: dict[str, object]) -> str | None:
    """Convert validated element feedback into one safe terminal input line."""
    fields = ("component_id", "fragment", "authored_source", "feedback")
    if not all(isinstance(message.get(field), str) for field in fields):
        return None

    component_id = str(message["component_id"])
    fragment = str(message["fragment"])
    authored_source = str(message["authored_source"])
    printable_feedback = "".join(
        character if character.isprintable() else " " for character in str(message["feedback"])
    )
    feedback = " ".join(printable_feedback.split())
    if (
        not IDENTIFIER_RE.fullmatch(component_id)
        or not IDENTIFIER_RE.fullmatch(fragment)
        or not SOURCE_PATH_RE.fullmatch(authored_source)
        or ".." in Path(authored_source).parts
        or len(authored_source) > 500
        or not feedback
        or len(feedback) > FEEDBACK_LIMIT
    ):
        return None

    source_kind = "slide" if fragment == "slide" else "component"
    return (
        f"Review mathpub {source_kind} {component_id} ({fragment}, {authored_source}): {feedback}"
    )


def _publication_output_metadata(
    manifest_path: Path,
    manifest: dict[str, object],
    output: dict[str, object],
) -> tuple[Path, dict[str, object]]:
    """Describe one built PDF and whether its SyncTeX mapping artifacts are usable."""
    edition = manifest_path.parent
    output_name = str(output.get("path", ""))
    output_path = (edition / output_name).resolve()
    stem = Path(output_name).stem
    synctex_name = str(output.get("synctex", f"{stem}.synctex.gz"))
    required = {
        "SyncTeX data": edition / synctex_name,
        "generated TeX": edition / "generated-tex" / f"{stem}.tex",
        "source map": edition / "generated-tex" / "source-map.json",
    }
    missing = [label for label, artifact in required.items() if not artifact.is_file()]
    publication_path = str(manifest.get("publication_path", ""))
    root_seed = str(manifest.get("root_seed", ""))
    variant = str(manifest.get("variant", ""))
    rebuild_command = None
    if publication_path and root_seed and variant:
        rebuild_command = shlex.join(
            [
                "nix",
                "run",
                ".#mathpub",
                "--",
                "build",
                publication_path,
                "--seed",
                root_seed,
                "--variant",
                variant,
                "--replace",
                "--json",
            ]
        )

    metadata: dict[str, object] = {
        "publication_id": manifest.get("publication_id"),
        "variant": manifest.get("variant"),
        "projection": output.get("projection"),
        "pages": output.get("pages", 1),
        "lesson_ids": manifest.get("lesson_ids", []),
        "publication_path": manifest.get("publication_path"),
        "root_seed": str(manifest.get("root_seed", "")),
        "font_family": manifest.get("font_family"),
        "synctex_ready": not missing,
        "mapping_error": f"Missing {', '.join(missing)}" if missing else None,
        "mapping_rebuild_command": rebuild_command,
    }
    return output_path, metadata


class WorkspaceServer:
    """Workspace HTTP & WebSocket server for mathpub GUI."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        *,
        project_root: Path | None = None,
        agent_command: list[str] | None = None,
        agent_label: str = "Antigravity",
        lock_libraries: bool = True,
        mathpub_url: str = "github:anicolao/mathpub",
        library_creator: Callable[..., dict[str, object]] = create_authoring_library,
        library_history: LibraryHistory | None = None,
        build_version: str | None = None,
        native_preview_opener: Callable[[Path], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.library_history = library_history or LibraryHistory.default()
        self.project_root = self._initial_project_root(project_root)
        self.agent = (
            AgentConfiguration.from_environment()
            if agent_command is None
            else AgentConfiguration(agent_label, tuple(agent_command))
        )
        self.lock_libraries = lock_libraries
        self.mathpub_url = mathpub_url
        self.library_creator = library_creator
        self.build_version = build_version or display_version()
        self.native_preview_opener = native_preview_opener or _default_native_preview_opener()
        self.source_edit_lock = asyncio.Lock()

    def _initial_project_root(self, project_root: Path | None) -> Path | None:
        try:
            return find_project(project_root).root
        except MathpubError as error:
            if error.code == "MP-SRC-004" and project_root is None:
                recent = self.library_history.most_recent()
                return recent.root if recent is not None else None
            if error.code == "MP-SRC-004":
                return None
            raise

    def _project(self) -> Project | None:
        if self.project_root is None:
            return None
        try:
            return find_project(self.project_root)
        except MathpubError:
            return None

    def _workspace_payload(self) -> dict[str, object]:
        project = self._project()
        root = project.root if project is not None else None
        return {
            "project": project.config["project"] if project is not None else None,
            "root": str(root) if root is not None else None,
            "default_parent": str(root.parent if root is not None else Path.home()),
            "recent_libraries": self.library_history.recent(),
            "agent": self.agent.payload(root),
            "starter_prompt": STARTER_PROMPT,
            "version": self.build_version,
            "native_pdf_viewer": {
                "available": self.native_preview_opener is not None,
                "label": "Preview",
            },
        }

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            header_bytes = await reader.read(8192)
            if not header_bytes:
                _close_writer(writer)
                return
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            _close_writer(writer)
            return

        header_block, separator, initial_body = header_bytes.partition(b"\r\n\r\n")
        if not separator:
            _close_writer(writer)
            return
        header_text = header_block.decode(errors="ignore")
        lines = header_text.split("\r\n")
        if not lines:
            _close_writer(writer)
            return

        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 2:
            _close_writer(writer)
            return

        method = parts[0]
        path = parts[1]
        headers = {}
        for line in lines[1:]:
            key, separator, value = line.partition(":")
            if separator:
                headers[key.strip().lower()] = value.strip()

        # Handle WebSocket Handshake
        if "Upgrade: websocket" in header_text or "upgrade: websocket" in header_text:
            key_match = re.search(r"Sec-WebSocket-Key:\s*(.+)", header_text, re.IGNORECASE)
            if key_match:
                sec_key = key_match.group(1).strip()
                accept_key = _websocket_accept_key(sec_key)
                response = (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
                )
                writer.write(response.encode())
                await writer.drain()
                await self._run_terminal_websocket(reader, writer)
                return

        # Handle HTTP API & Static File Requests
        if path == "/api/health":
            body = json.dumps({"status": "ok", "version": self.build_version}).encode()
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path == "/api/workspace":
            writer.write(_json_response(200, self._workspace_payload()))
            await writer.drain()
            _close_writer(writer)
            return

        if path == "/api/pdf/open" and method == "POST":
            project = self._project()
            content_type = headers.get("content-type", "")
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = -1
            if project is None:
                response = _json_response(404, {"error": "no authoring library is open"})
            elif not content_type.lower().startswith("application/json"):
                response = _json_response(400, {"error": "request body must use application/json"})
            elif content_length < 0 or content_length > REQUEST_BODY_LIMIT:
                response = _json_response(400, {"error": "invalid request body length"})
            elif self.native_preview_opener is None:
                response = _json_response(
                    400,
                    {"error": "the native Preview application is available only on macOS"},
                )
            else:
                body = initial_body
                remaining = content_length - len(body)
                if remaining > 0:
                    try:
                        body += await reader.readexactly(remaining)
                    except asyncio.IncompleteReadError:
                        body = b""
                try:
                    payload = json.loads(body[:content_length])
                    pdf_rel_path = payload.get("path")
                except (json.JSONDecodeError, AttributeError):
                    pdf_rel_path = None
                if not isinstance(pdf_rel_path, str) or not pdf_rel_path:
                    response = _json_response(400, {"error": "PDF path must be a non-empty string"})
                else:
                    target_pdf = (project.root / pdf_rel_path).resolve()
                    if (
                        not target_pdf.is_relative_to(project.root)
                        or target_pdf.suffix.lower() != ".pdf"
                        or not target_pdf.is_file()
                    ):
                        response = _json_response(
                            404,
                            {"error": "PDF does not exist in the current authoring library"},
                        )
                    else:
                        try:
                            await asyncio.to_thread(self.native_preview_opener, target_pdf)
                        except (OSError, subprocess.SubprocessError) as error:
                            response = _json_response(
                                500,
                                {"error": f"could not open PDF in Preview: {error}"},
                            )
                        else:
                            response = _json_response(
                                200,
                                {"opened": pdf_rel_path, "viewer": "Preview"},
                            )
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        parsed_path = urlparse(path)
        if parsed_path.path == "/api/source" and method == "GET":
            project = self._project()
            if project is None:
                response = _json_response(404, {"error": "no authoring library is open"})
            else:
                source = parse_qs(parsed_path.query).get("path", [""])[0]
                try:
                    document = await asyncio.to_thread(load_tex_source, project, source)
                except MathpubError as error:
                    status = 404 if error.code == "MP-GUI-011" else 400
                    response = _json_response(
                        status,
                        {
                            "error": error.message,
                            "code": error.code,
                            "details": error.details,
                        },
                    )
                else:
                    response = _json_response(200, {"source": document})
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if parsed_path.path == "/api/source" and method == "PUT":
            project = self._project()
            content_type = headers.get("content-type", "")
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = -1
            if project is None:
                response = _json_response(404, {"error": "no authoring library is open"})
            elif not content_type.lower().startswith("application/json"):
                response = _json_response(400, {"error": "request body must use application/json"})
            elif content_length < 0:
                response = _json_response(400, {"error": "invalid request body length"})
            elif content_length > SOURCE_REQUEST_BODY_LIMIT:
                response = _json_response(413, {"error": "source edit request is too large"})
            else:
                body = initial_body
                remaining = content_length - len(body)
                if remaining > 0:
                    try:
                        body += await reader.readexactly(remaining)
                    except asyncio.IncompleteReadError:
                        body = b""
                try:
                    payload = json.loads(body[:content_length])
                    async with self.source_edit_lock:
                        result = await asyncio.to_thread(
                            save_tex_source,
                            project,
                            payload.get("path"),
                            payload.get("content"),
                            payload.get("revision"),
                        )
                except (json.JSONDecodeError, AttributeError):
                    response = _json_response(400, {"error": "request body must be a JSON object"})
                except MathpubError as error:
                    status = {
                        "MP-GUI-011": 404,
                        "MP-GUI-012": 409,
                        "MP-GUI-013": 500,
                        "MP-GUI-014": 409,
                    }.get(error.code, 400)
                    response = _json_response(
                        status,
                        {
                            "error": error.message,
                            "code": error.code,
                            "details": error.details,
                        },
                    )
                else:
                    response = _json_response(200, {"source": result})
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path == "/api/libraries" and method == "POST":
            content_type = headers.get("content-type", "")
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = -1
            if not content_type.lower().startswith("application/json"):
                response = _json_response(400, {"error": "request body must use application/json"})
            elif content_length < 0 or content_length > REQUEST_BODY_LIMIT:
                response = _json_response(400, {"error": "invalid request body length"})
            else:
                body = initial_body
                remaining = content_length - len(body)
                if remaining > 0:
                    try:
                        body += await reader.readexactly(remaining)
                    except asyncio.IncompleteReadError:
                        body = b""
                try:
                    payload = json.loads(body[:content_length])
                    parent = payload.get("parent")
                    name = payload.get("name")
                    result = await asyncio.to_thread(
                        self.library_creator,
                        parent,
                        name,
                        mathpub_url=self.mathpub_url,
                        lock_flake=self.lock_libraries,
                    )
                except (json.JSONDecodeError, AttributeError):
                    response = _json_response(400, {"error": "request body must be a JSON object"})
                except MathpubError as error:
                    status = 409 if error.code == "MP-GUI-002" else 400
                    response = _json_response(
                        status,
                        {
                            "error": error.message,
                            "code": error.code,
                            "details": error.details,
                        },
                    )
                except Exception as error:
                    response = _json_response(500, {"error": str(error)})
                else:
                    self.project_root = Path(str(result["root"])).resolve()
                    persistence_warning = None
                    try:
                        self.library_history.remember(self.project_root)
                    except MathpubError as error:
                        persistence_warning = error.message
                    response = _json_response(
                        201,
                        {
                            "library": result,
                            "workspace": self._workspace_payload(),
                            "warning": persistence_warning,
                        },
                    )
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path == "/api/libraries/open" and method == "POST":
            content_type = headers.get("content-type", "")
            try:
                content_length = int(headers.get("content-length", "0"))
            except ValueError:
                content_length = -1
            if not content_type.lower().startswith("application/json"):
                response = _json_response(400, {"error": "request body must use application/json"})
            elif content_length < 0 or content_length > REQUEST_BODY_LIMIT:
                response = _json_response(400, {"error": "invalid request body length"})
            else:
                body = initial_body
                remaining = content_length - len(body)
                if remaining > 0:
                    try:
                        body += await reader.readexactly(remaining)
                    except asyncio.IncompleteReadError:
                        body = b""
                try:
                    payload = json.loads(body[:content_length])
                    project = open_authoring_library(payload.get("path"))
                except (json.JSONDecodeError, AttributeError):
                    response = _json_response(400, {"error": "request body must be a JSON object"})
                except MathpubError as error:
                    response = _json_response(
                        400,
                        {
                            "error": error.message,
                            "code": error.code,
                            "details": error.details,
                        },
                    )
                else:
                    self.project_root = project.root
                    persistence_warning = None
                    try:
                        self.library_history.remember(project.root)
                    except MathpubError as error:
                        persistence_warning = error.message
                    response = _json_response(
                        200,
                        {
                            "library": {
                                "name": project.config["project"],
                                "root": str(project.root),
                            },
                            "workspace": self._workspace_payload(),
                            "warning": persistence_warning,
                        },
                    )
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path.startswith("/api/publications"):
            project = self._project()
            if project is None:
                writer.write(_json_response(200, {"publications": []}))
                await writer.drain()
                _close_writer(writer)
                return
            build_dir = project.root / project.config.get("build_dir", "build")
            metadata_by_path: dict[Path, dict[str, object]] = {}
            if build_dir.exists():
                for manifest_path in build_dir.glob("*/*/manifest.json"):
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    for output in manifest.get("outputs", []):
                        output_path, metadata = _publication_output_metadata(
                            manifest_path,
                            manifest,
                            output,
                        )
                        metadata_by_path[output_path] = metadata

            pdf_files = []
            if build_dir.exists():
                for pdf_path in sorted(build_dir.rglob("*.pdf")):
                    rel_path = str(pdf_path.relative_to(project.root))
                    pdf_files.append(
                        {
                            "name": pdf_path.name,
                            "path": rel_path,
                            **metadata_by_path.get(
                                pdf_path.resolve(),
                                {
                                    "synctex_ready": False,
                                    "mapping_error": "No edition manifest describes this PDF",
                                    "mapping_rebuild_command": None,
                                },
                            ),
                        }
                    )

            body = json.dumps({"publications": pdf_files}).encode()
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path.startswith("/api/synctex/boxes"):
            query = parse_qs(urlparse(path).query)
            publication_id = query.get("publication_id", [""])[0]
            variant = query.get("variant", [""])[0]
            projection = query.get("projection", [""])[0]
            page_text = query.get("page", [""])[0]
            identifiers = (publication_id, variant, projection)
            try:
                page_number = int(page_text)
            except ValueError:
                page_number = 0
            if not all(IDENTIFIER_RE.fullmatch(value) for value in identifiers) or page_number < 1:
                response = _json_response(
                    400,
                    {
                        "error": "invalid SyncTeX query",
                        "required": [
                            "publication_id",
                            "variant",
                            "projection",
                            "page",
                        ],
                    },
                )
            else:
                try:
                    project = self._project()
                    if project is None:
                        raise SyncTeXError("no authoring library is open")
                    payload = spatial_index(
                        project.root,
                        publication_id,
                        variant,
                        projection,
                        page_number,
                        build_dir=project.config.get("build_dir", "build"),
                    )
                except SyncTeXError as error:
                    response = _json_response(404, {"error": str(error)})
                else:
                    response = _json_response(200, payload)
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path.startswith("/api/pdf-preview"):
            parsed = urlparse(path)
            query = parse_qs(parsed.query)
            pdf_rel_path = query.get("path", [""])[0]
            try:
                page_number = int(query.get("page", ["1"])[0])
            except ValueError:
                page_number = 0

            if pdf_rel_path and page_number >= 1:
                project = self._project()
                project_root = project.root if project is not None else None
                if project_root is None:
                    response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                    writer.write(response)
                    await writer.drain()
                    _close_writer(writer)
                    return
                target_pdf = (project_root / pdf_rel_path).resolve()
                if (
                    target_pdf.exists()
                    and target_pdf.is_file()
                    and target_pdf.is_relative_to(project_root)
                ):
                    try:
                        rendered = subprocess.run(
                            [
                                "pdftocairo",
                                "-png",
                                "-singlefile",
                                "-f",
                                str(page_number),
                                "-l",
                                str(page_number),
                                "-r",
                                str(PDF_PREVIEW_DPI),
                                str(target_pdf),
                                "-",
                            ],
                            check=True,
                            capture_output=True,
                            timeout=30,
                        )
                    except (OSError, subprocess.SubprocessError):
                        response = (
                            b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\n\r\n"
                        )
                    else:
                        content = rendered.stdout
                        response = (
                            f"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\n"
                            f"Content-Length: {len(content)}\r\n\r\n"
                        ).encode() + content
                    writer.write(response)
                    await writer.drain()
                    _close_writer(writer)
                    return

            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path.startswith("/api/pdf"):
            parsed = urlparse(path)
            query = parse_qs(parsed.query)
            pdf_rel_path = query.get("path", [""])[0]

            if pdf_rel_path:
                project = self._project()
                project_root = project.root if project is not None else None
                if project_root is None:
                    response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                    writer.write(response)
                    await writer.drain()
                    _close_writer(writer)
                    return
                target_pdf = (project_root / pdf_rel_path).resolve()
                if (
                    target_pdf.exists()
                    and target_pdf.is_file()
                    and target_pdf.is_relative_to(project_root)
                ):
                    content = target_pdf.read_bytes()
                    response = (
                        f"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
                        f'Content-Disposition: inline; filename="{target_pdf.name}"\r\n'
                        f"Content-Length: {len(content)}\r\n\r\n"
                    ).encode() + content
                    writer.write(response)
                    await writer.drain()
                    _close_writer(writer)
                    return

            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        # Serve Static Assets
        target_file = (STATIC_DIR / path.lstrip("/")).resolve()
        if (
            path == "/"
            or not target_file.exists()
            or not str(target_file).startswith(str(STATIC_DIR))
        ):
            target_file = STATIC_DIR / "index.html"

        if target_file.exists() and target_file.is_file():
            content = target_file.read_bytes()
            mime_type, _ = mimetypes.guess_type(str(target_file))
            mime_type = mime_type or "application/octet-stream"
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: {mime_type}\r\n"
                f"Content-Length: {len(content)}\r\n\r\n"
            ).encode() + content
            writer.write(response)
            await writer.drain()

        _close_writer(writer)

    async def _run_terminal_websocket(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        project = self._project()
        terminal_root = project.root if project is not None else Path.cwd()
        pty = PTYManager(cwd=str(terminal_root))
        pty.start(rows=24, cols=80)

        loop = asyncio.get_running_loop()
        write_lock = asyncio.Lock()

        async def send_event(event: dict[str, object]) -> None:
            try:
                async with write_lock:
                    writer.write(_encode_ws_frame(json.dumps(event), opcode=0x1))
                    await writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                return

        watcher = IncrementalPreviewWatcher(project, send_event) if project is not None else None

        async def read_pty_to_ws() -> None:
            while pty.is_alive():
                data = await loop.run_in_executor(None, pty.read, 4096)
                if data:
                    frame = _encode_ws_frame(data, opcode=0x2)  # Binary frame
                    async with write_lock:
                        writer.write(frame)
                        await writer.drain()
                else:
                    await asyncio.sleep(0.02)

        async def read_ws_to_pty() -> None:
            while pty.is_alive():
                try:
                    data = await reader.read(4096)
                    if not data:
                        break
                    decoded = _decode_ws_frame(data)
                    if decoded:
                        opcode, payload = decoded
                        if opcode == 0x8:  # Close frame
                            break
                        if isinstance(payload, str):
                            try:
                                msg = json.loads(payload)
                                if msg.get("type") == "resize":
                                    pty.set_size(msg.get("rows", 24), msg.get("cols", 80))
                                    continue
                                if msg.get("type") == "input":
                                    pty.write(msg["data"].encode())
                                    continue
                                if msg.get("type") == "feedback":
                                    prompt = _feedback_prompt(msg)
                                    if prompt is not None:
                                        pty.write(prompt.encode())
                                    continue
                                if msg.get("type") == "start-agent":
                                    command = self.agent.shell_command_for(
                                        project.root if project is not None else None
                                    )
                                    if command is None:
                                        await send_event(
                                            {
                                                "type": "agent-unavailable",
                                                "label": self.agent.label,
                                            }
                                        )
                                    else:
                                        pty.write(b"\x15" + command.encode() + b"\r")
                                        await send_event(
                                            {
                                                "type": "agent-started",
                                                "label": self.agent.label,
                                            }
                                        )
                                    continue
                                if msg.get("type") == "starter-prompt":
                                    pty.write(STARTER_PROMPT.encode())
                                    await send_event({"type": "starter-prompt-inserted"})
                                    continue
                                if msg.get("type") == "watch-preview":
                                    selection = watcher.select(msg) if watcher is not None else None
                                    preparation_error = None
                                    if selection is not None:
                                        try:
                                            await asyncio.to_thread(
                                                watcher.prepare,
                                                selection,
                                            )
                                        except Exception as error:
                                            preparation_error = str(error)
                                    await send_event(
                                        {
                                            "type": "preview-watch-ready"
                                            if selection is not None and preparation_error is None
                                            else "preview-watch-failed",
                                            "error": preparation_error
                                            or (
                                                None
                                                if selection is not None
                                                else "Invalid preview selection"
                                            ),
                                        }
                                    )
                                    continue
                            except json.JSONDecodeError:
                                pass
                            pty.write(payload.encode())
                        elif isinstance(payload, bytes):
                            pty.write(payload)
                except Exception:
                    break

        try:
            await asyncio.gather(read_pty_to_ws(), read_ws_to_pty())
        finally:
            if watcher is not None:
                await watcher.close()
            pty.close()
            writer.close()


def run_workspace_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    browser: str = "webkit",
) -> None:
    import subprocess
    import sys

    server_obj = WorkspaceServer(host, port)

    async def main() -> None:
        server = await asyncio.start_server(server_obj.handle_client, host, port)
        url = f"http://{host}:{port}/"
        print(f"mathpub workspace running at {url}")
        if open_browser:
            if sys.platform == "darwin" and browser in ("webkit", "safari"):
                try:
                    subprocess.run(["open", "-a", "Safari", url], check=False)
                except Exception:
                    webbrowser.open(url)
            else:
                webbrowser.open(url)
        async with server:
            await server.serve_forever()

    asyncio.run(main())
