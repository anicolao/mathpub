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
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mathpub.config import find_project
from mathpub.gui.synctex import SyncTeXError, spatial_index
from mathpub.gui.terminal import PTYManager
from mathpub.gui.watch import IncrementalPreviewWatcher

STATIC_DIR = Path(__file__).parent / "static"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
HTTP_REASONS = {200: "OK", 400: "Bad Request", 404: "Not Found"}
FEEDBACK_LIMIT = 2000


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

    return f"Review mathpub component {component_id} ({fragment}, {authored_source}): {feedback}"


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

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port

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

        header_text = header_bytes.decode(errors="ignore")
        lines = header_text.split("\r\n")
        if not lines:
            _close_writer(writer)
            return

        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 2:
            _close_writer(writer)
            return

        path = parts[1]

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
            body = json.dumps({"status": "ok", "version": "0.1.0"}).encode()
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            writer.write(response)
            await writer.drain()
            _close_writer(writer)
            return

        if path.startswith("/api/publications"):
            project = find_project()
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
                    project = find_project()
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
                project_root = Path.cwd().resolve()
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
                                "96",
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
                project_root = Path.cwd().resolve()
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
        pty = PTYManager()
        pty.start(rows=24, cols=80)

        loop = asyncio.get_running_loop()
        write_lock = asyncio.Lock()

        async def send_event(event: dict[str, object]) -> None:
            async with write_lock:
                writer.write(_encode_ws_frame(json.dumps(event), opcode=0x1))
                await writer.drain()

        watcher = IncrementalPreviewWatcher(find_project(), send_event)

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
                                if msg.get("type") == "watch-preview":
                                    selection = watcher.select(msg)
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
