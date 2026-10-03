"""Parsing of ``<dimension> [breakpoints] <bp> <bp> ...`` partition expressions."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import NamedTuple

from slice_and_dice.constants import ALL_DIMENSIONS, NUMERIC_DIMENSIONS

_BREAKPOINTS_KEYWORD = "breakpoints"
_DATE_FORMATS = {"date": "%Y-%m-%d", "datetime": "%Y-%m-%d_%H:%M"}


class Partition(NamedTuple):
    """Dimensions to group by, each with its (possibly empty) breakpoints.

    Attributes:
        fields: The dimensions, in the order given.
        breakpoints: One comma-separated breakpoint list per dimension; an
            empty string groups by every distinct value.
    """

    fields: list[str]
    breakpoints: list[str]

    def fields_param(self) -> str:
        """Fields in the ``a;b;c`` form the server expects."""
        return ";".join(self.fields)

    def breakpoints_param(self) -> str:
        """Breakpoints in the ``1,2;;x,y`` form the server expects."""
        return ";".join(self.breakpoints)


def _normalize(field: str, values: list[str]) -> list[str]:
    """Validate and order breakpoints so the server receives clean buckets."""
    if field in NUMERIC_DIMENSIONS:
        try:
            return [str(v) for v in sorted(int(v) for v in values)]
        except ValueError:
            raise ValueError(f"breakpoints of {field} must be integers: {values}") from None
    if field in _DATE_FORMATS:
        fmt = _DATE_FORMATS[field]
        try:
            moments = sorted(datetime.strptime(v, fmt) for v in values)
        except ValueError:
            raise ValueError(
                f"breakpoints of {field} must look like {fmt.replace('%', '')}: {values}"
            ) from None
        return [str(m.date()) if field == "date" else str(m) for m in moments]
    # Textual buckets are prefixes; try the most specific (longest) one first.
    return sorted(values, key=len, reverse=True)


def parse_partition(args: str, dimensions: Collection[str] = ALL_DIMENSIONS) -> Partition:
    """Parse a partition expression.

    Examples:
        >>> parse_partition("network")
        Partition(fields=['network'], breakpoints=[''])
        >>> parse_partition("size breakpoints 50000 10000 geo")
        Partition(fields=['size', 'geo'], breakpoints=['10000,50000', ''])

    Args:
        args: Dimensions, each optionally followed by breakpoint values. The
            word ``breakpoints`` before the values is optional.
        dimensions: The dimension names that start a new group.

    Returns:
        The parsed partition. An empty ``args`` yields an empty partition.

    Raises:
        ValueError: If the expression does not start with a dimension or a
            breakpoint does not fit its dimension's type.
    """
    tokens = args.split()
    starts = [index for index, token in enumerate(tokens) if token in dimensions]
    if tokens and (not starts or starts[0] != 0):
        stray = tokens[: starts[0]] if starts else tokens
        raise ValueError(f"expected a dimension, got: {' '.join(stray)}")

    fields: list[str] = []
    breakpoints: list[str] = []
    ends = [*starts[1:], len(tokens)] if starts else []
    for start, end in zip(starts, ends, strict=True):
        field = tokens[start]
        values = tokens[start + 1 : end]
        if values and values[0] == _BREAKPOINTS_KEYWORD:
            values = values[1:]
        fields.append(field)
        breakpoints.append(",".join(_normalize(field, values)))
    return Partition(fields, breakpoints)
