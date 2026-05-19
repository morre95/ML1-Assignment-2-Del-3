from pathlib import Path

import pytest

from react_agent_system.tools.repo import (
    RepositoryToolError,
    read_text_file,
    replace_exact_section,
    search_text,
)


def test_replace_exact_section_updates_single_match(tmp_path: Path) -> None:
    file_path = tmp_path / "example.py"
    file_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = replace_exact_section(tmp_path, "example.py", "beta", "delta")

    assert result == "Updated example.py"
    assert file_path.read_text(encoding="utf-8") == "alpha\ndelta\ngamma\n"


def test_replace_exact_section_rejects_multiple_matches(tmp_path: Path) -> None:
    file_path = tmp_path / "example.py"
    file_path.write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        replace_exact_section(tmp_path, "example.py", "same", "different")


def test_read_text_file_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        read_text_file(tmp_path, str(outside))


def test_search_text_finds_matching_lines(tmp_path: Path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("first\nNeedle here\n", encoding="utf-8")

    result = search_text(tmp_path, "needle")

    assert "notes.txt:2: Needle here" in result
