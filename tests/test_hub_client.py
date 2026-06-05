import pytest

from react_agent_system.hub.client import (
    HubAuthenticationError,
    HubClientError,
    HubRateLimitError,
    RunPodHubClient,
)
from react_agent_system.hub.rate_limit import RateLimiter


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls = []
        self.next_response = FakeResponse(200, {"messages": []})

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.calls.append(("GET", url, params, timeout))
        return self.next_response

    def post(self, url: str, json: dict, timeout: int) -> FakeResponse:
        self.calls.append(("POST", url, json, timeout))
        return self.next_response


def test_fetch_messages_sends_password_and_since() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(
        200,
        {"messages": [{"seq": 1, "agent_name": "other", "content": "hello"}]},
    )
    client = RunPodHubClient(
        "https://hub.example",
        "secret",
        RateLimiter(0),
        session=session,
    )

    response = client.fetch_messages(since=12)

    assert response.messages[0].content == "hello"
    assert session.calls[0][2] == {"since": 12, "password": "secret"}


def test_fetch_messages_parses_embedded_stats() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(
        200,
        {
            "messages": [],
            "stats": {
                "paused": True,
                "manager": "lead-agent",
                "allowed_agents": {"me": False},
                "billboard": {"content": "Build a guessing game"},
                "files": [{"filename": "game.py", "size": 42, "author": "me"}],
            },
        },
    )
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    response = client.fetch_messages(since=0)

    assert response.stats.paused is True
    assert response.stats.manager == "lead-agent"
    assert response.stats.allowed_agents == {"me": False}
    assert response.stats.billboard.content == "Build a guessing game"
    assert response.stats.files[0].filename == "game.py"


def test_post_message_includes_role() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(200, {"ok": True, "seq": 1})
    client = RunPodHubClient(
        "https://hub.example",
        "secret",
        RateLimiter(0),
        session=session,
        role="developer",
    )

    client.post_message("me", "hi")

    assert session.calls[0][2]["role"] == "developer"


def test_upload_file_rejects_oversized_content() -> None:
    session = FakeSession()
    client = RunPodHubClient(
        "https://hub.example",
        "secret",
        RateLimiter(0),
        session=session,
        max_file_bytes=10,
    )

    with pytest.raises(HubClientError):
        client.upload_file("me", "big.py", "x" * 11)
    assert session.calls == []


def test_read_file_sends_filename_param() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(
        200, {"filename": "game.py", "content": "print('hi')", "author": "me"}
    )
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    result = client.read_file("game.py")

    assert result.content == "print('hi')"
    assert session.calls[0][2] == {"filename": "game.py", "password": "secret"}


def test_post_message_maps_429_to_rate_limit_error() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(429, {"error": "rate limited"})
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    with pytest.raises(HubRateLimitError):
        client.post_message("agent", "content")


def test_post_message_accepts_live_hub_ok_response() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(200, {"ok": True, "seq": 17})
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    response = client.post_message("agent", "content")

    assert response.ok is True
    assert response.seq == 17


def test_fetch_state_maps_401_to_auth_error() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(401, {"error": "bad password"})
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    with pytest.raises(HubAuthenticationError):
        client.fetch_state()
