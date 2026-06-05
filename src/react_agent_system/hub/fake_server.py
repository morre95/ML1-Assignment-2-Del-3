"""Local fake RunPod hub for offline development and tests."""

from __future__ import annotations

import argparse
import html
import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8089
DEFAULT_PASSWORD = "dev-hub-password"
DEFAULT_MAX_PER_AGENT = 20
DEFAULT_MAX_GLOBAL = 500
MAX_MESSAGE_CHARS = 4096
MAX_FILE_BYTES = 32_768
MAX_FILES = 50


class FakeHubError(ValueError):
    """Raised for client-visible fake hub request errors."""

    def __init__(self, message: str, status: HTTPStatus) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FakeHubConfig:
    password: str = DEFAULT_PASSWORD
    max_per_agent: int = DEFAULT_MAX_PER_AGENT
    max_global: int = DEFAULT_MAX_GLOBAL
    max_message_chars: int = MAX_MESSAGE_CHARS
    max_file_bytes: int = MAX_FILE_BYTES
    max_files: int = MAX_FILES


@dataclass
class FakeHubStore:
    """Thread-safe in-memory store mirroring the new hub API."""

    config: FakeHubConfig
    messages: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    billboard: dict[str, Any] = field(
        default_factory=lambda: {"content": "", "updated_by": "", "updated_at": ""}
    )
    paused: bool = False
    manager: str = ""
    allowed_agents: dict[str, bool] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_message(self, agent_name: str, content: str) -> dict[str, Any]:
        agent_name = agent_name.strip()
        content = content.strip()
        if not agent_name:
            raise FakeHubError("agent_name is required", HTTPStatus.BAD_REQUEST)
        if not content:
            raise FakeHubError("content is required", HTTPStatus.BAD_REQUEST)
        if len(content) > self.config.max_message_chars:
            raise FakeHubError("message too long", HTTPStatus.BAD_REQUEST)

        with self._lock:
            if len(self.messages) >= self.config.max_global:
                raise FakeHubError("global message cap reached", HTTPStatus.TOO_MANY_REQUESTS)

            per_agent = self._per_agent_counts()
            if per_agent.get(agent_name, 0) >= self.config.max_per_agent:
                raise FakeHubError("agent message cap reached", HTTPStatus.TOO_MANY_REQUESTS)

            message = {
                "seq": len(self.messages) + 1,
                "agent_name": agent_name,
                "content": content,
                "timestamp": _now(),
            }
            self.messages.append(message)
            return dict(message)

    def get_messages_since(self, since: int) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(message) for message in self.messages if message["seq"] > since]

    def upload_file(self, agent_name: str, filename: str, content: str) -> dict[str, Any]:
        agent_name = agent_name.strip()
        filename = filename.strip()
        if not agent_name:
            raise FakeHubError("agent_name is required", HTTPStatus.BAD_REQUEST)
        if not filename:
            raise FakeHubError("filename is required", HTTPStatus.BAD_REQUEST)
        byte_size = len(content.encode("utf-8"))
        if byte_size > self.config.max_file_bytes:
            raise FakeHubError("file too large", HTTPStatus.BAD_REQUEST)

        with self._lock:
            if filename not in self.files and len(self.files) >= self.config.max_files:
                raise FakeHubError("file cap reached", HTTPStatus.TOO_MANY_REQUESTS)
            self.files[filename] = {
                "filename": filename,
                "content": content,
                "author": agent_name,
                "size": byte_size,
                "updated_at": _now(),
            }
            return {"ok": True, "filename": filename}

    def list_files(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "filename": entry["filename"],
                    "size": entry["size"],
                    "author": entry["author"],
                    "updated_at": entry["updated_at"],
                }
                for entry in sorted(self.files.values(), key=lambda item: item["filename"])
            ]

    def read_file(self, filename: str) -> dict[str, Any]:
        with self._lock:
            entry = self.files.get(filename)
            if entry is None:
                raise FakeHubError("file not found", HTTPStatus.NOT_FOUND)
            return {
                "filename": entry["filename"],
                "content": entry["content"],
                "author": entry["author"],
                "updated_at": entry["updated_at"],
            }

    def set_billboard(self, content: str, updated_by: str) -> dict[str, Any]:
        with self._lock:
            self.billboard = {
                "content": content,
                "updated_by": updated_by,
                "updated_at": _now(),
            }
            return dict(self.billboard)

    def get_billboard(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.billboard)

    def set_controls(
        self,
        paused: bool | None = None,
        manager: str | None = None,
        allowed_agents: dict[str, bool] | None = None,
    ) -> None:
        with self._lock:
            if paused is not None:
                self.paused = paused
            if manager is not None:
                self.manager = manager
            if allowed_agents is not None:
                self.allowed_agents = dict(allowed_agents)

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "paused": self.paused,
                "manager": self.manager,
                "allowed_agents": dict(self.allowed_agents),
                "billboard": dict(self.billboard),
                "files": [
                    {
                        "filename": entry["filename"],
                        "size": entry["size"],
                        "author": entry["author"],
                        "updated_at": entry["updated_at"],
                    }
                    for entry in sorted(self.files.values(), key=lambda item: item["filename"])
                ],
            }

    def dump_messages(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(message) for message in self.messages]

    def _per_agent_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for message in self.messages:
            counts[message["agent_name"]] = counts.get(message["agent_name"], 0) + 1
        return counts


class FakeHubHandler(BaseHTTPRequestHandler):
    """HTTP handler for RunPod-compatible fake hub endpoints."""

    store: FakeHubStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._handle_index()
                return
            self._require_password(params)
            if parsed.path == "/api/messages":
                self._handle_messages(params)
                return
            if parsed.path == "/api/files":
                self._handle_get_files(params)
                return
            if parsed.path == "/api/billboard":
                self._write_json(self.store.get_billboard())
                return
            if parsed.path == "/api/dump":
                self._write_json(
                    {"messages": self.store.dump_messages(), "stats": self.store.state()}
                )
                return
            self._write_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except FakeHubError as exc:
            self._write_json({"error": str(exc)}, exc.status)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
            self._require_password(body)
            if parsed.path in {"/api/message", "/api/seed"}:
                message = self.store.add_message(
                    agent_name=str(body.get("agent_name", "")),
                    content=str(body.get("content", "")),
                )
                self._write_json(
                    {
                        "ok": True,
                        "status": "ok",
                        "seq": message["seq"],
                        "paused": self.store.paused,
                        "manager": self.store.manager,
                        "allowed_agents": dict(self.store.allowed_agents),
                    }
                )
                return
            if parsed.path == "/api/files":
                result = self.store.upload_file(
                    agent_name=str(body.get("agent_name", "")),
                    filename=str(body.get("filename", "")),
                    content=str(body.get("content", "")),
                )
                self._write_json(result)
                return
            if parsed.path == "/api/billboard":
                self._write_json(
                    self.store.set_billboard(
                        content=str(body.get("content", "")),
                        updated_by=str(body.get("agent_name", "")),
                    )
                )
                return
            if parsed.path == "/api/control":
                self.store.set_controls(
                    paused=body.get("paused"),
                    manager=body.get("manager"),
                    allowed_agents=body.get("allowed_agents"),
                )
                self._write_json({"ok": True})
                return
            self._write_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except FakeHubError as exc:
            self._write_json({"error": str(exc)}, exc.status)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)

    def _handle_messages(self, params: dict[str, list[str]]) -> None:
        since_values = params.get("since", ["0"])
        try:
            since = int(since_values[0])
        except ValueError as exc:
            raise FakeHubError("since must be an integer", HTTPStatus.BAD_REQUEST) from exc
        self._write_json(
            {"messages": self.store.get_messages_since(since), "stats": self.store.state()}
        )

    def _handle_get_files(self, params: dict[str, list[str]]) -> None:
        filename = _first_value(params.get("filename"))
        if filename:
            self._write_json(self.store.read_file(filename))
            return
        self._write_json({"files": self.store.list_files()})

    def _handle_index(self) -> None:
        messages = self.store.dump_messages()
        state = self.store.state()
        rows = "\n".join(
            "<tr>"
            f"<td>{message['seq']}</td>"
            f"<td>{html.escape(message['timestamp'])}</td>"
            f"<td>{html.escape(message['agent_name'])}</td>"
            f"<td>{html.escape(message['content'])}</td>"
            "</tr>"
            for message in messages
        )
        file_names = ", ".join(html.escape(file["filename"]) for file in state["files"]) or "none"
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Fake Hub</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem; text-align: left; vertical-align: top; }}
    td:last-child {{ white-space: pre-wrap; }}
    code {{ background: #eee; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Fake Hub</h1>
  <p>Messages: {len(messages)} / {self.store.config.max_global}</p>
  <p>Shared files: {file_names}</p>
  <p>Use <code>/api/dump?password={html.escape(self.store.config.password)}</code> for JSON.</p>
  <table>
    <thead><tr><th>Seq</th><th>Timestamp</th><th>Agent</th><th>Content</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise FakeHubError("JSON body is required", HTTPStatus.BAD_REQUEST)
        raw_body = self.rfile.read(content_length)
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise FakeHubError("invalid JSON body", HTTPStatus.BAD_REQUEST) from exc
        if not isinstance(data, dict):
            raise FakeHubError("JSON body must be an object", HTTPStatus.BAD_REQUEST)
        return data

    def _require_password(self, values: dict[str, Any]) -> None:
        password = _first_value(values.get("password"))
        if password != self.store.config.password:
            raise FakeHubError("wrong password", HTTPStatus.UNAUTHORIZED)

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def build_server(
    host: str,
    port: int,
    config: FakeHubConfig,
) -> ThreadingHTTPServer:
    store = FakeHubStore(config)

    class ConfiguredFakeHubHandler(FakeHubHandler):
        pass

    ConfiguredFakeHubHandler.store = store
    return ThreadingHTTPServer((host, port), ConfiguredFakeHubHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local fake RunPod hub.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--max-per-agent", type=int, default=DEFAULT_MAX_PER_AGENT)
    parser.add_argument("--max-global", type=int, default=DEFAULT_MAX_GLOBAL)
    args = parser.parse_args()

    server = build_server(
        host=args.host,
        port=args.port,
        config=FakeHubConfig(
            password=args.password,
            max_per_agent=args.max_per_agent,
            max_global=args.max_global,
        ),
    )
    print(f"fake hub listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_value(value: Any) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    main()
