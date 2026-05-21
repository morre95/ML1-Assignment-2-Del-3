"""Read-only GitHub pull request inspection tools."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import requests

GITHUB_API_URL = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS = 20
MAX_BODY_CHARS = 4_000
MAX_DIFF_CHARS = 20_000
MAX_COMMENT_CHARS = 2_000


class GitHubToolError(ValueError):
    """Raised when GitHub PR context cannot be fetched safely."""


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int


@dataclass
class GitHubPullRequestClient:
    """Small read-only GitHub API client for pull request review context."""

    token: str | None = None
    session: requests.Session | None = None
    api_url: str = GITHUB_API_URL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        self.api_url = self.api_url.rstrip("/")
        if self.session is None:
            self.session = requests.Session()

    def fetch_pull_request_context(self, pr_reference: str) -> str:
        pr_ref = parse_pull_request_ref(pr_reference)
        pull = self._get_json(f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.number}")
        files = self._get_json(f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.number}/files")
        issue_comments = self._get_json(
            f"/repos/{pr_ref.owner}/{pr_ref.repo}/issues/{pr_ref.number}/comments"
        )
        review_comments = self._get_json(
            f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.number}/comments"
        )
        diff = self._get_text(
            f"/repos/{pr_ref.owner}/{pr_ref.repo}/pulls/{pr_ref.number}",
            accept="application/vnd.github.v3.diff",
        )
        checks = self._fetch_checks(pull)
        return format_pull_request_context(
            pr_ref=pr_ref,
            pull=pull,
            files=files,
            issue_comments=issue_comments,
            review_comments=review_comments,
            checks=checks,
            diff=diff,
        )

    def _fetch_checks(self, pull: dict[str, Any]) -> dict[str, Any] | list[Any]:
        head_sha = str(pull.get("head", {}).get("sha", ""))
        if not head_sha:
            return {}
        repo = pull.get("head", {}).get("repo") or {}
        owner = str(repo.get("owner", {}).get("login", ""))
        name = str(repo.get("name", ""))
        if not owner or not name:
            return {}
        return self._get_json(f"/repos/{owner}/{name}/commits/{head_sha}/check-runs")

    def _get_json(self, path: str) -> dict[str, Any] | list[Any]:
        response = self._get(path, accept="application/vnd.github+json")
        try:
            data = response.json()
        except ValueError as exc:
            raise GitHubToolError("GitHub returned invalid JSON.") from exc
        if not isinstance(data, dict | list):
            raise GitHubToolError("GitHub returned an unexpected JSON response.")
        return data

    def _get_text(self, path: str, accept: str) -> str:
        response = self._get(path, accept=accept)
        return response.text

    def _get(self, path: str, accept: str) -> requests.Response:
        if self.session is None:
            raise GitHubToolError("GitHub HTTP session is not configured.")
        response = self.session.get(
            f"{self.api_url}{path}",
            headers=self._headers(accept),
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            raise GitHubToolError("GitHub PR was not found or is not accessible.")
        if response.status_code == 401:
            raise GitHubToolError("GitHub rejected the configured token.")
        if response.status_code >= 400:
            raise GitHubToolError(f"GitHub request failed with HTTP {response.status_code}.")
        return response

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "react-agent-system-pr-review",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


def fetch_github_pull_request_context(pr_reference: str) -> str:
    """Fetch read-only GitHub PR context from a full pull request URL."""

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    client = GitHubPullRequestClient(token=token)
    return client.fetch_pull_request_context(pr_reference)


def parse_pull_request_ref(pr_reference: str) -> PullRequestRef:
    match = re.fullmatch(
        r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)/?",
        pr_reference.strip(),
    )
    if not match:
        raise GitHubToolError("Expected a GitHub pull request URL like https://github.com/owner/repo/pull/123.")
    return PullRequestRef(
        owner=match.group("owner"),
        repo=match.group("repo"),
        number=int(match.group("number")),
    )


def format_pull_request_context(
    pr_ref: PullRequestRef,
    pull: dict[str, Any] | list[Any],
    files: dict[str, Any] | list[Any],
    issue_comments: dict[str, Any] | list[Any],
    review_comments: dict[str, Any] | list[Any],
    checks: dict[str, Any] | list[Any],
    diff: str,
) -> str:
    if not isinstance(pull, dict):
        raise GitHubToolError("GitHub pull request response was not an object.")

    file_items = files if isinstance(files, list) else []
    issue_comment_items = issue_comments if isinstance(issue_comments, list) else []
    review_comment_items = review_comments if isinstance(review_comments, list) else []
    check_items = checks.get("check_runs", []) if isinstance(checks, dict) else []

    sections = [
        f"# GitHub PR Context: {pr_ref.owner}/{pr_ref.repo}#{pr_ref.number}",
        _format_metadata(pull),
        _format_files(file_items),
        _format_checks(check_items),
        _format_comments("Issue Comments", issue_comment_items),
        _format_comments("Review Comments", review_comment_items),
        "## Diff\n" + _truncate(diff, MAX_DIFF_CHARS),
    ]
    return "\n\n".join(section for section in sections if section)


def _format_metadata(pull: dict[str, Any]) -> str:
    user = pull.get("user") or {}
    base = pull.get("base") or {}
    head = pull.get("head") or {}
    return "\n".join(
        [
            "## Metadata",
            f"Title: {pull.get('title', '')}",
            f"State: {pull.get('state', '')}",
            f"Draft: {pull.get('draft', False)}",
            f"Author: {user.get('login', '')}",
            f"Base: {base.get('label', '')}",
            f"Head: {head.get('label', '')}",
            f"URL: {pull.get('html_url', '')}",
            "Body:",
            _truncate(str(pull.get("body") or ""), MAX_BODY_CHARS),
        ]
    )


def _format_files(files: list[Any]) -> str:
    lines = ["## Changed Files"]
    for file_item in files:
        if not isinstance(file_item, dict):
            continue
        lines.append(
            "- "
            f"{file_item.get('filename', '')} "
            f"({file_item.get('status', '')}, "
            f"+{file_item.get('additions', 0)}/-{file_item.get('deletions', 0)})"
        )
    return "\n".join(lines)


def _format_checks(checks: list[Any]) -> str:
    if not checks:
        return "## Checks\nNo check runs found."
    lines = ["## Checks"]
    for check in checks:
        if not isinstance(check, dict):
            continue
        lines.append(
            "- "
            f"{check.get('name', '')}: "
            f"{check.get('status', '')}"
            f"/{check.get('conclusion') or 'pending'}"
        )
    return "\n".join(lines)


def _format_comments(title: str, comments: list[Any]) -> str:
    if not comments:
        return f"## {title}\nNo comments found."
    lines = [f"## {title}"]
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        user = comment.get("user") or {}
        lines.extend(
            [
                f"### {user.get('login', 'unknown')}",
                _truncate(str(comment.get("body") or ""), MAX_COMMENT_CHARS),
            ]
        )
    return "\n".join(lines)


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n...[truncated]"
