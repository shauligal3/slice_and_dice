"""The result of parsing a command line against a :class:`CommandGrammar`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

#: A single parsed value; purely numeric tokens are converted to ``int``.
ParamValue: TypeAlias = str | int

#: What a keyword maps to: nothing (a flag), one value, or several values.
ParamValues: TypeAlias = ParamValue | list[ParamValue] | None


def as_list(values: ParamValues) -> list[ParamValue]:
    """Normalize a keyword's parsed values to a list."""
    if values is None:
        return []
    if isinstance(values, list):
        return values
    return [values]


@dataclass
class ParsedCommand:
    """Parameters, completions and errors produced by parsing one line.

    Attributes:
        completions: Words that may legally follow the parsed line.
        params: Keyword -> value(s). A keyword given without values maps to
            ``None``; one value maps to the value; several map to a list.
        error: Human-readable description of any problems, one per line.
    """

    completions: list[str] = field(default_factory=list)
    params: dict[str, ParamValues] = field(default_factory=dict)
    error: str = ""

    def value_count(self, keyword: str) -> int:
        """Return how many values were given for ``keyword``."""
        return len(as_list(self.params.get(keyword)))

    def append_value(self, keyword: str, value: ParamValue) -> None:
        """Record one more value for ``keyword``."""
        current = self.params.get(keyword)
        if current is None:
            self.params[keyword] = value
        elif isinstance(current, list):
            current.append(value)
        else:
            self.params[keyword] = [current, value]

    def append_error(self, error: str) -> None:
        """Record an error message (empty messages are ignored)."""
        if error:
            self.error = f"{self.error}\n{error}" if self.error else error
