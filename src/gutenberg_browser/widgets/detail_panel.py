import webbrowser
from typing import Optional

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Button, Label, Static
from textual.containers import Vertical, VerticalScroll

from ..models import Book


_PLACEHOLDER = (
    "[dim]Select a book from the list\nto view its details.[/dim]"
)


def _fmt_author(author) -> str:
    parts = [author.name]
    if author.birthdate or author.deathdate:
        b = str(author.birthdate) if author.birthdate else "?"
        d = str(author.deathdate) if author.deathdate else "?"
        parts.append(f"({b}–{d})")
    return " ".join(parts)


def _fmt_size(size: Optional[int]) -> str:
    if size is None:
        return ""
    if size >= 1_048_576:
        return f" ({size / 1_048_576:.1f} MB)"
    if size >= 1024:
        return f" ({size // 1024} KB)"
    return f" ({size} B)"


def _mime_label(mime: str) -> str:
    table = {
        "application/epub+zip":               "EPUB",
        "application/x-mobipocket-ebook":     "Kindle (MOBI)",
        "application/x-kf8":                  "Kindle (KF8)",
        "text/plain":                          "Plain Text",
        "text/html":                           "HTML",
        "application/rdf+xml":                "RDF/XML",
        "application/zip":                    "ZIP",
        "image/jpeg":                         "JPEG",
        "image/png":                          "PNG",
    }
    for key, label in table.items():
        if mime.startswith(key):
            return label
    return mime.split(";")[0].strip()


class BookDetail(Vertical):
    """Right-side panel showing full metadata for the selected book."""

    book: reactive[Optional[Book]] = reactive(None, layout=True)

    DEFAULT_CSS = """
    BookDetail {
        padding: 1 2;
        height: 100%;
    }
    BookDetail #detail-placeholder {
        color: $text-muted;
        text-align: center;
        margin-top: 4;
        height: 100%;
        content-align: center middle;
    }
    BookDetail #detail-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 0;
    }
    BookDetail .detail-section-header {
        text-style: bold;
        color: $secondary;
        margin-top: 1;
    }
    BookDetail .detail-row {
        color: $text;
    }
    BookDetail .detail-muted {
        color: $text-muted;
    }
    BookDetail #open-browser-btn {
        margin-top: 1;
        width: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(_PLACEHOLDER, id="detail-placeholder", markup=True)

    def watch_book(self, book: Optional[Book]) -> None:
        placeholder = self.query_one("#detail-placeholder", Static)
        for w in list(self.query(".detail-widget")):
            w.remove()
        if book is None:
            placeholder.update(_PLACEHOLDER)
            placeholder.display = True
            return
        placeholder.display = False
        self._render_book(book)

    def _render_book(self, book: Book) -> None:
        widgets = []

        # Title
        title_text = book.title.replace("[", r"\[")
        widgets.append(Static(f"[bold $primary]{title_text}[/]", classes="detail-widget detail-title", markup=True))

        # Authors
        if book.authors:
            author_lines = "\n".join(f"  {_fmt_author(a)}" for a in book.authors)
            widgets.append(Static(
                f"[bold]{('Author' if len(book.authors) == 1 else 'Authors')}:[/] {author_lines}".lstrip(),
                classes="detail-widget detail-row",
                markup=True,
            ))

        # Meta row: issued, language, downloads
        meta_parts = []
        if book.issued:
            meta_parts.append(f"[dim]Issued:[/dim] {book.issued}")
        if book.language:
            meta_parts.append(f"[dim]Language:[/dim] {book.language.upper()}")
        if book.downloads:
            meta_parts.append(f"[dim]Downloads:[/dim] {book.downloads:,}")
        if meta_parts:
            widgets.append(Static("  ".join(meta_parts), classes="detail-widget detail-muted", markup=True))

        # Summary
        if book.summary:
            widgets.append(Static("[bold]Summary[/bold]", classes="detail-widget detail-section-header", markup=True))
            summary_safe = book.summary[:800].replace("[", r"\[")
            if len(book.summary) > 800:
                summary_safe += "…"
            widgets.append(Static(summary_safe, classes="detail-widget detail-row", markup=False))

        # Subjects
        if book.subjects:
            widgets.append(Static("[bold]Subjects[/bold]", classes="detail-widget detail-section-header", markup=True))
            for s in book.subjects[:12]:
                safe = s.replace("[", r"\[")
                widgets.append(Static(f"  • {safe}", classes="detail-widget detail-muted", markup=False))
            if len(book.subjects) > 12:
                widgets.append(Static(f"  … and {len(book.subjects) - 12} more", classes="detail-widget detail-muted", markup=False))

        # Bookshelves
        if book.bookshelves:
            widgets.append(Static("[bold]Bookshelves[/bold]", classes="detail-widget detail-section-header", markup=True))
            for s in book.bookshelves:
                safe = s.replace("[", r"\[")
                widgets.append(Static(f"  • {safe}", classes="detail-widget detail-muted", markup=False))

        # Formats
        readable_fmts = [
            fmt for fmt in book.formats
            if not fmt.mime.startswith("application/rdf") and not fmt.mime.startswith("image/")
        ]
        if readable_fmts:
            widgets.append(Static("[bold]Formats[/bold]", classes="detail-widget detail-section-header", markup=True))
            for fmt in readable_fmts[:8]:
                label = _mime_label(fmt.mime)
                size_str = _fmt_size(fmt.size)
                widgets.append(Static(f"  • {label}{size_str}", classes="detail-widget detail-muted", markup=False))

        # Open in browser button
        widgets.append(Button("Open in Browser  [o]", id="open-browser-btn",
                               variant="primary", classes="detail-widget"))

        self.mount(*widgets)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-browser-btn" and self.book:
            webbrowser.open(f"https://www.gutenberg.org/ebooks/{self.book.id}")
            event.stop()
