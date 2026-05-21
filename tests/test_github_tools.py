import pytest

from react_agent_system.tools.github import (
    GitHubPullRequestClient,
    GitHubToolError,
    PullRequestRef,
    parse_pull_request_ref,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | list | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text

    def json(self) -> dict | list:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        self.calls.append(("GET", url, headers, timeout))
        path = url.removeprefix("https://api.github.com")
        if headers["Accept"] == "application/vnd.github.v3.diff":
            return FakeResponse(200, text="diff --git a/app.py b/app.py\n+print('hi')\n")
        payloads: dict[str, dict | list] = {
            "/repos/example/project/pulls/7": {
                "title": "Fix add",
                "state": "open",
                "draft": False,
                "html_url": "https://github.com/example/project/pull/7",
                "body": "This fixes add.",
                "user": {"login": "octo"},
                "base": {"label": "example:main"},
                "head": {
                    "label": "contrib:fix-add",
                    "sha": "abc123",
                    "repo": {"name": "project", "owner": {"login": "example"}},
                },
            },
            "/repos/example/project/pulls/7/files": [
                {"filename": "app.py", "status": "modified", "additions": 1, "deletions": 1}
            ],
            "/repos/example/project/issues/7/comments": [
                {"user": {"login": "reviewer"}, "body": "Please add tests."}
            ],
            "/repos/example/project/pulls/7/comments": [],
            "/repos/example/project/commits/abc123/check-runs": {
                "check_runs": [{"name": "tests", "status": "completed", "conclusion": "success"}]
            },
        }
        return FakeResponse(200, payloads[path])


def test_parse_pull_request_ref_accepts_github_url() -> None:
    assert parse_pull_request_ref("https://github.com/example/project/pull/7") == PullRequestRef(
        owner="example",
        repo="project",
        number=7,
    )


def test_parse_pull_request_ref_rejects_non_pr_input() -> None:
    with pytest.raises(GitHubToolError):
        parse_pull_request_ref("example/project#7")


def test_client_fetches_read_only_pr_context() -> None:
    session = FakeSession()
    client = GitHubPullRequestClient(token="secret", session=session)

    context = client.fetch_pull_request_context("https://github.com/example/project/pull/7")

    assert "GitHub PR Context: example/project#7" in context
    assert "Title: Fix add" in context
    assert "- app.py (modified, +1/-1)" in context
    assert "- tests: completed/success" in context
    assert "Please add tests." in context
    assert "diff --git a/app.py b/app.py" in context
    assert {call[0] for call in session.calls} == {"GET"}
    assert all(call[2]["Authorization"] == "Bearer secret" for call in session.calls)


def test_client_maps_github_errors() -> None:
    class NotFoundSession:
        def get(self, url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
            return FakeResponse(404, {"message": "not found"})

    client = GitHubPullRequestClient(session=NotFoundSession())

    with pytest.raises(GitHubToolError):
        client.fetch_pull_request_context("https://github.com/example/project/pull/7")
