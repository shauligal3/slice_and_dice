"""Grammars (keywords, values, completions) of the shell's structured commands."""

from __future__ import annotations

from slice_and_dice.command_grammar import CommandGrammar
from slice_and_dice.command_param import CommandParam
from slice_and_dice.constants import (
    AGGREGATES,
    ALL_DIMENSIONS,
    CALCULATED_COLUMNS,
    NUMERIC_DIMENSIONS,
    SETTINGS,
)

#: Flag accepted by ``order_by`` to sort in descending order.
DESCENDING = "desc"


def aggregate_grammar() -> CommandGrammar:
    """Grammar of ``select`` / ``order_by``: ``median fbu dcu perc95 speed [desc]``."""
    grammar = CommandGrammar("aggregate")
    for aggregate in AGGREGATES:
        grammar.add_param(CommandParam(aggregate, max_vals=5, options=NUMERIC_DIMENSIONS))
    for column in CALCULATED_COLUMNS:
        grammar.add_param(CommandParam(column, min_vals=0, max_vals=0))
    grammar.add_param(CommandParam(DESCENDING, min_vals=0, max_vals=0))
    return grammar


def settings_grammar() -> CommandGrammar:
    """Grammar of ``set``: ``set <setting> [<value>]``; no value resets the setting."""
    grammar = CommandGrammar("set")
    for setting in SETTINGS:
        grammar.add_param(CommandParam(setting, min_vals=0, max_vals=1))
    return grammar


def report_grammar() -> CommandGrammar:
    """Grammar of ``build_report`` / ``projection_report``.

    Example: ``control network size policy max_burst outcome fbu bp_size 10000 50000``.
    """
    grammar = CommandGrammar("report")
    for dimension in ALL_DIMENSIONS:
        grammar.add_param(CommandParam(f"bp_{dimension}", min_vals=1, max_vals=10))
    grammar.add_param(CommandParam("control", required=True, max_vals=5, options=ALL_DIMENSIONS))
    grammar.add_param(CommandParam("latent", max_vals=5, options=ALL_DIMENSIONS))
    grammar.add_param(CommandParam("policy", required=True, max_vals=5, options=ALL_DIMENSIONS))
    grammar.add_param(CommandParam("outcome", max_vals=5, options=ALL_DIMENSIONS))
    grammar.add_param(CommandParam("timeout"))
    return grammar
