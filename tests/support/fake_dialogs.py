"""Stand-ins for the file pickers of the app window."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FakeDialogs:
    """Answers the questions a real window would ask the user.

    Attributes:
        export: What "choose the export" returns; ``None`` means cancelled.
        save: What "choose where to save" returns; ``None`` means cancelled.
        opened: Folders the app asked to show.
    """

    export: Path | None = None
    save: Path | None = None
    opened: list[Path] = field(default_factory=list)

    def choose_export(self) -> Path | None:
        """Return the configured export."""
        return self.export

    def choose_save(self, suggested_name: str) -> Path | None:
        """Return the configured target; the suggestion is ignored."""
        del suggested_name
        return self.save

    def open_folder(self, folder: Path) -> None:
        """Record the request."""
        self.opened.append(folder)
