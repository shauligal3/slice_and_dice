"""Commands that look at individual log records: ``samples``, ``timelines``, ``session``."""

from __future__ import annotations

from typing import Any

from slice_and_dice.constants import ALL_DIMENSIONS
from slice_and_dice.formatting import format_cell, to_json
from slice_and_dice.report import Column
from slice_and_dice.result_table import ResultTable
from slice_and_dice.shell_base import ShellBase
from slice_and_dice.timeline import render_timeline

_ORDER_BY = "order-by"
_DESCENDING = "desc"
#: Widest a samples column may get, in characters.
_MAX_CELL_WIDTH = 50
#: Columns never shortened to ``1.2K`` style, since they are identifiers.
_ID_COLUMNS = ("ses",)


class SampleCommands(ShellBase):
    """Paging through raw log records of the current scope."""

    def fetch_samples(self, args: str) -> bool:
        """Fetch the next page of samples.

        Args:
            args: ``[order-by <dimension> [desc]]``.

        Returns:
            Whether any samples were fetched.
        """
        tokens = args.split()
        order_by: str | None = None
        descending = False
        if tokens:
            if tokens[0] != _ORDER_BY or len(tokens) < 2 or tokens[1] not in self.dimensions:
                raise ValueError("usage: samples [order-by <dimension> [desc]]")
            order_by = tokens[1]
            descending = len(tokens) > 2 and tokens[2] == _DESCENDING
        if args != self.last_samples_command:
            self.samples_offset = 0
            self.last_samples_command = args
        self.samples_order_by = order_by

        limit = self.settings.get_int("max-results", 10)
        params: dict[str, Any] = {
            "scope_id": self.scope_id,
            "startfrom": self.samples_offset,
            "limit": limit,
        }
        if order_by:
            params["order_by"] = order_by
            if descending:
                params["desc"] = 1
        result = self.call("/scope/samples", params, self.timeout(30))
        if not result:
            self.recover()
            return False
        self.samples = result.get("samples", [])
        self.sql = result.get("sql", "")
        # A full page means there may be more; otherwise start over next time.
        self.samples_offset = self.samples_offset + limit if len(self.samples) == limit else 0
        return bool(self.samples)

    def visible_columns(self, columns: list[str]) -> list[str]:
        """Drop columns pinned to a single value by the scope (e.g. ``geo = US``)."""
        pinned = {
            level.scope.key
            for level in self.all_levels()
            if level.scope
            and level.scope.key != "datetime"
            and level.scope.op not in ("gt", "lt", "not-null")
        }
        return [column for column in columns if column not in pinned]

    def show_samples(self) -> None:
        """Print the fetched samples, fitting as many columns as the line allows."""
        if not self.samples:
            self.out("no samples found")
            return
        view = self.visible_columns(self.dimensions)
        widths: dict[str, int] = {}
        for sample in self.samples:
            for column in view:
                value = str(sample.get(column, ""))
                if value:
                    width = max(min(len(value) + 1, _MAX_CELL_WIDTH), len(column) + 1)
                    widths[column] = max(widths.get(column, 0), width)

        shown: list[str] = []
        if self.samples_order_by in widths:
            shown.append(self.samples_order_by)
        line_width = self.settings.get_int("max-report-line", 80)
        used = sum(widths[column] for column in shown)
        for column in view:
            if column in widths and column not in shown:
                if used + widths[column] > line_width:
                    break
                shown.append(column)
                used += widths[column]

        self.report_kind = "samples"
        self.out("".join(format_cell(column, widths[column]) for column in shown))
        abbreviate = bool(self.settings.get("abbreviate-numbers"))
        for sample in self.samples:
            self.out(
                "".join(
                    format_cell(
                        sample.get(column, ""),
                        widths[column],
                        abbreviate and column not in _ID_COLUMNS,
                    )
                    for column in shown
                )
            )
        self.last_result = ResultTable(
            self.samples, [Column(column, column, widths[column]) for column in shown]
        )

    def on_settings_changed(self) -> None:
        """Redraw samples with the new display settings."""
        super().on_settings_changed()
        if self.report_kind == "samples" and self.samples:
            self.show_samples()

    def do_samples(self, arg: str) -> None:
        """Show raw log records of the current scope; press Enter for more.

        Usage: samples [order-by <dimension> [desc]]
        Columns fixed by the scope are hidden; 'select <dimension>' moves a
        column to the front and 'unselect' restores the default order.
        """
        if self.reconnect() and self.fetch_samples(arg):
            self.show_samples()

    def complete_samples(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete ``order-by <dimension> desc``."""
        words = line[:begidx].split()[1:]
        if not words:
            candidates = [_ORDER_BY]
        elif len(words) == 1 and words[0] == _ORDER_BY:
            candidates = list(self.dimensions)
        elif len(words) == 2:
            candidates = [_DESCENDING]
        else:
            candidates = []
        return [c for c in candidates if c.startswith(text)]

    def do_timelines(self, arg: str) -> None:
        """Draw the timeline of each sampled request, to see where time was spent.

        Usage: timelines [order-by <dimension> [desc]]
        Events: co = connected, fb = first byte, dc = download complete;
        suffix u = user device, h = acceleration proxy, o = origin server.
        """
        if not self.reconnect() or not self.fetch_samples(arg):
            return
        self.report_kind = "timelines"
        self.out(f"{format_cell('speed', 10)}{format_cell('size', 10)}timeline")
        for sample in self.samples:
            speed = format_cell(sample.get("speed", 0), 10)
            size = format_cell(sample.get("size", 0), 10)
            self.out(f"{speed}{size}{render_timeline(sample)}")

    def complete_timelines(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete like ``samples``."""
        return self.complete_samples(text, line, begidx, endidx)

    def select_samples(self, args: str) -> None:
        """Move columns to the front of the samples view."""
        found = False
        for column in args.split():
            if column in self.dimensions:
                self.dimensions.remove(column)
                self.dimensions.insert(0, column)
                found = True
            else:
                self.error(f"unknown column: {column}")
        if found:
            self.show_samples()

    def unselect_samples(self, args: str) -> None:
        """Move columns to the back of the samples view (reset the order without args)."""
        columns = args.split()
        if not columns:
            self.dimensions = list(ALL_DIMENSIONS)
        for column in columns:
            if column in self.dimensions:
                self.dimensions.remove(column)
                self.dimensions.append(column)
        self.show_samples()

    def do_session(self, arg: str) -> None:
        """Dump the raw events of a user session as JSON.

        Usage: session <session id> [<event name>]
        """
        parts = arg.split()
        if not parts or len(parts) > 2 or not parts[0].isdigit():
            raise ValueError("usage: session <session id> [<event name>]")
        event = parts[1] if len(parts) > 1 else ""
        result = self.call("/mongo/session", {"ses": int(parts[0]), "evt": event})
        if result is not None:
            self.out(to_json(result, indent=4))
