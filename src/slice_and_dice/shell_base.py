"""State, I/O and server plumbing shared by every command group of the shell."""

from __future__ import annotations

import cmd
import inspect
import logging
import traceback
from collections.abc import Mapping
from typing import IO, Any

from slice_and_dice.api_client import ApiClient, JsonObject
from slice_and_dice.constants import ALL_DIMENSIONS
from slice_and_dice.dimension_value import DimensionValue
from slice_and_dice.grammars import DESCENDING, aggregate_grammar
from slice_and_dice.parsed_command import ParamValues, as_list
from slice_and_dice.report import Report
from slice_and_dice.result_table import ResultTable
from slice_and_dice.scope import Scope
from slice_and_dice.scope_library import ScopeLibrary
from slice_and_dice.settings import Settings
from slice_and_dice.shell_options import ShellOptions
from slice_and_dice.stack_level import StackLevel

logger = logging.getLogger(__name__)

#: Commands that page through results: pressing Enter repeats them.
_PAGING_COMMANDS = ("group_by", "order_by", "samples", "timelines")


class ShellBase(cmd.Cmd):
    """Common foundation of the interactive shell.

    The shell keeps a *stack of scopes*: each ``in <condition>`` narrows the
    current subset of the data and pushes the previous position on the stack,
    and ``out`` pops it. The server holds the actual subsets and identifies
    them by *scope ids*; the client only remembers ids, conditions and counts.

    Command groups (scope navigation, breakdowns, samples, reports, settings)
    are implemented by subclasses and combined in
    :class:`~slice_and_dice.shell.Shell`.

    Args:
        client: Connection to the analytics server.
        settings: User settings.
        scope_library: Storage for named scopes.
        options: Start-up options.
        stdout: Where output goes; defaults to standard output.
        stdin: Where input comes from; defaults to standard input.
    """

    prompt = "(perf) "

    def __init__(
        self,
        client: ApiClient,
        settings: Settings,
        scope_library: ScopeLibrary,
        *,
        options: ShellOptions | None = None,
        stdout: IO[str] | None = None,
        stdin: IO[str] | None = None,
    ) -> None:
        super().__init__(stdin=stdin, stdout=stdout)
        if stdin is not None:
            self.use_rawinput = False
        self.client = client
        self.settings = settings
        self.scope_library = scope_library
        self.options = options or ShellOptions()
        self.aggregate_grammar = aggregate_grammar()

        #: Dimensions in the order samples display them (``select`` reorders).
        self.dimensions: list[str] = list(ALL_DIMENSIONS)
        #: Aggregate columns added to breakdowns with ``select``.
        self.breakdown_selected: list[str] = []
        #: When the server process started, to detect restarts.
        self.server_started: Any = 0
        self.password_verified = False
        self.echo_commands = False
        self.reset_state()

    # ------------------------------------------------------------------ #
    # Session state
    # ------------------------------------------------------------------ #

    def reset_state(self) -> None:
        """Forget the scope stack and every cached result."""
        self.scope_stack: list[StackLevel] = []
        self.scope_id = 0
        self.scope: Scope | None = None
        self.count = 0
        self.acc_scope_id = 0
        self.byp_scope_id = 0
        self.acc_ct: float = 0
        self.byp_ct: float = 0
        self.dimension: str | None = None
        self.dimension_values: dict[str, DimensionValue] = {}
        self.last_group_command: str | None = None
        self.last_result: ResultTable | None = None
        self.samples: list[dict[str, Any]] = []
        self.last_samples_command: str | None = None
        self.samples_offset = 0
        self.breakdown_offset = 0
        self.breakdown_order_by: str | None = None
        self.samples_order_by: str | None = None
        self.report_kind = ""
        self.sql = ""
        self.in_recovery = False
        self.cid: str | None = self.options.cid

    def clear_results(self) -> None:
        """Drop cached results after the scope changed."""
        self.dimension = None
        self.dimension_values = {}
        self.last_group_command = None
        self.last_result = None
        self.acc_scope_id = 0
        self.byp_scope_id = 0
        self.samples = []
        self.samples_offset = 0
        self.breakdown_offset = 0

    def current_level(self) -> StackLevel:
        """Return a snapshot of the current position."""
        return StackLevel(
            scope_id=self.scope_id,
            scope=self.scope,
            count=self.count,
            dimension=self.dimension,
            dimension_values=self.dimension_values,
            acc_scope_id=self.acc_scope_id,
            byp_scope_id=self.byp_scope_id,
        )

    def restore_level(self, level: StackLevel) -> None:
        """Move back to a previously saved position."""
        self.scope_id = level.scope_id
        self.scope = level.scope
        self.count = level.count
        self.dimension = level.dimension
        self.dimension_values = level.dimension_values
        self.acc_scope_id = level.acc_scope_id
        self.byp_scope_id = level.byp_scope_id

    def all_levels(self) -> list[StackLevel]:
        """Return the stack followed by the current position."""
        return [*self.scope_stack, self.current_level()]

    def all_scopes(self) -> list[Scope]:
        """Return every condition in effect, outermost first."""
        return [level.scope for level in self.all_levels() if level.scope is not None]

    def describe_scope(self) -> str:
        """Return the conditions in effect, e.g. ``"geo = US and size > 1000"``."""
        return " and ".join(str(scope) for scope in self.all_scopes()) or "all"

    def equality_conditions(self) -> dict[str, str]:
        """Return the ``dimension = value`` conditions in effect."""
        return {s.key: s.value for s in self.all_scopes() if s.op == "eq"}

    def set_prompt(self) -> None:
        """Show the scope id and (an abbreviation of) the scope in the prompt."""
        scope = self.describe_scope()
        limit = max(self.settings.get_int("max-prompt", 40), 20)
        if len(scope) >= limit:
            head = limit // 2 - 5
            tail = len(scope) - limit // 2
            scope = f"{scope[:head]} ... {scope[tail:]}"
        self.prompt = f"[{self.scope_id}:{scope}] "

    # ------------------------------------------------------------------ #
    # Hooks implemented by command groups
    # ------------------------------------------------------------------ #

    def recover(self) -> bool:
        """Rebuild the scope stack on the server; returns whether it succeeded."""
        raise NotImplementedError

    def reset_session(self) -> None:
        """Start over from the initial scope."""
        raise NotImplementedError

    def on_settings_changed(self) -> None:
        """Refresh whatever is on screen after a setting changed."""

    # ------------------------------------------------------------------ #
    # Output
    # ------------------------------------------------------------------ #

    def out(self, *parts: object) -> None:
        """Print to the shell's output stream."""
        print(*parts, file=self.stdout)

    def error(self, message: str) -> None:
        """Print an error message."""
        self.out(f"error: {message}")

    def new_report(self) -> Report:
        """Create a table that honours the display settings."""
        return Report(
            abbreviate=bool(self.settings.get("abbreviate-numbers")),
            delimiter=self.settings.get_str("delimiter"),
            table_delimiter=self.settings.get_str("table-delimiter"),
            stream=self.stdout,
        )

    def print_gains_report(self, report: Report, rows: list[dict[str, Any]]) -> None:
        """Print rows comparing accelerated and bypassed traffic.

        Adds each row's share of the total traffic and hides rows whose sample
        sizes are below the ``min-*-samples`` settings, since gains measured on
        a handful of requests are noise.
        """
        report.add_column("%share", "percent_share", 15)
        report.write_header()
        min_total = self.settings.get_int("min-total-samples", 0)
        min_acc = self.settings.get_int("min-acc-samples", 0)
        min_byp = self.settings.get_int("min-byp-samples", 0)

        def counts(row: Mapping[str, Any]) -> tuple[float, float]:
            accelerated = (row.get("acc_ct") or 0) + (row.get("ace_ct") or 0)
            bypassed = (row.get("byp_ct") or 0) + (row.get("bye_ct") or 0)
            return accelerated, bypassed

        grand_total = sum(sum(counts(row)) for row in rows)
        for row in rows:
            accelerated, bypassed = counts(row)
            total = accelerated + bypassed
            row["percent_share"] = total * 100.0 / grand_total if grand_total else 0.0
            if total >= min_total and accelerated >= min_acc and bypassed >= min_byp:
                report.write_row(row)
        self.last_result = ResultTable(rows, list(report.columns))

    # ------------------------------------------------------------------ #
    # Server access
    # ------------------------------------------------------------------ #

    def timeout(self, default: int) -> int:
        """Return the request timeout: the ``timeout`` setting or ``default``."""
        return self.settings.get_int("timeout", default)

    def use_median(self) -> int:
        """Return ``1`` when results should report medians rather than averages."""
        return 1 if self.settings.get("use-median") else 0

    def call(
        self, endpoint: str, params: Mapping[str, Any] | None = None, timeout: int = 30
    ) -> JsonObject | None:
        """Call the server; failures are reported to the user and yield ``None``."""
        return self.client.call(endpoint, params, timeout)

    def healthcheck(self, cid: str | None = None, timeout: int = 10) -> JsonObject | None:
        """Ping the server (selecting customer ``cid``); ``None`` unless it is healthy."""
        status = self.call("/healthcheck", {"cid": cid or self.cid or 0}, timeout)
        return status if status and status.get("status") == "ok" else None

    def ping(self) -> None:
        """Keep the server-side session alive (called from a background thread)."""
        self.healthcheck()

    def reconnect(self) -> bool:
        """Make sure the server is up and still knows our scopes.

        If the server restarted since the session began, its scope ids are
        gone, so the stack is replayed from the stored conditions.

        Returns:
            Whether the command that called this may proceed.
        """
        status = self.healthcheck() or self.healthcheck()
        if status is None:
            self.error("the server is down")
            return False
        started = status.get("started", 0)
        if self.server_started and started != self.server_started:
            self.server_started = started
            self.out(f"the server at {self.client.address} restarted, rebuilding the scope stack")
            if not self.recover():
                self.out("resetting the scope")
                self.reset_session()
                return False
        return True

    # ------------------------------------------------------------------ #
    # Aggregate columns (shared by breakdowns and reports)
    # ------------------------------------------------------------------ #

    def aggregate_params(self, args: str, allow_desc: bool) -> dict[str, ParamValues]:
        """Validate aggregate expressions such as ``median fbu dcu perc95 speed``.

        Raises:
            ValueError: If the expression is invalid.
        """
        self.aggregate_grammar.get_param(DESCENDING).is_active = allow_desc
        params, error = self.aggregate_grammar.validate(args)
        if error:
            raise ValueError(error)
        return params

    def aggregate_columns(self, args: str) -> list[str]:
        """Turn ``median fbu dcu acc_ct`` into ``["median(fbu)", "median(dcu)", "acc_ct"]``.

        Raises:
            ValueError: If the expression is invalid.
        """
        columns: list[str] = []
        for keyword, values in self.aggregate_params(args, allow_desc=True).items():
            if keyword == DESCENDING:
                continue
            arguments = as_list(values)
            if arguments:
                columns.extend(f"{keyword}({value})" for value in arguments)
            else:
                columns.append(keyword)
        return columns

    def complete_aggregates(self, line: str, allow_desc: bool) -> list[str]:
        """Complete an aggregate expression (``line`` includes the command name)."""
        self.aggregate_grammar.get_param(DESCENDING).is_active = allow_desc
        return self.aggregate_grammar.complete(line)

    # ------------------------------------------------------------------ #
    # cmd.Cmd integration
    # ------------------------------------------------------------------ #

    def precmd(self, line: str) -> str:
        """Echo commands when ``echo`` mode is on (handy for scripted sessions)."""
        if self.echo_commands and line.strip():
            self.out(line)
        return line

    def onecmd(self, line: str) -> bool:
        """Run one command, reporting errors instead of ending the session."""
        try:
            return bool(super().onecmd(line))
        except (ValueError, OSError) as exc:  # bad input or I/O: the message says it all
            self.error(str(exc))
        except Exception as exc:
            self.error(f"unexpected {type(exc).__name__}: {exc}")
            if self.options.debug:
                traceback.print_exc(file=self.stdout)
            else:
                self.out("(start with --debug for details)")
        return False

    def emptyline(self) -> bool:
        """On Enter, fetch the next page of a paging command; otherwise do nothing."""
        if self.lastcmd.split(" ", 1)[0] in _PAGING_COMMANDS:
            return self.onecmd(self.lastcmd)
        return False

    def default(self, line: str) -> None:
        """Report unknown commands."""
        self.error(f"unknown command: {line.split(maxsplit=1)[0]} (type help for a list)")

    def do_help(self, arg: str) -> bool | None:
        """List the commands, or describe one: help <command>."""
        method = getattr(self, f"do_{arg}", None) if arg else None
        if method is not None and method.__doc__:
            self.out(inspect.cleandoc(method.__doc__))
            return None
        return super().do_help(arg)
