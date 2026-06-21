import re
from dataclasses import dataclass, field

_WHITESPACE = re.compile(r"\s+")
_DISPLAY_QUOTES = ('"', "“", "”")  # straight and curly double quotes


def clean_title(title: str) -> str:
    """Normalize a title for display.

    Many Project Gutenberg titles carry embedded newlines and wrap phrases in
    double quotes (e.g. '"Captains Courageous": A Story'), which add visual
    noise in compact result rows. Collapse whitespace and drop double quotes.
    """
    title = _WHITESPACE.sub(" ", title).strip()
    for q in _DISPLAY_QUOTES:
        title = title.replace(q, "")
    return title


@dataclass
class Author:
    id: int
    name: str
    birthdate: int | None = None
    deathdate: int | None = None
    webpage: str | None = None


@dataclass
class BookFormat:
    mime: str
    url: str
    size: int | None = None


@dataclass
class Book:
    id: int
    title: str
    issued: str | None = None
    rights: str | None = None
    summary: str | None = None
    downloads: int = 0
    language: str | None = None
    content_hash: str | None = None
    authors: list[Author] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    bookshelves: list[str] = field(default_factory=list)
    formats: list[BookFormat] = field(default_factory=list)


@dataclass
class BookRow:
    """Lightweight result row for the search results list."""
    id: int
    title: str
    authors: str
    issued: str | None
    language: str | None
    downloads: int
