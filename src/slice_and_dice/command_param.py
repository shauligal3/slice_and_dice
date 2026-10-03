"""Declaration of one keyword accepted by a command grammar."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class CommandParam:
    """A keyword parameter such as ``median`` in ``select median fbu``.

    Attributes:
        keyword: The keyword the user types.
        required: Whether the command is invalid without this keyword.
        min_vals: Minimum number of values that must follow the keyword.
        max_vals: Maximum number of values that may follow the keyword;
            ``0`` declares a flag that takes no value.
        options: The values allowed after the keyword. An empty list accepts
            any value (and offers no completions).
        is_active: Inactive parameters are neither accepted nor completed.
    """

    keyword: str
    required: bool = False
    min_vals: int = 1
    max_vals: int = 1
    options: Sequence[str] = field(default_factory=list)
    is_active: bool = True
