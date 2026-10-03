"""The rows and columns of the last result shown, kept for exporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from slice_and_dice.report import Column


@dataclass
class ResultTable:
    """A result as returned by the server, plus the columns it was shown with.

    Attributes:
        rows: The result rows.
        columns: The columns displayed; an empty list means "every key".
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
