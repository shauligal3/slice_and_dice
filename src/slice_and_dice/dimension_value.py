"""One row of a single-dimension breakdown, remembered so the user can step into it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


def _number(value: object) -> float:
    """Coerce a server value to a number, treating missing values as zero."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        return float(str(value))
    except ValueError:
        return 0.0


@dataclass
class DimensionValue:
    """Statistics for one value of the dimension the user last grouped by.

    After ``group_by network`` the shell keeps one ``DimensionValue`` per
    network so that ``in LTE`` can jump straight into that subset, reusing the
    server-side scope id and the counts that were already computed.

    Attributes:
        scope_id: Server-side id of the subset holding this value.
        acc_ct: Number of accelerated requests.
        byp_ct: Number of bypassed (control group) requests.
        acc_spd: Median download speed of accelerated requests.
        byp_spd: Median download speed of bypassed requests.
        acc_fbu: Median time to first byte of accelerated requests.
        byp_fbu: Median time to first byte of bypassed requests.
        extra: Any other columns the server returned for the row.
    """

    scope_id: int = 0
    acc_ct: float = 0
    byp_ct: float = 0
    acc_spd: float = 0
    byp_spd: float = 0
    acc_fbu: float = 0
    byp_fbu: float = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> DimensionValue:
        """Build an instance from a breakdown row returned by the server."""
        known = {"scope_id", "acc_ct", "byp_ct", "acc_spd", "byp_spd", "acc_fbu", "byp_fbu"}
        return cls(
            scope_id=int(_number(row.get("scope_id", 0))),
            acc_ct=_number(row.get("acc_ct", 0)),
            byp_ct=_number(row.get("byp_ct", 0)),
            acc_spd=_number(row.get("acc_spd", 0)),
            byp_spd=_number(row.get("byp_spd", 0)),
            acc_fbu=_number(row.get("acc_fbu", 0)),
            byp_fbu=_number(row.get("byp_fbu", 0)),
            extra={k: v for k, v in row.items() if k not in known},
        )

    @property
    def total_ct(self) -> int:
        """Total number of requests, accelerated and bypassed."""
        return int(self.acc_ct + self.byp_ct)

    def __str__(self) -> str:
        return f"sid {self.scope_id}"
