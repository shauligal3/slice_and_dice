"""A single filter condition narrowing the data set (one level of the scope stack)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from slice_and_dice.dimension_value import DimensionValue

_OPERATOR_SYMBOLS: Final[dict[str, str]] = {
    "eq": "=",
    "gt": ">",
    "lt": "<",
    "lte": "<=",
    "gte": ">=",
}


@dataclass
class Scope:
    """A condition such as ``geo = US`` or ``size > 10000``.

    A scope is either *unmapped* (only the condition is known and the server
    has to evaluate it) or *mapped* (the server already returned an id for the
    resulting subset, e.g. a row of a previous breakdown).

    Attributes:
        key: The dimension being filtered.
        op: The operator, one of :data:`~slice_and_dice.constants.OPERATORS`,
            or ``"range"`` for a breakpoint bucket of a breakdown.
        value: The operand, as typed by the user.
        scope_id: Server-side id of the subset, when already known.
        dimension_value: The breakdown row this scope was picked from, if any.
        count: Number of log records in the subset, when known.
    """

    key: str
    op: str
    value: str
    scope_id: int = 0
    dimension_value: DimensionValue | None = None
    count: int = 0

    @property
    def is_mapped(self) -> bool:
        """Whether the server-side subset for this scope is already known."""
        return bool(self.scope_id)

    @property
    def is_range(self) -> bool:
        """Whether the condition bounds a value instead of matching it."""
        return self.op in ("gt", "lt")

    def __str__(self) -> str:
        value = self.value
        if self.op == "range":
            # Breakdown buckets are labelled "lt 100", "gt 500" or "100-500".
            prefix = value[:2]
            if prefix in ("lt", "gt"):
                op = _OPERATOR_SYMBOLS[prefix]
                value = value[3:]
            else:
                op = "="
        else:
            op = _OPERATOR_SYMBOLS.get(self.op, self.op)
        return f"{self.key} {op} {value}".rstrip()
