from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ProgressBar
from textual.containers import Center, Horizontal, Middle, Vertical


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

    def set_phase(self, title: str, subtitle: str = "") -> None:
        try:
            self.query_one("#progress-title", Label).update(title)
            self.query_one("#progress-subtitle", Label).update(subtitle)
        except Exception:
            pass

    def update_download(self, downloaded: int, total: int) -> None:
        try:
            bar = self.query_one("#progress-bar", ProgressBar)
            mb = downloaded / (1024 * 1024)
            if total > 0:
                bar.total = total
                bar.progress = downloaded
                self.query_one("#progress-label", Label).update(
                    f"{mb:.1f} MB / {total / (1024 * 1024):.1f} MB downloaded"
                )
            else:
                # Unknown size: keep the bar indeterminate, show bytes so far.
                bar.total = None
                self.query_one("#progress-label", Label).update(
                    f"{mb:.1f} MB downloaded"
                )
        except Exception:
            pass

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

    def show_error(self, message: str) -> None:
        try:
            self.query_one("#progress-title", Label).update("Download failed")
            self.query_one("#progress-subtitle", Label).update(
                f"[red]{message}[/red]\nPress Esc to dismiss."
            )
            self.query_one("#progress-bar", ProgressBar).display = False
            self.query_one("#progress-label", Label).update("")
            self._dismissable = True
        except Exception:
            pass

    def on_key(self, event) -> None:
        if getattr(self, "_dismissable", False) and event.key in ("escape", "enter"):
            self.dismiss()


class ConfirmRefreshScreen(ModalScreen[bool]):
    """Confirmation dialog before downloading + refreshing the catalog."""

    DEFAULT_CSS = """
    ConfirmRefreshScreen {
        align: center middle;
    }
    ConfirmRefreshScreen > Vertical {
        width: 64;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 4;
    }
    ConfirmRefreshScreen #confirm-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
        text-align: center;
    }
    ConfirmRefreshScreen #confirm-message {
        text-align: center;
        margin-bottom: 1;
    }
    ConfirmRefreshScreen Horizontal {
        height: auto;
        align: center middle;
    }
    ConfirmRefreshScreen Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("n", "cancel", "Cancel"),
        Binding("y", "confirm", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Refresh catalog", id="confirm-title")
            yield Label(
                "Download the latest catalog (~180 MB) from gutenberg.org\n"
                "and update the index?",
                id="confirm-message",
            )
            with Horizontal():
                yield Button("Refresh", variant="primary", id="confirm-yes")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
