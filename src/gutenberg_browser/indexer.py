import hashlib
import re
import sqlite3
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from .db import delete_book, get_content_hashes, init_schema
from .models import Author, Book, BookFormat

NS = {
    "rdf":     "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "pgterms": "http://www.gutenberg.org/2009/pgterms/",
    "dcam":    "http://purl.org/dc/dcam/",
}
_RDF_ABOUT    = f"{{{NS['rdf']}}}about"
_RDF_RESOURCE = f"{{{NS['rdf']}}}resource"

LCSH_URI = "http://purl.org/dc/terms/LCSH"
BATCH_SIZE = 500


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or not el.text:
        return None
    return el.text.strip() or None


def _int(el: Optional[ET.Element]) -> Optional[int]:
    t = _text(el)
    if t is None:
        return None
    try:
        return int(t)
    except ValueError:
        return None


def _book_id_from_path(name: str) -> Optional[int]:
    """Extract numeric book ID from cache/epub/99/pg99.rdf path."""
    m = re.search(r"/pg(\d+)\.rdf$", name)
    if not m:
        return None
    return int(m.group(1))


def parse_rdf(content: bytes) -> Optional[Book]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None

    ebook = root.find("pgterms:ebook", NS)
    if ebook is None:
        return None

    about = ebook.get(_RDF_ABOUT, "")
    m = re.match(r"ebooks/(\d+)$", about)
    if not m:
        return None
    book_id = int(m.group(1))

    title_el = ebook.find("dcterms:title", NS)
    title = _text(title_el) or "(untitled)"

    issued  = _text(ebook.find("dcterms:issued", NS))
    rights  = _text(ebook.find("dcterms:rights", NS))
    summary = _text(ebook.find("pgterms:marc520", NS))
    downloads = _int(ebook.find("pgterms:downloads", NS)) or 0

    # Language
    lang_el = ebook.find("dcterms:language/rdf:Description/rdf:value", NS)
    language = _text(lang_el)

    # Authors
    authors: list[Author] = []
    for creator_el in ebook.findall("dcterms:creator", NS):
        agent_el = creator_el.find("pgterms:agent", NS)
        if agent_el is None:
            continue
        agent_about = agent_el.get(_RDF_ABOUT, "")
        am = re.search(r"/agents/(\d+)$", agent_about)
        agent_id = int(am.group(1)) if am else None
        if agent_id is None:
            continue
        name = _text(agent_el.find("pgterms:name", NS)) or ""
        birthdate = _int(agent_el.find("pgterms:birthdate", NS))
        deathdate = _int(agent_el.find("pgterms:deathdate", NS))
        webpage_el = agent_el.find("pgterms:webpage", NS)
        webpage = webpage_el.get(_RDF_RESOURCE) if webpage_el is not None else None
        authors.append(Author(id=agent_id, name=name, birthdate=birthdate,
                              deathdate=deathdate, webpage=webpage))

    # Subjects (LCSH only)
    subjects: list[str] = []
    for subj_el in ebook.findall("dcterms:subject", NS):
        desc = subj_el.find("rdf:Description", NS)
        if desc is None:
            continue
        member_of = desc.find("dcam:memberOf", NS)
        if member_of is not None and member_of.get(_RDF_RESOURCE, "") == LCSH_URI:
            val = _text(desc.find("rdf:value", NS))
            if val:
                subjects.append(val)

    # Bookshelves
    bookshelves: list[str] = []
    for shelf_el in ebook.findall("pgterms:bookshelf", NS):
        desc = shelf_el.find("rdf:Description", NS)
        if desc is None:
            continue
        val = _text(desc.find("rdf:value", NS))
        if val:
            bookshelves.append(val)

    # Formats
    formats: list[BookFormat] = []
    for fmt_el in ebook.findall("dcterms:hasFormat", NS):
        file_el = fmt_el.find("pgterms:file", NS)
        if file_el is None:
            continue
        url = file_el.get(_RDF_ABOUT, "")
        if not url:
            continue
        size = _int(file_el.find("dcterms:extent", NS))
        mime_el = file_el.find("dcterms:format/rdf:Description/rdf:value", NS)
        mime = _text(mime_el) or "application/octet-stream"
        formats.append(BookFormat(mime=mime, url=url, size=size))

    return Book(
        id=book_id,
        title=title,
        issued=issued,
        rights=rights,
        summary=summary,
        downloads=downloads,
        language=language,
        authors=authors,
        subjects=subjects,
        bookshelves=bookshelves,
        formats=formats,
    )


class _Batcher:
    """Accumulates parsed books and flushes to DB in batches."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._books: list[Book] = []
        # In-process caches to avoid round-trip SELECTs per book
        self._lang_cache:   dict[str, int] = {}
        self._author_cache: dict[int, bool] = {}
        self._subj_cache:   dict[str, int] = {}
        self._shelf_cache:  dict[str, int] = {}
        self._load_caches()

    def _load_caches(self) -> None:
        for r in self.conn.execute("SELECT id, code FROM languages"):
            self._lang_cache[r[1]] = r[0]
        for r in self.conn.execute("SELECT id FROM authors"):
            self._author_cache[r[0]] = True
        for r in self.conn.execute("SELECT id, name FROM subjects"):
            self._subj_cache[r[1]] = r[0]
        for r in self.conn.execute("SELECT id, name FROM bookshelves"):
            self._shelf_cache[r[1]] = r[0]

    def add(self, book: Book) -> None:
        self._books.append(book)
        if len(self._books) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if not self._books:
            return
        conn = self.conn
        conn.execute("BEGIN")
        try:
            for book in self._books:
                self._write_book(conn, book)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        self._books.clear()

    def _get_or_create_lang(self, conn: sqlite3.Connection, code: str) -> int:
        if code not in self._lang_cache:
            conn.execute("INSERT OR IGNORE INTO languages(code) VALUES(?)", (code,))
            row = conn.execute("SELECT id FROM languages WHERE code=?", (code,)).fetchone()
            self._lang_cache[code] = row[0]
        return self._lang_cache[code]

    def _get_or_create_subject(self, conn: sqlite3.Connection, name: str) -> int:
        if name not in self._subj_cache:
            conn.execute("INSERT OR IGNORE INTO subjects(name) VALUES(?)", (name,))
            row = conn.execute("SELECT id FROM subjects WHERE name=?", (name,)).fetchone()
            self._subj_cache[name] = row[0]
        return self._subj_cache[name]

    def _get_or_create_shelf(self, conn: sqlite3.Connection, name: str) -> int:
        if name not in self._shelf_cache:
            conn.execute("INSERT OR IGNORE INTO bookshelves(name) VALUES(?)", (name,))
            row = conn.execute("SELECT id FROM bookshelves WHERE name=?", (name,)).fetchone()
            self._shelf_cache[name] = row[0]
        return self._shelf_cache[name]

    def _write_book(self, conn: sqlite3.Connection, book: Book) -> None:
        lang_id = self._get_or_create_lang(conn, book.language) if book.language else None

        conn.execute(
            """INSERT OR REPLACE INTO books
               (id, title, issued, rights, summary, downloads, language_id, content_hash)
               VALUES (?,?,?,?,?,?,?,?)""",
            (book.id, book.title, book.issued, book.rights, book.summary,
             book.downloads, lang_id, book.content_hash),
        )

        author_names: list[str] = []
        for author in book.authors:
            author_names.append(author.name)
            if author.id not in self._author_cache:
                conn.execute(
                    """INSERT OR IGNORE INTO authors(id, name, birthdate, deathdate, webpage)
                       VALUES(?,?,?,?,?)""",
                    (author.id, author.name, author.birthdate, author.deathdate, author.webpage),
                )
                self._author_cache[author.id] = True
            conn.execute(
                "INSERT OR IGNORE INTO book_authors(book_id, author_id) VALUES(?,?)",
                (book.id, author.id),
            )

        for subj in book.subjects:
            sid = self._get_or_create_subject(conn, subj)
            conn.execute(
                "INSERT OR IGNORE INTO book_subjects(book_id, subject_id) VALUES(?,?)",
                (book.id, sid),
            )

        for shelf in book.bookshelves:
            shid = self._get_or_create_shelf(conn, shelf)
            conn.execute(
                "INSERT OR IGNORE INTO book_bookshelves(book_id, bookshelf_id) VALUES(?,?)",
                (book.id, shid),
            )

        for fmt in book.formats:
            conn.execute(
                "INSERT INTO formats(book_id, mime, url, size) VALUES(?,?,?,?)",
                (book.id, fmt.mime, fmt.url, fmt.size),
            )

        conn.execute(
            "INSERT OR REPLACE INTO books_fts(rowid, title, author_names, subjects, bookshelves)"
            " VALUES(?,?,?,?,?)",
            (
                book.id, book.title, ", ".join(author_names),
                " ".join(book.subjects), " ".join(book.bookshelves),
            ),
        )


def _set_indexing_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -65536")
    conn.execute("PRAGMA temp_store = MEMORY")


def _iter_rdf_files(zip_path: Path):
    """Yield (member_name, content_bytes) for each RDF file in the zip+tar."""
    with zipfile.ZipFile(zip_path) as z:
        tar_name = next(m for m in z.namelist() if m.endswith(".tar"))
        with z.open(tar_name) as zf:
            with tarfile.open(fileobj=zf, mode="r|") as tar:
                for member in tar:
                    if not member.isfile() or not member.name.endswith(".rdf"):
                        continue
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    yield member.name, f.read()


def full_index(
    zip_path: Path,
    db_path: Path,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Parse all RDF files and build the DB from scratch."""
    conn = sqlite3.connect(db_path)
    try:
        init_schema(conn)
        _set_indexing_pragmas(conn)
        batcher = _Batcher(conn)
        count = 0
        total = 78503  # approximate; updated during streaming is not needed
        for name, content in _iter_rdf_files(zip_path):
            h = hashlib.md5(content).hexdigest()
            book = parse_rdf(content)
            if book is None:
                continue
            book.content_hash = h
            batcher.add(book)
            count += 1
            if progress_cb and count % BATCH_SIZE == 0:
                progress_cb(count, total)
        batcher.flush()
        if progress_cb:
            progress_cb(count, total)
        conn.execute("PRAGMA optimize")
    finally:
        conn.close()


def update_index(
    zip_path: Path,
    db_path: Path,
    progress_cb: Optional[Callable[[int, int, int, int], None]] = None,
) -> tuple[int, int, int]:
    """
    Incrementally update the DB from a new zip archive.
    Returns (added, updated, skipped).
    """
    conn = sqlite3.connect(db_path)
    try:
        init_schema(conn)
        _set_indexing_pragmas(conn)
        existing = get_content_hashes(conn)
        batcher = _Batcher(conn)
        added = updated = skipped = 0
        total = 78503

        for name, content in _iter_rdf_files(zip_path):
            h = hashlib.md5(content).hexdigest()
            book_id = _book_id_from_path(name)
            if book_id is None:
                continue
            if existing.get(book_id) == h:
                skipped += 1
                processed = added + updated + skipped
                if progress_cb and processed % BATCH_SIZE == 0:
                    progress_cb(processed, total, added, updated)
                continue

            book = parse_rdf(content)
            if book is None:
                continue
            book.content_hash = h

            if book_id in existing:
                delete_book(conn, book_id)
                updated += 1
            else:
                added += 1

            batcher.add(book)
            processed = added + updated + skipped
            if progress_cb and processed % BATCH_SIZE == 0:
                progress_cb(processed, total, added, updated)

        batcher.flush()
        if progress_cb:
            progress_cb(added + updated + skipped, total, added, updated)
        conn.execute("PRAGMA optimize")
        return added, updated, skipped
    finally:
        conn.close()


def index_rdf_file(db_path: Path, rdf_path: Path) -> str:
    """Upsert a single .rdf file into the DB. Returns 'added', 'updated', or 'skipped'."""
    content = rdf_path.read_bytes()
    h = hashlib.md5(content).hexdigest()
    book = parse_rdf(content)
    if book is None:
        return "skipped"
    book.content_hash = h

    conn = sqlite3.connect(db_path)
    try:
        existing = get_content_hashes(conn)
        if existing.get(book.id) == h:
            return "skipped"
        if book.id in existing:
            delete_book(conn, book.id)
            result = "updated"
        else:
            result = "added"
        batcher = _Batcher(conn)
        batcher.add(book)
        batcher.flush()
        return result
    finally:
        conn.close()
