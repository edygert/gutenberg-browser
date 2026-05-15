import sqlite3
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header

from .db import get_book_count, get_bookshelves, get_connection, get_languages, get_subjects, get_book_detail
from .widgets.detail_panel import BookDetail
from .widgets.progress_screen import IndexingProgressScreen
from .widgets.search_panel import SearchPanel

ZIP_PATH = Path("rdf-files.tar.zip")
DB_PATH  = Path("gutenberg.db")


class GutenbergApp(App):
    """Project Gutenberg metadata browser."""

    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("/", "focus_search", "Search", show=True),
        Binding("o", "open_browser", "Open in Browser", show=True),
        Binding("escape", "clear_search", "Clear", show=False),
    ]

    TITLE = "Project Gutenberg Browser"

    def __init__(self, mode: str = "normal") -> None:
        super().__init__()
        self.db: Optional[sqlite3.Connection] = None
        self._mode = mode  # "normal", "update", "reindex"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            yield SearchPanel()
            with VerticalScroll(id="right-scroll"):
                yield BookDetail()
        yield Footer()

    def on_mount(self) -> None:
        if self._mode == "reindex" or not DB_PATH.exists():
            self._start_full_index()
        elif self._mode == "update":
            self._start_update_index()
        else:
            self._open_db()

    # ─── Indexing ──────────────────────────────────────────────────────────

    def _start_full_index(self) -> None:
        if DB_PATH.exists():
            DB_PATH.unlink()
        screen = IndexingProgressScreen("Building index from RDF archive…")
        self.push_screen(screen)
        self.run_worker(
            self._worker_full_index,
            thread=True,
            name="full-index",
            exclusive=True,
        )

    def _start_update_index(self) -> None:
        screen = IndexingProgressScreen("Updating index…")
        self.push_screen(screen)
        self.run_worker(
            self._worker_update_index,
            thread=True,
            name="update-index",
            exclusive=True,
        )

    def _worker_full_index(self) -> None:
        from .indexer import full_index

        def progress(current: int, total: int) -> None:
            self.call_from_thread(self._on_index_progress, current, total)

        full_index(ZIP_PATH, DB_PATH, progress_cb=progress)
        self.call_from_thread(self._on_index_done, 0, 0, 0)

    def _worker_update_index(self) -> None:
        from .indexer import full_index, update_index

        if not DB_PATH.exists():
            def progress(current: int, total: int) -> None:
                self.call_from_thread(self._on_index_progress, current, total)
            full_index(ZIP_PATH, DB_PATH, progress_cb=progress)
            self.call_from_thread(self._on_index_done, 0, 0, 0)
            return

        def progress(current: int, total: int, added: int, updated: int) -> None:
            self.call_from_thread(self._on_index_progress, current, total)

        added, updated, skipped = update_index(ZIP_PATH, DB_PATH, progress_cb=progress)
        self.call_from_thread(self._on_index_done, added, updated, skipped)

    def _on_index_progress(self, current: int, total: int) -> None:
        try:
            screen = self.screen
            if isinstance(screen, IndexingProgressScreen):
                screen.update_progress(current, total)
        except Exception:
            pass

    def _on_index_done(self, added: int, updated: int, skipped: int) -> None:
        try:
            screen = self.screen
            if isinstance(screen, IndexingProgressScreen):
                if skipped > 0:
                    screen.show_summary(added, updated, skipped)
                    self.set_timer(2.0, self._finish_indexing)
                else:
                    self.pop_screen()
                    self._open_db()
        except Exception:
            self._open_db()

    def _finish_indexing(self) -> None:
        try:
            self.pop_screen()
        except Exception:
            pass
        self._open_db()

    # ─── DB setup ──────────────────────────────────────────────────────────

    def _open_db(self) -> None:
        try:
            self.db = get_connection(DB_PATH)
            count = get_book_count(self.db)
            self.sub_title = f"{count:,} books"
            languages  = get_languages(self.db)
            subjects   = get_subjects(self.db)
            bookshelves = get_bookshelves(self.db)
            panel = self.query_one(SearchPanel)
            panel.populate_filters(languages, subjects, bookshelves)
            panel._do_search()
            panel.focus_search()
        except Exception as e:
            self.notify(f"DB error: {e}", severity="error")

    # ─── Actions ───────────────────────────────────────────────────────────

    def action_focus_search(self) -> None:
        try:
            self.query_one(SearchPanel).focus_search()
        except Exception:
            pass

    def action_open_browser(self) -> None:
        try:
            detail = self.query_one(BookDetail)
            if detail.book:
                import webbrowser
                webbrowser.open(f"https://www.gutenberg.org/ebooks/{detail.book.id}")
        except Exception:
            pass

    def action_clear_search(self) -> None:
        try:
            from textual.widgets import Input
            inp = self.query_one("#search-input", Input)
            inp.value = ""
        except Exception:
            pass

    # ─── Book detail ───────────────────────────────────────────────────────

    def show_book_detail(self, book_id: int) -> None:
        if self.db is None:
            return
        book = get_book_detail(self.db, book_id)
        try:
            self.query_one(BookDetail).book = book
        except Exception:
            pass
