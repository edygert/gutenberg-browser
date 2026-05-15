from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, ProgressBar
from textual.containers import Center, Middle, Vertical


class IndexingProgressScreen(ModalScreen):
    """Full-screen modal shown while the indexer runs."""

    DEFAULT_CSS = """
    IndexingProgressScreen {
        align: center middle;
    }
    IndexingProgressScreen > Vertical {
        width: 70;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2 4;
    }
    IndexingProgressScreen #progress-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }
    IndexingProgressScreen ProgressBar {
        margin: 1 0;
    }
    IndexingProgressScreen #progress-label {
        text-align: center;
        color: $text-muted;
    }
    IndexingProgressScreen #progress-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    """

    def __init__(self, title: str = "Indexing Project Gutenberg metadata…", total: int = 78503) -> None:
        super().__init__()
        self._title = title
        self._total = total

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, id="progress-title")
            yield Label("This takes about 30–60 seconds and only happens once.", id="progress-subtitle")
            yield ProgressBar(total=self._total, show_eta=True, id="progress-bar")
            yield Label(f"0 / {self._total:,} books indexed", id="progress-label")

    def update_progress(self, current: int, total: int) -> None:
        try:
            bar = self.query_one("#progress-bar", ProgressBar)
            bar.total = total
            bar.progress = current
            self.query_one("#progress-label", Label).update(
                f"{current:,} / {total:,} books indexed"
            )
        except Exception:
            pass

    def show_summary(self, added: int, updated: int, skipped: int) -> None:
        try:
            self.query_one("#progress-subtitle", Label).update(
                f"Done! Added [bold green]{added:,}[/bold green]  "
                f"Updated [bold yellow]{updated:,}[/bold yellow]  "
                f"Skipped [dim]{skipped:,}[/dim]"
            )
        except Exception:
            pass
