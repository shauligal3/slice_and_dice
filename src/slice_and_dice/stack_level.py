"""A snapshot of the shell's position, pushed when the user steps into a scope."""

from __future__ import annotations

from dataclasses import dataclass, field

from slice_and_dice.dimension_value import DimensionValue
from slice_and_dice.scope import Scope


@dataclass
class StackLevel:
    """Everything needed to return to a previous scope with ``out``.

    Attributes:
        scope_id: Server-side id of the subset at this level (0 if unknown).
        scope: The condition that produced this level (``None`` at the root).
        count: Number of log records in the subset.
        dimension: The dimension last grouped by at this level, if any.
        dimension_values: Rows of that breakdown, keyed by dimension value.
        acc_scope_id: Server-side id of the accelerated part of the subset.
        byp_scope_id: Server-side id of the bypassed part of the subset.
    """

    scope_id: int = 0
    scope: Scope | None = None
    count: int = 0
    dimension: str | None = None
    dimension_values: dict[str, DimensionValue] = field(default_factory=dict)
    acc_scope_id: int = 0
    byp_scope_id: int = 0

    def describe(self) -> str:
        """Return a one-line description used by ``show stack``."""
        text = f"[{self.scope_id}] {self.scope or 'all'} #ct={self.count}"
        if self.dimension:
            values = " ".join(f"{k}: {v}" for k, v in self.dimension_values.items())
            text += f" , {self.dimension}={values}"
        return text
