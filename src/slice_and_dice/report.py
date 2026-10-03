"""Fixed-width text tables for printing query results."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from typing import IO, Any, NamedTuple

from slice_and_dice.formatting import format_cell

Row = Mapping[str, Any]


class Column(NamedTuple):
    """A report column.

    Attributes:
        header: Title printed in the header line (and used to look columns up).
        key: Key of the value inside each result row.
        width: Width of the column in characters.
    """

    header: str
    key: str
    width: int


class Report:
    """A text table whose columns are declared up front and rows printed one by one.

    Example::

        report = Report()
        report.add_column("class", "class", 8)
        report.add_column("<speed>", "speed", 8)
        report.render(rows)

    Args:
        abbreviate: Shorten large numbers (``1.2M``). The first column is
            never abbreviated since it usually holds the row's key.
        delimiter: Optional character printed between columns.
        table_delimiter: Optional character printed between columns *and*
            around the table edges; takes precedence over ``delimiter``.
        stream: Where the table is printed; defaults to standard output.
    """

    def __init__(
        self,
        abbreviate: bool = True,
        delimiter: str | None = None,
        table_delimiter: str | None = None,
        stream: IO[str] | None = None,
    ) -> None:
        self.columns: list[Column] = []
        self.abbreviate = abbreviate
        self.delimiter = delimiter or None
        self.table_delimiter = table_delimiter or None
        self.stream = stream

    # ------------------------------------------------------------------ #
    # Column management
    # ------------------------------------------------------------------ #

    def add_column(self, header: str, key: str, width: int) -> None:
        """Append a column; columns without a header or key are ignored."""
        if header and key:
            self.columns.append(Column(header, key, width))

    def remove_column(self, header: str) -> None:
        """Remove the first column with the given header, if any."""
        for column in self.columns:
            if column.header == header:
                self.columns.remove(column)
                return

    def has_column(self, header: str) -> bool:
        """Return whether a column with the given header exists."""
        return any(column.header == header for column in self.columns)

    def filter_empty_columns(self, rows: Iterable[Row]) -> list[str]:
        """Drop columns that hold no meaningful value in any row.

        A value is meaningful when it is truthy and not the string ``"0"``.

        Args:
            rows: The rows that will be printed.

        Returns:
            Headers of the columns that were removed.
        """
        rows = list(rows)

        def has_data(column: Column) -> bool:
            return any(row.get(column.key) and row.get(column.key) != "0" for row in rows)

        kept = [column for column in self.columns if has_data(column)]
        removed = [column.header for column in self.columns if column not in kept]
        self.columns = kept
        return removed

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    @property
    def _separator(self) -> str | None:
        return self.table_delimiter or self.delimiter

    def _join(self, cells: list[str]) -> str:
        """Join pre-formatted cells, inserting delimiters as configured."""
        separator = self._separator
        if not separator or len(cells) < 2:
            return "".join(cells)
        # With a table delimiter every cell is closed by a separator and the
        # line is opened by one; otherwise separators only go between cells.
        closed = len(cells) if self.table_delimiter else len(cells) - 1
        line = self.table_delimiter or ""
        for index, cell in enumerate(cells):
            line += cell + separator + " " if index < closed else cell
        return line

    def format_header(self) -> str:
        """Return the header line."""
        return self._join([format_cell(c.header, c.width) for c in self.columns])

    def format_row(self, row: Row) -> str | None:
        """Return the line for ``row``, or ``None`` if every cell would be empty."""
        if not any(row.get(column.key, "") for column in self.columns):
            return None
        cells = [
            format_cell(row.get(column.key, ""), column.width, self.abbreviate and index > 0)
            for index, column in enumerate(self.columns)
        ]
        return self._join(cells)

    def write_header(self) -> None:
        """Print the header line."""
        print(self.format_header(), file=self.stream or sys.stdout)

    def write_row(self, row: Row) -> None:
        """Print one row (rows with no data in any column are skipped)."""
        line = self.format_row(row)
        if line is not None:
            print(line, file=self.stream or sys.stdout)

    def render(self, rows: Iterable[Row]) -> None:
        """Print the header followed by every row."""
        self.write_header()
        for row in rows:
            self.write_row(row)
