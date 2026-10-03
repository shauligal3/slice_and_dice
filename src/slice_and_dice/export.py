"""Writing results to CSV files."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from slice_and_dice.report import Column


def _all_keys(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the keys of all rows, in order of first appearance."""
    keys: dict[str, None] = {}
    for row in rows:
        keys.update(dict.fromkeys(row))
    return list(keys)


def write_csv(
    path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[Column] = (),
    delimiter: str = ",",
    delimiter_replacement: str | None = None,
    preamble: str | None = None,
) -> int:
    """Write result rows to a CSV file.

    Args:
        path: The file to create (overwritten if it exists).
        rows: The rows to write.
        columns: Columns to export, in order, titled by their headers; when
            empty, every key found in the rows is exported under its own name.
        delimiter: Field delimiter.
        delimiter_replacement: When given, occurrences of the delimiter inside
            text values are replaced with it, for consumers that do not
            understand CSV quoting.
        preamble: An optional line written before the header (e.g. the scope).

    Returns:
        The number of data rows written.
    """
    rows = list(rows)
    keys = [column.key for column in columns] or _all_keys(rows)
    titles = {column.key: column.header for column in columns} or {key: key for key in keys}

    def clean(value: Any) -> Any:
        if delimiter_replacement is not None and isinstance(value, str):
            return value.replace(delimiter, delimiter_replacement)
        return value

    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        if preamble:
            stream.write(preamble + "\n")
        writer = csv.DictWriter(stream, fieldnames=keys, delimiter=delimiter, extrasaction="ignore")
        writer.writerow(titles)
        for row in rows:
            writer.writerow({key: clean(row.get(key, "")) for key in keys})
    return len(rows)
