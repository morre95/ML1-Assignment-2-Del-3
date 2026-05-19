"""Research tool implementations."""

from __future__ import annotations

import wikipedia
from duckduckgo_search import DDGS


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return compact text results."""

    if not query.strip():
        raise ValueError("Search query cannot be empty.")

    rows: list[str] = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=max_results):
            title = result.get("title", "Untitled")
            href = result.get("href", "")
            body = result.get("body", "")
            rows.append(f"- {title}\n  {href}\n  {body}")

    return "\n".join(rows) if rows else "No web search results found."


def wikipedia_lookup(query: str, sentences: int = 5) -> str:
    """Look up a topic on Wikipedia."""

    if not query.strip():
        raise ValueError("Wikipedia query cannot be empty.")

    try:
        page_title = wikipedia.search(query, results=1)[0]
        return wikipedia.summary(page_title, sentences=sentences, auto_suggest=False)
    except IndexError:
        return "No Wikipedia page found."
    except wikipedia.DisambiguationError as exc:
        options = ", ".join(exc.options[:5])
        return f"Query is ambiguous. Top options: {options}"
    except wikipedia.PageError:
        return "No Wikipedia page found."
