"""Asyncio HTTP & WebSocket server for the mathpub interactive workspace GUI."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import mimetypes
import re
import struct
import webbrowser
from pathlib import Path

from mathpub.gui.terminal import PTYManager

STATIC_DIR = Path(__file__).parent / "static"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


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


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    with contextlib.suppress(Exception):
        writer.close()
        await writer.wait_closed()


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
                await _close_writer(writer)
                return
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            await _close_writer(writer)
            return

        header_text = header_bytes.decode(errors="ignore")
        lines = header_text.split("\r\n")
        if not lines:
            await _close_writer(writer)
            return

        request_line = lines[0]
        parts = request_line.split()
        if len(parts) < 2:
            await _close_writer(writer)
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
            await _close_writer(writer)
            return

        if path.startswith("/api/publications"):
            build_dir = Path.cwd() / "build"
            pdf_files = []
            if build_dir.exists():
                for pdf_path in sorted(build_dir.rglob("*.pdf")):
                    rel_path = str(pdf_path.relative_to(Path.cwd()))
                    pdf_files.append({"name": pdf_path.name, "path": rel_path})

            body = json.dumps({"publications": pdf_files}).encode()
            response = (
                f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            writer.write(response)
            await writer.drain()
            await _close_writer(writer)
            return

        if path.startswith("/api/pdf"):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(path)
            query = parse_qs(parsed.query)
            pdf_rel_path = query.get("path", [""])[0]

            if pdf_rel_path:
                target_pdf = (Path.cwd() / pdf_rel_path).resolve()
                if (
                    target_pdf.exists()
                    and target_pdf.is_file()
                    and str(target_pdf).startswith(str(Path.cwd()))
                ):
                    content = target_pdf.read_bytes()
                    response = (
                        f"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\n"
                        f"Content-Length: {len(content)}\r\n\r\n"
                    ).encode() + content
                    writer.write(response)
                    await writer.drain()
                    await _close_writer(writer)
                    return

            response = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
            writer.write(response)
            await writer.drain()
            await _close_writer(writer)
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

        await _close_writer(writer)

    async def _run_terminal_websocket(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        pty = PTYManager()
        pty.start(rows=24, cols=80)

        loop = asyncio.get_running_loop()

        async def read_pty_to_ws() -> None:
            while pty.is_alive():
                data = await loop.run_in_executor(None, pty.read, 4096)
                if data:
                    frame = _encode_ws_frame(data, opcode=0x2)  # Binary frame
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
