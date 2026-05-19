"""REST client for the RunPod hub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from react_agent_system.hub.models import HubMessagesResponse, HubPostResponse, HubStats
from react_agent_system.hub.rate_limit import RateLimiter


class HubClientError(RuntimeError):
    """Raised when the hub returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HubAuthenticationError(HubClientError):
    """Raised when the hub password is rejected."""


class HubRateLimitError(HubClientError):
    """Raised when the hub rate-limits the agent or caps messages."""


@dataclass
class RunPodHubClient:
    """Typed client for the hub API described in the connection guide."""

    base_url: str
    password: str
    rate_limiter: RateLimiter
    session: requests.Session | None = None
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        if not self.password:
            raise ValueError("Hub password is required.")
        self.base_url = self.base_url.rstrip("/")
        if self.session is None:
            self.session = requests.Session()

    def fetch_messages(self, since: int) -> HubMessagesResponse:
        self.rate_limiter.wait()
        response = self.session.get(
            f"{self.base_url}/api/messages",
            params={"since": since, "password": self.password},
            timeout=self.timeout_seconds,
        )
        data = self._json_or_raise(response)
        return HubMessagesResponse.model_validate(data)

    def post_message(self, agent_name: str, content: str) -> HubPostResponse:
        self.rate_limiter.wait()
        response = self.session.post(
            f"{self.base_url}/api/message",
            json={
                "agent_name": agent_name,
                "content": content,
                "password": self.password,
            },
            timeout=self.timeout_seconds,
        )
        data = self._json_or_raise(response)
        return HubPostResponse.model_validate(data)

    def fetch_stats(self) -> HubStats:
        self.rate_limiter.wait()
        response = self.session.get(
            f"{self.base_url}/api/stats",
            params={"password": self.password},
            timeout=self.timeout_seconds,
        )
        data = self._json_or_raise(response)
        return HubStats.model_validate(data)

    def _json_or_raise(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code == 401:
            raise HubAuthenticationError("Hub rejected the configured password.", 401)
        if response.status_code == 429:
            raise HubRateLimitError(_response_error_text(response), 429)
        if response.status_code >= 400:
            raise HubClientError(_response_error_text(response), response.status_code)
        data = response.json()
        if not isinstance(data, dict):
            raise HubClientError("Hub returned a non-object JSON response.")
        return data


def _response_error_text(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or f"Hub request failed with HTTP {response.status_code}."
    if isinstance(data, dict):
        return str(data.get("error") or data.get("message") or data)
    return str(data)
