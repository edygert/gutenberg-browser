import webbrowser
from typing import Optional

from textual.app import ComposeResult
from textual.widgets import Button, Static
from textual.containers import Vertical

from ..models import Book


_PLACEHOLDER = "[dim]Select a book from the list to view its details.[/dim]"


def _fmt_author(author) -> str:
    name = author.name
    if author.birthdate or author.deathdate:
        b = str(author.birthdate) if author.birthdate else "?"
        d = str(author.deathdate) if author.deathdate else "?"
        name += f" ({b}–{d})"
    return name


def _fmt_size(size: Optional[int]) -> str:
    if size is None:
        return ""
    if size >= 1_048_576:
        return f" ({size / 1_048_576:.1f} MB)"
    if size >= 1024:
        return f" ({size // 1024} KB)"
    return f" ({size} B)"


def _mime_label(mime: str) -> str:
    for key, label in (
        ("application/epub+zip",           "EPUB"),
        ("application/x-mobipocket-ebook", "Kindle"),
        ("application/x-kf8",              "Kindle KF8"),
        ("text/plain",                     "Plain Text"),
        ("text/html",                      "HTML"),
        ("application/zip",                "ZIP"),
    ):
        if mime.startswith(key):
            return label
    return mime.split(";")[0].strip()


def _esc(text: str) -> str:
    """Escape Rich markup special characters."""
    return text.replace("\\", "\\\\").replace("[", r"\[")


def _render_text(book: Book) -> str:
    lines: list[str] = []

    lines.append(f"[bold $accent]{_esc(book.title)}[/]")
    lines.append("")

    if book.authors:
        label = "Author" if len(book.authors) == 1 else "Authors"
        lines.append(f"[bold]{label}[/bold]")
        for a in book.authors:
            lines.append(f"  {_esc(_fmt_author(a))}")
        lines.append("")

    meta: list[str] = []
    if book.issued:
        meta.append(f"[dim]Issued:[/dim] {book.issued}")
    if book.language:
        meta.append(f"[dim]Language:[/dim] {book.language.upper()}")
    if book.downloads:
        meta.append(f"[dim]Downloads:[/dim] {book.downloads:,}")
    if meta:
        lines.append("  ".join(meta))
        lines.append("")

    if book.summary:
        lines.append("[bold]Summary[/bold]")
        text = book.summary[:600]
        if len(book.summary) > 600:
            text += "…"
        lines.append(_esc(text))
        lines.append("")

    if book.subjects:
        lines.append("[bold $secondary]Subjects[/bold $secondary]")
        for s in book.subjects[:12]:
            lines.append(f"  • {_esc(s)}")
        if len(book.subjects) > 12:
            lines.append(f"  [dim]… and {len(book.subjects) - 12} more[/dim]")
        lines.append("")

    if book.bookshelves:
        lines.append("[bold $secondary]Bookshelves[/bold $secondary]")
        for s in book.bookshelves:
            lines.append(f"  • {_esc(s)}")
        lines.append("")

    readable = [
        f for f in book.formats
        if not f.mime.startswith("application/rdf")
        and not f.mime.startswith("image/")
    ]
    if readable:
        lines.append("[bold $secondary]Formats[/bold $secondary]")
        for f in readable[:8]:
            lines.append(f"  • {_mime_label(f.mime)}{_fmt_size(f.size)}")

    return "\n".join(lines)


class BookDetail(Vertical):
    """Right-side detail panel. Fixed structure: one Static + one Button."""

    DEFAULT_CSS = """
    BookDetail {
        padding: 1 2;
        height: auto;
    }
    BookDetail #detail-text {
        height: auto;
    }
    BookDetail #open-browser-btn {
        height: auto;
        margin-top: 1;
        width: auto;
        display: none;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._current_book: Optional[Book] = None

    def compose(self) -> ComposeResult:
        yield Static(_PLACEHOLDER, id="detail-text", markup=True)
        yield Button("Open in Browser", id="open-browser-btn", variant="primary")

    def load_book(self, book: Optional[Book]) -> None:
        self._current_book = book
        text_widget = self.query_one("#detail-text", Static)
        btn = self.query_one("#open-browser-btn", Button)
        if book is None:
            text_widget.update(_PLACEHOLDER)
            btn.display = False
        else:
            text_widget.update(_render_text(book))
            btn.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "open-browser-btn" and self._current_book:
            webbrowser.open(
                f"https://www.gutenberg.org/ebooks/{self._current_book.id}"
            )
            event.stop()
