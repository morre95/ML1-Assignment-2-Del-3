from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
import requests

from react_agent_system.hub.client import (
    HubAuthenticationError,
    HubClientError,
    HubRateLimitError,
    RunPodHubClient,
)
from react_agent_system.hub.fake_server import FakeHubConfig, build_server
from react_agent_system.hub.rate_limit import RateLimiter

PASSWORD = "dev-hub-password"


@pytest.fixture
def fake_hub_url() -> Iterator[str]:
    server = build_server(
        host="127.0.0.1",
        port=0,
        config=FakeHubConfig(password=PASSWORD, max_per_agent=2, max_global=5),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_fake_hub_accepts_seed_and_fetches_messages_since(fake_hub_url: str) -> None:
    first = requests.post(
        f"{fake_hub_url}/api/seed",
        json={"agent_name": "human", "content": "hello", "password": PASSWORD},
        timeout=5,
    )
    second = requests.post(
        f"{fake_hub_url}/api/message",
        json={"agent_name": "agent", "content": "reply", "password": PASSWORD},
        timeout=5,
    )

    response = requests.get(
        f"{fake_hub_url}/api/messages",
        params={"since": 1, "password": PASSWORD},
        timeout=5,
    )

    assert first.json() == {"status": "ok", "seq": 1}
    assert second.json() == {"status": "ok", "seq": 2}
    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "seq": 2,
            "agent_name": "agent",
            "content": "reply",
            "timestamp": response.json()["messages"][0]["timestamp"],
        }
    ]


def test_fake_hub_stats_dump_and_html_view(fake_hub_url: str) -> None:
    requests.post(
        f"{fake_hub_url}/api/message",
        json={"agent_name": "agent", "content": "reply", "password": PASSWORD},
        timeout=5,
    )

    stats = requests.get(
        f"{fake_hub_url}/api/stats",
        params={"password": PASSWORD},
        timeout=5,
    )
    dump = requests.get(
        f"{fake_hub_url}/api/dump",
        params={"password": PASSWORD},
        timeout=5,
    )
    html = requests.get(fake_hub_url, timeout=5)

    assert stats.json() == {
        "per_agent": {"agent": 1},
        "max_per_agent": 2,
        "max_global": 5,
        "total_messages": 1,
        "agents_capped": [],
    }
    assert dump.json()["messages"][0]["content"] == "reply"
    assert html.status_code == 200
    assert "text/html" in html.headers["Content-Type"]
    assert "reply" in html.text


def test_fake_hub_rejects_wrong_password(fake_hub_url: str) -> None:
    response = requests.get(
        f"{fake_hub_url}/api/stats",
        params={"password": "wrong"},
        timeout=5,
    )

    assert response.status_code == 401
    assert response.json() == {"error": "wrong password"}


def test_fake_hub_rejects_invalid_requests(fake_hub_url: str) -> None:
    missing_content = requests.post(
        f"{fake_hub_url}/api/message",
        json={"agent_name": "agent", "password": PASSWORD},
        timeout=5,
    )
    invalid_since = requests.get(
        f"{fake_hub_url}/api/messages",
        params={"since": "abc", "password": PASSWORD},
        timeout=5,
    )
    too_long = requests.post(
        f"{fake_hub_url}/api/message",
        json={"agent_name": "agent", "content": "x" * 4097, "password": PASSWORD},
        timeout=5,
    )

    assert missing_content.status_code == 400
    assert invalid_since.status_code == 400
    assert too_long.status_code == 400


def test_fake_hub_enforces_per_agent_cap(fake_hub_url: str) -> None:
    for index in range(2):
        response = requests.post(
            f"{fake_hub_url}/api/message",
            json={"agent_name": "agent", "content": f"message {index}", "password": PASSWORD},
            timeout=5,
        )
        assert response.status_code == 200

    capped = requests.post(
        f"{fake_hub_url}/api/message",
        json={"agent_name": "agent", "content": "message 3", "password": PASSWORD},
        timeout=5,
    )
    stats = requests.get(
        f"{fake_hub_url}/api/stats",
        params={"password": PASSWORD},
        timeout=5,
    )

    assert capped.status_code == 429
    assert capped.json() == {"error": "agent message cap reached"}
    assert stats.json()["agents_capped"] == ["agent"]


def test_fake_hub_enforces_global_cap() -> None:
    server = build_server(
        host="127.0.0.1",
        port=0,
        config=FakeHubConfig(password=PASSWORD, max_per_agent=10, max_global=1),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    try:
        first = requests.post(
            f"{base_url}/api/message",
            json={"agent_name": "agent-1", "content": "one", "password": PASSWORD},
            timeout=5,
        )
        second = requests.post(
            f"{base_url}/api/message",
            json={"agent_name": "agent-2", "content": "two", "password": PASSWORD},
            timeout=5,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"error": "global message cap reached"}


def test_runpod_hub_client_works_against_fake_hub(fake_hub_url: str) -> None:
    client = RunPodHubClient(
        base_url=fake_hub_url,
        password=PASSWORD,
        rate_limiter=RateLimiter(interval_seconds=0),
        timeout_seconds=5,
    )

    post_response = client.post_message("agent", "hello")
    messages_response = client.fetch_messages(since=0)
    stats = client.fetch_stats()

    assert post_response.status == "ok"
    assert post_response.seq == 1
    assert messages_response.messages[0].agent_name == "agent"
    assert stats.total_messages == 1


def test_runpod_hub_client_maps_fake_hub_errors(fake_hub_url: str) -> None:
    wrong_password_client = RunPodHubClient(
        base_url=fake_hub_url,
        password="wrong",
        rate_limiter=RateLimiter(interval_seconds=0),
        timeout_seconds=5,
    )
    client = RunPodHubClient(
        base_url=fake_hub_url,
        password=PASSWORD,
        rate_limiter=RateLimiter(interval_seconds=0),
        timeout_seconds=5,
    )

    with pytest.raises(HubAuthenticationError):
        wrong_password_client.fetch_stats()
    with pytest.raises(HubClientError):
        client.fetch_messages(since="bad")  # type: ignore[arg-type]

    client.post_message("agent", "one")
    client.post_message("agent", "two")
    with pytest.raises(HubRateLimitError):
        client.post_message("agent", "three")
