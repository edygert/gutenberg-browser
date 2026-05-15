from dataclasses import dataclass, field


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
