import re
import sqlite3
from pathlib import Path
from typing import Optional

from .models import Author, Book, BookFormat, BookRow

DB_PATH = Path("gutenberg.db")

LANGUAGE_NAMES: dict[str, str] = {
    "af":  "Afrikaans",
    "ar":  "Arabic",
    "arp": "Arapaho",
    "bg":  "Bulgarian",
    "bo":  "Tibetan",
    "br":  "Breton",
    "ca":  "Catalan",
    "ceb": "Cebuano",
    "cs":  "Czech",
    "cy":  "Welsh",
    "da":  "Danish",
    "de":  "German",
    "el":  "Greek",
    "en":  "English",
    "enm": "Middle English",
    "eo":  "Esperanto",
    "es":  "Spanish",
    "et":  "Estonian",
    "fa":  "Persian",
    "fi":  "Finnish",
    "fr":  "French",
    "fur": "Friulian",
    "fy":  "Frisian",
    "ga":  "Irish",
    "gl":  "Galician",
    "gla": "Scottish Gaelic",
    "he":  "Hebrew",
    "hu":  "Hungarian",
    "ia":  "Interlingua",
    "ilo": "Ilocano",
    "is":  "Icelandic",
    "it":  "Italian",
    "iu":  "Inuktitut",
    "ja":  "Japanese",
    "la":  "Latin",
    "lt":  "Lithuanian",
    "mi":  "Māori",
    "myn": "Mayan",
    "nah": "Nahuatl",
    "nap": "Neapolitan",
    "nl":  "Dutch",
    "no":  "Norwegian",
    "oc":  "Occitan",
    "oji": "Ojibwe",
    "pl":  "Polish",
    "pt":  "Portuguese",
    "rmq": "Caló",
    "ro":  "Romanian",
    "ru":  "Russian",
    "sa":  "Sanskrit",
    "sco": "Scots",
    "sl":  "Slovenian",
    "sr":  "Serbian",
    "sv":  "Swedish",
    "te":  "Telugu",
    "tl":  "Tagalog",
    "yi":  "Yiddish",
    "zh":  "Chinese",
}


def lang_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id           INTEGER PRIMARY KEY,
    title        TEXT NOT NULL,
    issued       TEXT,
    rights       TEXT,
    summary      TEXT,
    downloads    INTEGER DEFAULT 0,
    language_id  INTEGER REFERENCES languages(id),
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS languages (
    id   INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS authors (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    birthdate INTEGER,
    deathdate INTEGER,
    webpage   TEXT
);

CREATE TABLE IF NOT EXISTS book_authors (
    book_id   INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, author_id)
);

CREATE TABLE IF NOT EXISTS subjects (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS book_subjects (
    book_id    INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, subject_id)
);

CREATE TABLE IF NOT EXISTS bookshelves (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS book_bookshelves (
    book_id      INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    bookshelf_id INTEGER NOT NULL REFERENCES bookshelves(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, bookshelf_id)
);

CREATE TABLE IF NOT EXISTS formats (
    id      INTEGER PRIMARY KEY,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    mime    TEXT NOT NULL,
    url     TEXT NOT NULL,
    size    INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title,
    author_names,
    subjects,
    bookshelves,
    summary,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_books_language     ON books(language_id);
CREATE INDEX IF NOT EXISTS idx_books_downloads    ON books(downloads DESC);
CREATE INDEX IF NOT EXISTS idx_book_authors_a     ON book_authors(author_id);
CREATE INDEX IF NOT EXISTS idx_book_subjects_s    ON book_subjects(subject_id);
CREATE INDEX IF NOT EXISTS idx_book_bookshelves_b ON book_bookshelves(bookshelf_id);
CREATE INDEX IF NOT EXISTS idx_formats_book       ON formats(book_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)


def get_book_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]


def get_languages(conn: sqlite3.Connection, query: str = "") -> list[tuple[str, int]]:
    """Return (code, count) pairs, optionally scoped to an FTS query."""
    fts_query = build_fts_query(query) if query else ""
    if fts_query:
        rows = conn.execute(
            """SELECT l.code, COUNT(*) AS cnt
               FROM books b
               JOIN languages l ON l.id = b.language_id
               WHERE b.id IN (SELECT rowid FROM books_fts WHERE books_fts MATCH ?)
               GROUP BY l.id
               ORDER BY cnt DESC""",
            (fts_query,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT l.code, COUNT(*) AS cnt
               FROM languages l JOIN books b ON b.language_id = l.id
               GROUP BY l.id ORDER BY cnt DESC"""
        ).fetchall()
    return [(r["code"], r["cnt"]) for r in rows]


def fts_schema_current(conn: sqlite3.Connection) -> bool:
    """Return True if books_fts has the current 5-column schema."""
    try:
        conn.execute("SELECT summary FROM books_fts LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def build_fts_query(text: str) -> str:
    clean = re.sub(r'["\'\(\)\*\:\^\-\+\~\.]', " ", text).strip()
    if not clean:
        return ""
    tokens = [t for t in clean.split() if t]
    return " ".join(f'"{t}"*' for t in tokens)


def search_books(
    conn: sqlite3.Connection,
    query: str = "",
    lang_code: str = "",
    sort: str = "title",
    page: int = 0,
    page_size: int = 50,
) -> tuple[list[BookRow], int]:
    params: list = []
    fts_query = build_fts_query(query) if query else ""

    # Relevance sort requires books_fts as the driving table to expose `rank`
    if fts_query and sort == "relevance":
        base = """
            SELECT b.id, b.title,
                   COALESCE(GROUP_CONCAT(a.name, ', '), '') AS authors,
                   b.issued, l.code AS language, b.downloads
            FROM (SELECT rowid AS bid, rank FROM books_fts WHERE books_fts MATCH ?) ranked
            JOIN books b ON b.id = ranked.bid
            LEFT JOIN book_authors ba ON ba.book_id = b.id
            LEFT JOIN authors a ON a.id = ba.author_id
            LEFT JOIN languages l ON l.id = b.language_id
            WHERE 1=1
        """
        params.append(fts_query)
        order = "ORDER BY MIN(ranked.rank)"
    elif fts_query:
        base = """
            SELECT b.id, b.title,
                   COALESCE(GROUP_CONCAT(a.name, ', '), '') AS authors,
                   b.issued, l.code AS language, b.downloads
            FROM books b
            LEFT JOIN book_authors ba ON ba.book_id = b.id
            LEFT JOIN authors a ON a.id = ba.author_id
            LEFT JOIN languages l ON l.id = b.language_id
            WHERE b.id IN (SELECT rowid FROM books_fts WHERE books_fts MATCH ?)
        """
        params.append(fts_query)
        order = "ORDER BY b.downloads DESC" if sort == "downloads" else "ORDER BY b.title COLLATE NOCASE ASC"
    else:
        base = """
            SELECT b.id, b.title,
                   COALESCE(GROUP_CONCAT(a.name, ', '), '') AS authors,
                   b.issued, l.code AS language, b.downloads
            FROM books b
            LEFT JOIN book_authors ba ON ba.book_id = b.id
            LEFT JOIN authors a ON a.id = ba.author_id
            LEFT JOIN languages l ON l.id = b.language_id
            WHERE 1=1
        """
        order = "ORDER BY b.downloads DESC" if sort == "downloads" else "ORDER BY b.title COLLATE NOCASE ASC"

    if lang_code:
        base += " AND l.code = ?"
        params.append(lang_code)

    base += f" GROUP BY b.id {order}"

    count_row = conn.execute(
        f"SELECT COUNT(*) FROM ({base}) _sub", params
    ).fetchone()
    total = count_row[0] if count_row else 0

    base += " LIMIT ? OFFSET ?"
    params += [page_size, page * page_size]

    rows = conn.execute(base, params).fetchall()
    return (
        [BookRow(
            id=r["id"],
            title=r["title"],
            authors=r["authors"] or "",
            issued=r["issued"],
            language=r["language"],
            downloads=r["downloads"],
        ) for r in rows],
        total,
    )


def get_book_detail(conn: sqlite3.Connection, book_id: int) -> Optional[Book]:
    row = conn.execute(
        """SELECT b.id, b.title, b.issued, b.rights, b.summary, b.downloads, l.code AS language
           FROM books b LEFT JOIN languages l ON l.id = b.language_id
           WHERE b.id = ?""",
        (book_id,),
    ).fetchone()
    if not row:
        return None

    book = Book(
        id=row["id"],
        title=row["title"],
        issued=row["issued"],
        rights=row["rights"],
        summary=row["summary"],
        downloads=row["downloads"],
        language=row["language"],
    )

    for r in conn.execute(
        """SELECT a.id, a.name, a.birthdate, a.deathdate, a.webpage
           FROM authors a JOIN book_authors ba ON ba.author_id = a.id
           WHERE ba.book_id = ?""",
        (book_id,),
    ):
        book.authors.append(Author(
            id=r["id"], name=r["name"],
            birthdate=r["birthdate"], deathdate=r["deathdate"],
            webpage=r["webpage"],
        ))

    for r in conn.execute(
        """SELECT s.name FROM subjects s JOIN book_subjects bs ON bs.subject_id = s.id
           WHERE bs.book_id = ? ORDER BY s.name""",
        (book_id,),
    ):
        book.subjects.append(r["name"])

    for r in conn.execute(
        """SELECT bs.name FROM bookshelves bs
           JOIN book_bookshelves bb ON bb.bookshelf_id = bs.id
           WHERE bb.book_id = ? ORDER BY bs.name""",
        (book_id,),
    ):
        book.bookshelves.append(r["name"])

    for r in conn.execute(
        "SELECT mime, url, size FROM formats WHERE book_id = ? ORDER BY mime",
        (book_id,),
    ):
        book.formats.append(BookFormat(mime=r["mime"], url=r["url"], size=r["size"]))

    return book


def get_content_hashes(conn: sqlite3.Connection) -> dict[int, str]:
    rows = conn.execute("SELECT id, content_hash FROM books WHERE content_hash IS NOT NULL").fetchall()
    return {r["id"]: r["content_hash"] for r in rows}


def delete_book(conn: sqlite3.Connection, book_id: int) -> None:
    conn.execute("DELETE FROM books_fts WHERE rowid = ?", (book_id,))
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
