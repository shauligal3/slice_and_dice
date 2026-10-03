"""Definitions of saved (or ad-hoc) policy/projection reports."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from slice_and_dice.constants import ALL_DIMENSIONS
from slice_and_dice.parsed_command import ParamValues, as_list

#: ``(dimension, comma-separated breakpoints)``.
FieldSpec = tuple[str, str]

#: Turns an outcome such as ``"median fbu"`` into server columns (``["median(fbu)"]``).
OutcomeParser = Callable[[str], list[str] | None]


def _sorted_breakpoints(values: Iterable[Any]) -> str:
    """Join breakpoints, sorted numerically when possible."""
    items = list(values)
    try:
        items.sort()
    except TypeError:  # mixed numbers and strings
        items.sort(key=str)
    return ",".join(str(item) for item in items)


def _field_specs(entries: Iterable[Any], dimensions: Collection[str]) -> list[FieldSpec]:
    """Parse a report clause: plain dimension names or ``{dimension: [breakpoints]}``."""
    specs: list[FieldSpec] = []
    for entry in entries:
        if isinstance(entry, Mapping):
            for name, values in entry.items():
                if name in dimensions:
                    specs.append((name, _sorted_breakpoints(as_list(values))))
        elif isinstance(entry, str) and entry in dimensions:
            specs.append((entry, ""))
    return specs


def _join(specs: Iterable[FieldSpec]) -> tuple[str, str]:
    """Return the ``;``-joined fields and breakpoints of ``specs``."""
    specs = list(specs)
    return ";".join(f for f, _ in specs), ";".join(b for _, b in specs)


@dataclass
class ReportSpec:
    """A report comparing outcomes across policies, controlled for confounders.

    Reports are stored on the server as documents like::

        {
          "name": "burst-by-network",
          "control-fields-no-agg": ["network", {"size": [10000, 50000]}],
          "control-fields-agg": ["hour"],
          "policy-fields": [{"max_burst": [3000, 6000]}],
          "outcome": ["median fbu", "median dcu"]
        }

    *Control* fields split the data into comparable cohorts (the
    ``-no-agg`` ones also appear in the output; the ``-agg`` ones are
    aggregated over), *policy* fields are the knobs being evaluated and
    *outcomes* are the aggregated metrics to compare.

    Attributes:
        name: Report name.
        outcomes: Server column names of the outcomes, e.g. ``median(fbu)``.
        control_agg: Control fields aggregated over.
        control_no_agg: Control fields kept in the output.
        policy: Policy fields.
    """

    name: str
    outcomes: list[str] = field(default_factory=list)
    control_agg: list[FieldSpec] = field(default_factory=list)
    control_no_agg: list[FieldSpec] = field(default_factory=list)
    policy: list[FieldSpec] = field(default_factory=list)

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        parse_outcome: OutcomeParser,
        dimensions: Collection[str] = ALL_DIMENSIONS,
    ) -> ReportSpec:
        """Build a spec from a report document.

        Args:
            document: The report document (see the class docstring).
            parse_outcome: Converts an outcome expression into server columns;
                outcomes that do not yield exactly one column are skipped.
            dimensions: Known dimension names; unknown fields are ignored.

        Raises:
            ValueError: If ``datetime`` is a control field without breakpoints,
                which would produce one cohort per log line.
        """
        outcome_names: list[str] = []
        for entry in as_list(document.get("outcome", [])):
            if isinstance(entry, Mapping):
                outcome_names.extend(str(key) for key in entry)
            elif isinstance(entry, str):
                outcome_names.append(entry)
        outcomes = []
        for name in outcome_names:
            columns = parse_outcome(name)
            if columns and len(columns) == 1:
                outcomes.append(columns[0])

        control_no_agg = _field_specs(document.get("control-fields-no-agg", []), dimensions)
        control_agg = [
            spec
            for spec in _field_specs(document.get("control-fields-agg", []), dimensions)
            if spec not in control_no_agg
        ]
        for name, breakpoints in control_agg + control_no_agg:
            if name == "datetime" and not breakpoints:
                raise ValueError("the datetime control field needs breakpoints")

        return cls(
            name=str(document.get("name", "no-name")),
            outcomes=outcomes,
            control_agg=control_agg,
            control_no_agg=control_no_agg,
            policy=_field_specs(document.get("policy-fields", []), dimensions),
        )

    @staticmethod
    def document_from_command(params: Mapping[str, ParamValues]) -> dict[str, Any]:
        """Build a report document from parsed ``build_report`` arguments.

        ``control``, ``latent``, ``policy`` and ``outcome`` keywords map to the
        document clauses; a ``bp_<dimension>`` keyword attaches breakpoints to
        that dimension.
        """
        clauses = {
            "control": "control-fields-no-agg",
            "latent": "control-fields-agg",
            "policy": "policy-fields",
        }
        document: dict[str, Any] = {"name": "ad-hoc", "timeout": params.get("timeout") or 120}
        for keyword, clause in clauses.items():
            if keyword not in params:
                continue
            entries: list[Any] = []
            for value in as_list(params[keyword]):
                breakpoints = params.get(f"bp_{value}")
                entries.append({value: as_list(breakpoints)} if breakpoints is not None else value)
            document[clause] = entries
        if "outcome" in params:
            document["outcome"] = [f"median {value}" for value in as_list(params["outcome"])]
        return document

    # ------------------------------------------------------------------ #
    # Server parameters
    # ------------------------------------------------------------------ #

    @property
    def control(self) -> list[FieldSpec]:
        """All control fields, aggregated first."""
        return self.control_agg + self.control_no_agg

    def projection_params(self) -> dict[str, str]:
        """Parameters of the ``/scope/gen_report`` endpoint."""
        control_fields, control_breakpoints = _join(self.control)
        policy_fields, policy_breakpoints = _join(self.policy)
        return {
            "control_fields": control_fields,
            "breakpoints_control": control_breakpoints,
            "outcome_fields": ",".join(self.outcomes),
            "policy_fields": policy_fields,
            "policy_fields_breakpoints": policy_breakpoints,
        }

    def best_policy_params(self) -> dict[str, str]:
        """Parameters of the ``/scope/best_policy`` endpoint."""
        agg_fields, agg_breakpoints = _join(self.control_agg)
        no_agg_fields, no_agg_breakpoints = _join(self.control_no_agg)
        policy_fields, policy_breakpoints = _join(self.policy)
        return {
            "control_fields_agg": agg_fields,
            "breakpoints_agg": agg_breakpoints,
            "control_fields_no_agg": no_agg_fields,
            "breakpoints_no_agg": no_agg_breakpoints,
            "outcome_fields": ",".join(self.outcomes),
            "policy_fields": policy_fields,
            "policy_fields_breakpoints": policy_breakpoints,
        }
