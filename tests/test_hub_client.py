import pytest

from react_agent_system.hub.client import HubAuthenticationError, HubRateLimitError, RunPodHubClient
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


def test_post_message_maps_429_to_rate_limit_error() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(429, {"error": "rate limited"})
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    with pytest.raises(HubRateLimitError):
        client.post_message("agent", "content")


def test_fetch_stats_maps_401_to_auth_error() -> None:
    session = FakeSession()
    session.next_response = FakeResponse(401, {"error": "bad password"})
    client = RunPodHubClient("https://hub.example", "secret", RateLimiter(0), session=session)

    with pytest.raises(HubAuthenticationError):
        client.fetch_stats()
