"""Repository file tools."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class RepositoryToolError(ValueError):
    """Raised when a repository tool receives unsafe or invalid input."""


def resolve_workspace_path(workspace: Path, user_path: str) -> Path:
    """Resolve a user path and ensure it stays inside the workspace."""

    base = workspace.resolve()
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RepositoryToolError(f"Path is outside the workspace: {user_path}") from exc
    return resolved


def read_text_file(workspace: Path, path: str, max_chars: int = 20_000) -> str:
    resolved = resolve_workspace_path(workspace, path)
    if not resolved.exists():
        raise RepositoryToolError(f"File does not exist: {path}")
    if not resolved.is_file():
        raise RepositoryToolError(f"Path is not a file: {path}")
    return resolved.read_text(encoding="utf-8")[:max_chars]


def search_text(workspace: Path, query: str, glob: str = "**/*", max_results: int = 50) -> str:
    if not query:
        raise RepositoryToolError("Search query cannot be empty.")

    results: list[str] = []
    for path in _iter_text_files(workspace, glob):
        relative = path.relative_to(workspace.resolve())
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line_number, line in enumerate(lines, 1):
            if query.lower() in line.lower():
                results.append(f"{relative}:{line_number}: {line}")
                if len(results) >= max_results:
                    return "\n".join(results)

    return "\n".join(results) if results else "No matches found."


def replace_exact_section(workspace: Path, path: str, old_text: str, new_text: str) -> str:
    if not old_text:
        raise RepositoryToolError("old_text cannot be empty.")

    resolved = resolve_workspace_path(workspace, path)
    if not resolved.exists():
        raise RepositoryToolError(f"File does not exist: {path}")

    contents = resolved.read_text(encoding="utf-8")
    occurrences = contents.count(old_text)
    if occurrences != 1:
        raise RepositoryToolError(
            f"Expected exactly one match for old_text in {path}, found {occurrences}."
        )

    resolved.write_text(contents.replace(old_text, new_text, 1), encoding="utf-8")
    return f"Updated {resolved.relative_to(workspace.resolve())}"


def _iter_text_files(workspace: Path, glob: str) -> Iterable[Path]:
    ignored_parts = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    base = workspace.resolve()
    for path in base.glob(glob):
        if not path.is_file():
            continue
        if ignored_parts.intersection(path.relative_to(base).parts):
            continue
        yield path
