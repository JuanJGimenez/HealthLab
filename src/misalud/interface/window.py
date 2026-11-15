"""Open the app window and connect it to the ``Api``.

This is the only module that touches the windowing library. It holds no logic:
it shows the page, and passes file dialogs to the operating system. What a
start does is decided in ``startup``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from misalud.config import APP_NAME, Paths, default_paths
from misalud.interface import startup
from misalud.interface.api import Api

WEB_DIR = Path(__file__).resolve().parent / "web"
WINDOW_SIZE = (1280, 860)
MINIMUM_SIZE = (900, 600)


class WindowDialogs:  # pragma: no cover - needs a real window; checked by hand on Windows
    """File pickers and the file explorer, through the app window."""

    def __init__(self) -> None:
        """Start without a window; ``attach`` sets it once it exists."""
        self._window: Any = None

    def attach(self, window: Any) -> None:
        """Remember the window the dialogs belong to."""
        self._window = window

    def _ask(self, kind: Any, **options: Any) -> Path | None:
        """Show a file dialog and return the chosen path, if any."""
        chosen = self._window.create_file_dialog(kind, **options)
        if not chosen:
            return None
        return Path(chosen if isinstance(chosen, str) else chosen[0])

    def choose_export(self) -> Path | None:
        """Ask for the Samsung Health zip to import."""
        import webview

        return self._ask(webview.FileDialog.OPEN, file_types=("Samsung Health (*.zip)",))

    def choose_save(self, suggested_name: str) -> Path | None:
        """Ask where to save a file."""
        import webview

        return self._ask(webview.FileDialog.SAVE, save_filename=suggested_name)

    def open_folder(self, folder: Path) -> None:
        """Show a folder in the file explorer."""
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(folder)])


def _open_window(paths: Paths) -> None:  # pragma: no cover - needs a real window
    """Show the app window and return when the user closes it."""
    import webview

    dialogs = WindowDialogs()
    api = Api(paths, dialogs)
    window = webview.create_window(
        APP_NAME,
        url=str(WEB_DIR / "index.html"),
        js_api=api,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MINIMUM_SIZE,
    )
    dialogs.attach(window)
    webview.start()


def _show_error(message: str) -> None:  # pragma: no cover - needs a real desktop
    """Tell the user the app could not start.

    A packaged app has no console, so on Windows the message goes in a dialog
    box. Elsewhere it is printed.
    """
    if sys.platform == "win32":
        import ctypes

        error_icon = 0x10
        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, error_icon)
    else:
        print(message, file=sys.stderr)


def main() -> None:  # pragma: no cover - needs a real window; checked by hand on Windows
    """Open MiSalud, or run the self-check with ``--check``."""
    sys.exit(startup.run(sys.argv[1:], default_paths(), _open_window, _show_error))
