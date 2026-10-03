"""The interactive shell: every command group combined into one ``cmd.Cmd``."""

from __future__ import annotations

from slice_and_dice import __version__
from slice_and_dice.breakdown_commands import BreakdownCommands
from slice_and_dice.constants import SHOW_TOPICS
from slice_and_dice.formatting import to_json
from slice_and_dice.report_commands import ReportCommands
from slice_and_dice.sample_commands import SampleCommands
from slice_and_dice.scope_commands import ScopeCommands
from slice_and_dice.settings_commands import SettingsCommands


class Shell(ScopeCommands, BreakdownCommands, SampleCommands, ReportCommands, SettingsCommands):
    """The ``slice_and_dice`` read-eval-print loop.

    A typical session narrows the data, compares traffic classes and drills
    into the most interesting rows::

        [12:datetime > 2024-05-01] in geo = US
        [15:datetime > 2024-05-01 and geo = US] group_by network
        [15:...] in LTE
        [21:...] samples order-by speed desc

    Commands that page (``group_by``, ``samples`` ...) fetch the next page
    when Enter is pressed on an empty line.
    """

    intro = f"slice_and_dice {__version__}. Type 'help' or '?' to list commands."

    def start(self) -> None:
        """Connect to the server and enter the initial scope.

        Raises:
            ConnectionError: If the server is unreachable or refuses the password.
        """
        self.reset_session()

    # ------------------------------------------------------------------ #
    # Commands whose meaning depends on the last result
    # ------------------------------------------------------------------ #

    def do_select(self, arg: str) -> None:
        """Add columns to the current view.

        After 'samples': select <dimension> ...   (move columns to the front)
        Otherwise:       select <aggregate> <dimension> ... | <calculated column>
                         e.g. select median fbu dcu perc95 speed
        """
        if self.report_kind == "samples":
            self.select_samples(arg)
        else:
            self.select_breakdown(arg)

    def complete_select(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete dimensions (samples) or aggregate expressions (breakdowns)."""
        if self.report_kind == "samples":
            return [d for d in self.dimensions if d.startswith(text)]
        return self.complete_aggregates(line[:endidx], allow_desc=False)

    def do_unselect(self, arg: str) -> None:
        """Remove columns from the current view (all extra columns without arguments)."""
        if self.report_kind == "samples":
            self.unselect_samples(arg)
        else:
            self.unselect_breakdown(arg)

    def complete_unselect(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete like ``select``."""
        if self.report_kind != "samples":
            return [c for c in self.breakdown_selected if c.startswith(text)]
        return self.complete_select(text, line, begidx, endidx)

    # ------------------------------------------------------------------ #
    # Introspection and housekeeping
    # ------------------------------------------------------------------ #

    def do_show(self, arg: str) -> None:
        """Show internal state.

        Usage: show stack | scope | sql | settings | rest | selected | iter | server
        stack     every level of the scope stack with its scope id and count
        scope     the conditions in effect
        sql       the last SQL query the server ran
        rest      the last API request sent to the server
        selected  extra columns added to breakdowns with 'select'
        iter      paging offsets of samples and breakdowns
        server    information about the server
        """
        topic = arg.strip()
        if topic == "scope":
            self.out(self.describe_scope())
        elif topic == "stack":
            for level in self.all_levels():
                self.out(level.describe())
        elif topic == "sql":
            self.out(self.sql)
        elif topic == "settings":
            self.out(to_json(self.settings.public_view(), indent=2))
        elif topic == "rest":
            self.out(self.client.last_request)
        elif topic == "selected":
            self.out(", ".join(self.breakdown_selected) or "(none)")
        elif topic == "iter":
            self.out(f"samples {self.samples_offset} breakdown {self.breakdown_offset}")
        elif topic == "server":
            result = self.call("/server/info", timeout=10)
            if result is not None:
                self.out(to_json(result, indent=2))
        else:
            raise ValueError(f"show what? one of: {', '.join(SHOW_TOPICS)}")

    def complete_show(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete the topics of ``show``."""
        return [topic for topic in SHOW_TOPICS if topic.startswith(text)]

    def do_policyd(self, arg: str) -> None:
        """Send a command to the policy daemon and print its answer."""
        result = self.call("/policyd/command", {"cmd": arg})
        if result is not None:
            self.out(result.get("result"))

    def do_print(self, arg: str) -> None:
        """Print the argument (useful to annotate scripted sessions)."""
        self.out(arg)

    def do_echo(self, arg: str) -> None:
        """Toggle echoing each command before running it (for scripted sessions)."""
        self.echo_commands = not self.echo_commands
        self.out(f"echo {'on' if self.echo_commands else 'off'}")

    def do_exit(self, arg: str) -> bool:
        """Leave the shell."""
        return True

    def do_EOF(self, arg: str) -> bool:
        """Leave the shell (Ctrl-D)."""
        self.out()
        return True
