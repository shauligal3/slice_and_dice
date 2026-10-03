"""Named scopes the user saved for later, stored as JSON next to the settings."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ScopeLibrary:
    """A small persistent ``name -> scope expression`` dictionary.

    A saved scope is the textual form of the scope stack, e.g.
    ``"datetime > 2024-05-01 and geo = US"``, which can be replayed with the
    ``in`` command.

    Args:
        path: The JSON file the scopes are stored in.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        """Return every saved scope; a missing file means none are saved.

        Raises:
            OSError: If the file exists but cannot be read.
            ValueError: If the file is not a JSON object.
        """
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        data = json.loads(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError(f"{self.path} does not hold a JSON object")
        return {str(name): str(expression) for name, expression in data.items()}

    def save(self, name: str, expression: str) -> None:
        """Save (or overwrite) a named scope.

        Raises:
            OSError: If the file cannot be written.
        """
        scopes = self.load()
        scopes[name] = expression
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(scopes, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, name: str) -> str | None:
        """Return the expression saved under ``name``, if any."""
        return self.load().get(name)
