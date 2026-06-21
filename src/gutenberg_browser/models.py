import re
from dataclasses import dataclass, field

_WHITESPACE = re.compile(r"\s+")
_DOUBLE_QUOTES = ('"', "“", "”")  # straight and curly double quotes
_SINGLE_QUOTES = ("'", "‘", "’")  # straight and curly single quotes
# Words that legitimately begin with an apostrophe (poetic elisions); a leading
# quote before one of these is an apostrophe, not a stray opening quotation mark.
_ELISIONS = {
    "twas", "tis", "twere", "twould", "twill", "twixt", "neath",
    "gainst", "tween", "em", "er", "round", "bout", "cause", "til", "tother",
}


def clean_title(title: str) -> str:
    """Normalize a title for display and sorting.

    Many Project Gutenberg titles carry embedded newlines and wrap phrases in
    double quotes (e.g. '"Captains Courageous": A Story'), which add visual
    noise and, because quotes sort before letters, skew alphabetical order.

    Rules:
    - Collapse whitespace and drop all double quotes.
    - Strip single quotes when a matching pair wraps the entire title
      (e.g. "'All's Well!'" -> "All's Well!"), preserving embedded apostrophes.
    - Strip a lone leading single quote that has no closing quote (a dangling
      opening quotation mark), except before an elision like 'Twas / 'Tis.
    """
    title = _WHITESPACE.sub(" ", title).strip()
    for q in _DOUBLE_QUOTES:
        title = title.replace(q, "")
    title = title.strip()

    if len(title) >= 2 and title[0] in _SINGLE_QUOTES and title[-1] in _SINGLE_QUOTES:
        title = title[1:-1].strip()
    elif len(title) >= 2 and title[0] in _SINGLE_QUOTES and not any(
        q in title[1:] for q in _SINGLE_QUOTES
    ):
        rest = title[1:]
        word = ""
        for ch in rest:
            if ch.isalpha():
                word += ch
            else:
                break
        if word.lower() not in _ELISIONS:
            title = rest.lstrip()

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
