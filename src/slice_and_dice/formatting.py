"""Small text-formatting helpers shared by reports and commands."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pprint import PrettyPrinter
from typing import IO, Any

_SUFFIXES: tuple[tuple[float, str, int], ...] = (
    (1_000_000_000, "G", 2),
    (1_000_000, "M", 2),
    (1_000, "K", 1),
)


def abbreviate_number(value: float) -> str:
    """Render a number compactly, e.g. ``1234567`` -> ``"1.23M"``.

    Args:
        value: The number to render.

    Returns:
        The number scaled to G/M/K units when large; otherwise integers as
        they are and fractions with two decimals.
    """
    for threshold, suffix, decimals in _SUFFIXES:
        if abs(value) > threshold:
            return f"{value / threshold:.{decimals}f}{suffix}"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


def format_cell(value: object, width: int, abbreviate: bool = True) -> str:
    """Format a value into a fixed-width table cell.

    Values longer than the cell are truncated so that at least one space
    always separates adjacent cells.

    Args:
        value: The value to render.
        width: Exact width of the returned string.
        abbreviate: Whether numbers should be shortened with
            :func:`abbreviate_number`.

    Returns:
        A string of exactly ``width`` characters.
    """
    if abbreviate and isinstance(value, (int, float)) and not isinstance(value, bool):
        text = abbreviate_number(value)
    else:
        text = str(value)
    if len(text) >= width:
        return text[: width - 1] + " "
    return text.ljust(width)


def pretty_print_records(
    records: Iterable[Mapping[str, Any]],
    title: str = "",
    stream: IO[str] | None = None,
    copy_to: IO[str] | None = None,
) -> None:
    """Pretty-print a list of dictionaries, one after another.

    Args:
        records: The dictionaries to print.
        title: Optional heading printed first.
        stream: Where to print; defaults to standard output.
        copy_to: An optional second stream (typically a file) that receives
            the same content, without the blank separator lines.
    """
    out = stream if stream is not None else sys.stdout
    records = list(records)
    if title:
        print(title, file=out)
    printer = PrettyPrinter(stream=out)
    for record in records:
        printer.pprint(record)
        print(file=out)
    if copy_to is not None:
        copy_to.write(title + "\n")
        file_printer = PrettyPrinter(stream=copy_to)
        for record in records:
            file_printer.pprint(record)


def _json_default(value: object) -> str:
    """Serialize values the :mod:`json` module does not know about."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def to_json(value: object, indent: int | None = None) -> str:
    """Serialize ``value`` to JSON, stringifying unknown types (ids, dates).

    Server responses originate in MongoDB documents and may contain values
    such as ``ObjectId``; those are written as plain strings.
    """
    return json.dumps(value, indent=indent, default=_json_default)


def timestamp_slug(moment: datetime | None = None) -> str:
    """Return a filesystem-friendly timestamp such as ``2024-05-01_13-45-10``."""
    return (moment or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
