from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import Button, Input, Label, ListItem, ListView, Select, Static

from ..models import BookRow


PAGE_SIZE = 50


class BookListItem(ListItem):
    """A ListItem that carries the book ID and row data."""

    def __init__(self, row: BookRow) -> None:
        super().__init__()
        self.book_row = row

    def compose(self) -> ComposeResult:
        title = self.book_row.title
        authors = self.book_row.authors or "Unknown"
        year = (self.book_row.issued or "")[:4]
        title_trunc = title[:42] + "…" if len(title) > 42 else title
        authors_trunc = authors[:28] + "…" if len(authors) > 28 else authors
        year_part = f" [{year}]" if year else ""
        yield Static(f"{title_trunc}", classes="result-title")
        yield Static(f"{authors_trunc}{year_part}", classes="result-authors")


class SearchPanel(Vertical):
    """Left panel: search input, filters, results list, pagination."""

    DEFAULT_CSS = """
    SearchPanel {
        width: 42;
        height: 100%;
        border-right: solid $primary-darken-2;
    }
    SearchPanel #search-input {
        margin: 0 1;
    }
    SearchPanel #filter-bar {
        height: auto;
        margin: 0 1;
    }
    SearchPanel .filter-label {
        color: $text-muted;
        width: auto;
        margin-top: 1;
        padding: 0 1;
    }
    SearchPanel Select {
        width: 1fr;
        margin: 0;
    }
    SearchPanel #results-list {
        height: 1fr;
        border: solid $primary-darken-3;
        margin: 0 1;
    }
    SearchPanel BookListItem {
        padding: 0 1;
    }
    SearchPanel BookListItem .result-title {
        color: $text;
        text-style: bold;
    }
    SearchPanel BookListItem .result-authors {
        color: $text-muted;
    }
    SearchPanel BookListItem.-highlighted .result-title {
        color: $primary;
    }
    SearchPanel BookListItem.-highlighted .result-authors {
        color: $primary-lighten-2;
    }
    SearchPanel #pagination-bar {
        height: auto;
        margin: 0 1;
        align: center middle;
    }
    SearchPanel #page-label {
        width: 1fr;
        text-align: center;
        color: $text-muted;
    }
    SearchPanel #btn-prev, SearchPanel #btn-next {
        width: auto;
        min-width: 6;
    }
    SearchPanel #result-count {
        text-align: center;
        color: $text-muted;
        height: 1;
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._page = 0
        self._total = 0
        self._debounce_timer: Optional[Timer] = None
        self._lang_options: list[tuple[str, str]] = [("All Languages", "")]
        self._subj_options: list[tuple[str, str]] = [("All Subjects", "")]
        self._shelf_options: list[tuple[str, str]] = [("All Shelves", "")]

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search title or author…", id="search-input")
        with Vertical(id="filter-bar"):
            yield Select(self._lang_options, value="", id="lang-filter", allow_blank=False)
            yield Select(self._subj_options, value="", id="subj-filter", allow_blank=False)
            yield Select(self._shelf_options, value="", id="shelf-filter", allow_blank=False)
        yield Static("", id="result-count")
        yield ListView(id="results-list")
        with Horizontal(id="pagination-bar"):
            yield Button("← Prev", id="btn-prev", variant="default")
            yield Label("", id="page-label")
            yield Button("Next →", id="btn-next", variant="default")

    def populate_filters(self, languages, subjects, bookshelves) -> None:
        """Called by the app once the DB is ready."""
        self._lang_options = [("All Languages", "")] + [
            (f"{code}  ({cnt:,})", code) for code, cnt in languages
        ]
        self._subj_options = [("All Subjects", "")] + [
            (name[:40], name) for name, _ in subjects
        ]
        self._shelf_options = [("All Shelves", "")] + [
            (name[:40], name) for name, _ in bookshelves
        ]
        try:
            self.query_one("#lang-filter", Select).set_options(
                (label, val) for label, val in self._lang_options
            )
            self.query_one("#subj-filter", Select).set_options(
                (label, val) for label, val in self._subj_options
            )
            self.query_one("#shelf-filter", Select).set_options(
                (label, val) for label, val in self._shelf_options
            )
        except Exception:
            pass

    # ─── reactive search inputs ────────────────────────────────────────────

    def _get_query(self) -> str:
        try:
            return self.query_one("#search-input", Input).value.strip()
        except Exception:
            return ""

    def _get_lang(self) -> str:
        try:
            v = self.query_one("#lang-filter", Select).value
            return "" if v is Select.NULL or v == "" else str(v)
        except Exception:
            return ""

    def _get_subject(self) -> str:
        try:
            v = self.query_one("#subj-filter", Select).value
            return "" if v is Select.NULL or v == "" else str(v)
        except Exception:
            return ""

    def _get_shelf(self) -> str:
        try:
            v = self.query_one("#shelf-filter", Select).value
            return "" if v is Select.NULL or v == "" else str(v)
        except Exception:
            return ""

    def _schedule_search(self, reset_page: bool = True) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        if reset_page:
            self._page = 0
        self._debounce_timer = self.set_timer(0.25, self._do_search)

    def _do_search(self) -> None:
        from ..db import search_books
        conn = self.app.db  # type: ignore[attr-defined]
        if conn is None:
            return
        rows, total = search_books(
            conn,
            query=self._get_query(),
            lang_code=self._get_lang(),
            subject=self._get_subject(),
            bookshelf=self._get_shelf(),
            page=self._page,
            page_size=PAGE_SIZE,
        )
        self._total = total
        self._populate_results(rows)
        self._update_pagination()

    def _populate_results(self, rows: list[BookRow]) -> None:
        lv = self.query_one("#results-list", ListView)
        lv.clear()
        for row in rows:
            lv.append(BookListItem(row))

        count_label = self.query_one("#result-count", Static)
        count_label.update(f"{self._total:,} books found")

    def _update_pagination(self) -> None:
        pages = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.query_one("#page-label", Label).update(f"Page {self._page + 1} / {pages}")
        self.query_one("#btn-prev", Button).disabled = self._page == 0
        self.query_one("#btn-next", Button).disabled = self._page >= pages - 1

    # ─── event handlers ────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._schedule_search(reset_page=True)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id in ("lang-filter", "subj-filter", "shelf-filter"):
            self._schedule_search(reset_page=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-prev" and self._page > 0:
            self._page -= 1
            self._schedule_search(reset_page=False)
            event.stop()
        elif event.button.id == "btn-next":
            pages = max(1, (self._total + PAGE_SIZE - 1) // PAGE_SIZE)
            if self._page < pages - 1:
                self._page += 1
                self._schedule_search(reset_page=False)
            event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, BookListItem):
            self.app.show_book_detail(event.item.book_row.id)  # type: ignore[attr-defined]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, BookListItem):
            self.app.show_book_detail(event.item.book_row.id)  # type: ignore[attr-defined]

    def focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()
