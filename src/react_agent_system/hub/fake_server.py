"""Local fake RunPod hub for offline development and tests."""

from __future__ import annotations

import argparse
import html
import json
import threading
from collections import Counter
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
HUMAN_AGENT_NAME = "human"


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


@dataclass
class FakeHubStore:
    """Thread-safe in-memory message store for the fake hub."""

    config: FakeHubConfig
    messages: list[dict[str, Any]] = field(default_factory=list)
    blocked_agents: set[str] = field(default_factory=set)
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
            if agent_name in self.blocked_agents:
                raise FakeHubError("agent is blocked", HTTPStatus.FORBIDDEN)
            if len(self.messages) >= self.config.max_global:
                raise FakeHubError("global message cap reached", HTTPStatus.TOO_MANY_REQUESTS)

            per_agent = Counter(message["agent_name"] for message in self.messages)
            if per_agent[agent_name] >= self.config.max_per_agent:
                raise FakeHubError("agent message cap reached", HTTPStatus.TOO_MANY_REQUESTS)

            message = {
                "seq": len(self.messages) + 1,
                "agent_name": agent_name,
                "content": content,
                "timestamp": (
                    datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
                ),
            }
            self.messages.append(message)
            return dict(message)

    def get_messages_since(self, since: int) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(message) for message in self.messages if message["seq"] > since]

    def dump_messages(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(message) for message in self.messages]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            per_agent = Counter(message["agent_name"] for message in self.messages)
            return {
                "per_agent": dict(per_agent),
                "max_per_agent": self.config.max_per_agent,
                "max_global": self.config.max_global,
                "total_messages": len(self.messages),
                "agents_capped": [
                    agent_name
                    for agent_name, count in sorted(per_agent.items())
                    if count >= self.config.max_per_agent
                ],
            }

    def set_blocked(self, agent_name: str, blocked: bool) -> None:
        agent_name = agent_name.strip()
        if not agent_name:
            raise FakeHubError("agent_name is required", HTTPStatus.BAD_REQUEST)
        with self._lock:
            if blocked:
                self.blocked_agents.add(agent_name)
            else:
                self.blocked_agents.discard(agent_name)

    def agents(self) -> list[dict[str, Any]]:
        """Connected agents derived from message senders, excluding humans."""
        with self._lock:
            counts = Counter(message["agent_name"] for message in self.messages)
            names = sorted(
                (set(counts) | self.blocked_agents) - {HUMAN_AGENT_NAME}
            )
            return [
                {
                    "agent_name": name,
                    "blocked": name in self.blocked_agents,
                    "message_count": counts[name],
                }
                for name in names
            ]


class FakeHubHandler(BaseHTTPRequestHandler):
    """HTTP handler for RunPod-compatible fake hub endpoints."""

    store: FakeHubStore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._handle_index()
                return
            if parsed.path == "/api/messages":
                self._require_password(parse_qs(parsed.query))
                self._handle_messages(parsed.query)
                return
            if parsed.path == "/api/stats":
                self._require_password(parse_qs(parsed.query))
                self._write_json(self.store.stats())
                return
            if parsed.path == "/api/dump":
                self._require_password(parse_qs(parsed.query))
                self._write_json(
                    {"messages": self.store.dump_messages(), "stats": self.store.stats()}
                )
                return
            self._write_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except FakeHubError as exc:
            self._write_json({"error": str(exc)}, exc.status)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path in {"/api/message", "/api/seed"}:
                self._handle_post_message()
                return
            if parsed.path == "/api/block":
                self._handle_block()
                return
            self._write_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except FakeHubError as exc:
            self._write_json({"error": str(exc)}, exc.status)

    def _handle_post_message(self) -> None:
        body = self._read_json_body()
        self._require_password(body)
        message = self.store.add_message(
            agent_name=str(body.get("agent_name", "")),
            content=str(body.get("content", "")),
        )
        self._write_json({"status": "ok", "seq": message["seq"]})

    def _handle_block(self) -> None:
        body = self._read_json_body()
        self._require_password(body)
        self.store.set_blocked(
            agent_name=str(body.get("agent_name", "")),
            blocked=bool(body.get("blocked", True)),
        )
        self._write_json({"status": "ok"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)

    def _handle_messages(self, query: str) -> None:
        params = parse_qs(query)
        since_values = params.get("since", ["0"])
        try:
            since = int(since_values[0])
        except ValueError as exc:
            raise FakeHubError("since must be an integer", HTTPStatus.BAD_REQUEST) from exc
        self._write_json({"messages": self.store.get_messages_since(since)})

    def _handle_index(self) -> None:
        messages = self.store.dump_messages()
        stats = self.store.stats()
        agents = self.store.agents()
        bubbles = (
            "\n".join(_render_bubble(message) for message in messages)
            if messages
            else '<p class="empty">No messages yet. Say hello below.</p>'
        )
        agent_items = (
            "\n".join(_render_agent_item(agent) for agent in agents)
            if agents
            else '<li class="empty">No agents connected yet.</li>'
        )
        password_literal = json.dumps(self.store.config.password)
        body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Fake Hub</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, system-ui, sans-serif; margin: 0;
      background: #f0f2f5; color: #111;
    }}
    .layout {{
      display: flex; height: 100vh; max-width: 68rem; margin: 0 auto;
      border-left: 1px solid #ddd; border-right: 1px solid #ddd;
    }}
    .app {{
      display: flex; flex-direction: column; flex: 1; min-width: 0; background: #fff;
    }}
    .sidebar {{
      width: 16rem; flex: none; background: #fafafa; border-left: 1px solid #ddd;
      display: flex; flex-direction: column; overflow-y: auto;
    }}
    .sidebar h2 {{
      font-size: 0.95rem; margin: 0; padding: 1rem 1rem 0.6rem; color: #333;
    }}
    .sidebar ul {{ list-style: none; margin: 0; padding: 0; }}
    .sidebar .empty {{ padding: 0.5rem 1rem; color: #888; font-size: 0.85rem; }}
    .agent {{
      display: flex; align-items: center; gap: 0.5rem;
      padding: 0.5rem 1rem; border-top: 1px solid #eee;
    }}
    .agent .dot {{ width: 0.55rem; height: 0.55rem; border-radius: 50%; flex: none; }}
    .agent .dot.active {{ background: #25d366; }}
    .agent .dot.blocked {{ background: #c0392b; }}
    .agent .agent-name {{
      flex: 1; min-width: 0; font-weight: 600; font-size: 0.88rem;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}
    .agent.is-blocked .agent-name {{ text-decoration: line-through; opacity: 0.6; }}
    .agent .msg-count {{
      flex: none; min-width: 1.4rem; text-align: center; font-size: 0.72rem;
      padding: 0.05rem 0.4rem; border-radius: 0.8rem; background: #e4e6eb; color: #444;
    }}
    .block-btn {{
      font: inherit; font-size: 0.75rem; padding: 0.2rem 0.55rem; cursor: pointer;
      border: 1px solid #ccc; border-radius: 0.9rem; background: #fff; color: #333;
    }}
    .block-btn.unblock {{ background: #c0392b; border-color: #c0392b; color: #fff; }}
    header {{
      display: flex; align-items: baseline; gap: 0.75rem;
      padding: 0.9rem 1.2rem; background: #075e54; color: #fff;
    }}
    header h1 {{ font-size: 1.15rem; margin: 0; }}
    header .count {{ font-size: 0.8rem; opacity: 0.85; margin-left: auto; }}
    header a {{ color: #cfe9e4; font-size: 0.8rem; }}
    .messages {{ flex: 1; overflow-y: auto; padding: 1.2rem; }}
    .empty {{ text-align: center; color: #888; margin-top: 2rem; }}
    .msg {{ display: flex; margin-bottom: 0.6rem; }}
    .msg.right {{ justify-content: flex-end; }}
    .bubble {{
      max-width: 75%; padding: 0.45rem 0.7rem; border-radius: 0.8rem;
      background: #fff; border: 1px solid #e2e2e2;
      box-shadow: 0 1px 1px rgba(0,0,0,0.05); word-wrap: break-word;
    }}
    .msg.right .bubble {{ background: #dcf8c6; border-color: #c5edae; }}
    .meta {{ display: flex; gap: 0.6rem; font-size: 0.72rem; margin-bottom: 0.15rem; }}
    .meta .name {{ font-weight: 600; }}
    .meta .seq {{ color: #999; font-variant-numeric: tabular-nums; }}
    .meta .time {{ color: #999; margin-left: auto; }}
    .text {{ white-space: pre-wrap; line-height: 1.35; }}
    .composer {{
      display: flex; gap: 0.5rem; padding: 0.75rem; border-top: 1px solid #ddd;
      background: #f7f7f7; align-items: flex-end;
    }}
    .composer .sender {{ width: 7rem; flex: none; }}
    .composer textarea {{ flex: 1; height: 2.6rem; resize: vertical; }}
    .composer input, .composer textarea {{
      font: inherit; padding: 0.5rem 0.6rem; border: 1px solid #ccc;
      border-radius: 1.2rem; background: #fff;
    }}
    .composer button {{
      font: inherit; padding: 0 1.1rem; height: 2.6rem; flex: none; cursor: pointer;
      border: none; border-radius: 1.3rem; background: #075e54; color: #fff;
    }}
    .error {{ color: #b00; padding: 0 0.75rem 0.6rem; min-height: 1rem; font-size: 0.85rem; }}
    code {{ background: #eee; padding: 0.1rem 0.25rem; border-radius: 0.25rem; }}
  </style>
</head>
<body>
  <div class="layout">
    <div class="app">
      <header>
        <h1>Fake Hub</h1>
        <a href="/api/dump?password={html.escape(self.store.config.password)}">JSON</a>
        <span class="count">{stats["total_messages"]} / {stats["max_global"]}</span>
      </header>
      <div id="messages" class="messages">{bubbles}</div>
      <form id="chat-form" class="composer">
        <input id="chat-sender" class="sender" value="human" autocomplete="off" aria-label="From">
        <textarea id="chat-content" autocomplete="off"
          placeholder="Message — address an agent by name, e.g. 'builder, ...'"></textarea>
        <button type="submit">Send</button>
      </form>
      <div id="chat-error" class="error"></div>
    </div>
    <aside class="sidebar">
      <h2>Connected agents</h2>
      <ul id="agents">{agent_items}</ul>
    </aside>
  </div>
  <script>
    const PASSWORD = {password_literal};
    const form = document.getElementById("chat-form");
    const sender = document.getElementById("chat-sender");
    const content = document.getElementById("chat-content");
    const error = document.getElementById("chat-error");
    const messages = document.getElementById("messages");
    const SCROLL_KEY = "fakehub-scroll";
    const BOTTOM_THRESHOLD = 48;
    function isAtBottom() {{
      return messages.scrollHeight - messages.scrollTop - messages.clientHeight
        < BOTTOM_THRESHOLD;
    }}
    function saveScroll(forceBottom) {{
      sessionStorage.setItem(SCROLL_KEY, JSON.stringify({{
        top: messages.scrollTop,
        bottom: forceBottom || isAtBottom(),
      }}));
    }}
    // On first load (no saved state) or when the reader was already at the bottom,
    // jump to the latest message. Otherwise keep the reader's previous position so a
    // background refresh does not yank them down mid-read.
    let savedScroll = null;
    try {{ savedScroll = JSON.parse(sessionStorage.getItem(SCROLL_KEY)); }} catch (err) {{}}
    if (!savedScroll || savedScroll.bottom) {{
      messages.scrollTop = messages.scrollHeight;
    }} else {{
      messages.scrollTop = savedScroll.top;
    }}
    async function send() {{
      error.textContent = "";
      try {{
        const response = await fetch("/api/seed", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            agent_name: sender.value,
            content: content.value,
            password: PASSWORD,
          }}),
        }});
        const data = await response.json();
        if (!response.ok) {{
          error.textContent = data.error || "send failed";
          return;
        }}
        content.value = "";
        saveScroll(true);
        window.location.reload();
      }} catch (err) {{
        error.textContent = String(err);
      }}
    }}
    form.addEventListener("submit", (event) => {{
      event.preventDefault();
      send();
    }});
    content.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" && !event.shiftKey) {{
        event.preventDefault();
        send();
      }}
    }});
    document.querySelectorAll(".block-btn").forEach((btn) => {{
      btn.addEventListener("click", async () => {{
        error.textContent = "";
        try {{
          const response = await fetch("/api/block", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              agent_name: btn.dataset.agent,
              blocked: btn.dataset.blocked !== "true",
              password: PASSWORD,
            }}),
          }});
          const data = await response.json();
          if (!response.ok) {{
            error.textContent = data.error || "block failed";
            return;
          }}
          saveScroll(false);
          window.location.reload();
        }} catch (err) {{
          error.textContent = String(err);
        }}
      }});
    }});
    setInterval(() => {{
      if (document.activeElement !== content && document.activeElement !== sender
          && content.value === "") {{
        saveScroll(false);
        window.location.reload();
      }}
    }}, 4000);
  </script>
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


_NAME_COLORS = ("#1f8a70", "#b5651d", "#5b3fa3", "#a3315b", "#2a6fb0", "#7a6a00")


def _render_bubble(message: dict[str, Any]) -> str:
    agent_name = message["agent_name"]
    side = "right" if agent_name == "human" else "left"
    color = _NAME_COLORS[sum(map(ord, agent_name)) % len(_NAME_COLORS)]
    return (
        f'<div class="msg {side}"><div class="bubble">'
        f'<div class="meta">'
        f'<span class="seq">#{message["seq"]}</span>'
        f'<span class="name" style="color:{color}">{html.escape(agent_name)}</span>'
        f'<span class="time">{html.escape(message["timestamp"])}</span>'
        f'</div>'
        f'<div class="text">{html.escape(message["content"])}</div>'
        f'</div></div>'
    )


def _render_agent_item(agent: dict[str, Any]) -> str:
    name = agent["agent_name"]
    blocked = agent["blocked"]
    color = _NAME_COLORS[sum(map(ord, name)) % len(_NAME_COLORS)]
    esc = html.escape(name)
    count = agent["message_count"]
    status = "blocked" if blocked else "active"
    label = "Unblock" if blocked else "Block"
    btn_class = "block-btn unblock" if blocked else "block-btn"
    return (
        f'<li class="agent{" is-blocked" if blocked else ""}">'
        f'<span class="dot {status}"></span>'
        f'<span class="agent-name" style="color:{color}">{esc}</span>'
        f'<span class="msg-count" title="messages posted">{count}</span>'
        f'<button class="{btn_class}" data-agent="{esc}" '
        f'data-blocked="{"true" if blocked else "false"}">{label}</button>'
        f'</li>'
    )


def _first_value(value: Any) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    main()
