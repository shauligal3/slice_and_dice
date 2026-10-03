"""Commands that dice the current scope: ``group_by``, ``order_by``, ``cluster`` ..."""

from __future__ import annotations

from typing import Any

from slice_and_dice.constants import CALCULATED_COLUMNS, DATE_DIMENSIONS, NUMERIC_DIMENSIONS
from slice_and_dice.dimension_value import DimensionValue
from slice_and_dice.export import write_csv
from slice_and_dice.formatting import timestamp_slug
from slice_and_dice.grammars import DESCENDING
from slice_and_dice.parsed_command import as_list
from slice_and_dice.partition import Partition, parse_partition
from slice_and_dice.report import Report
from slice_and_dice.result_table import ResultTable
from slice_and_dice.shell_base import ShellBase

#: ``group_by`` flag: count errored requests together with their traffic class.
_CLASS_MERGE = "classmerge"
#: ``group_by`` flag: write every row to a CSV file instead of paging on screen.
_SAVE_OUTPUT = "save_output"
#: Page size used with ``save_output`` (effectively unlimited).
_UNLIMITED = 99_999_999
#: Dimensions for which the error-class columns (#Ace / #Bye) are meaningful.
_ERROR_DIMENSIONS = ("status_code", "class", "exception")


class BreakdownCommands(ShellBase):
    """Comparing accelerated vs. bypassed performance across dimension values."""

    def group_by(self, args: str, order_by: str = "", desc: int = 1) -> None:
        """Run a breakdown and print the next page of it.

        Args:
            args: The partition expression, optionally with flags.
            order_by: Column to sort the rows by.
            desc: ``1`` to sort in descending order.
        """
        if not self.reconnect():
            return
        tokens = args.split()
        class_merge = _CLASS_MERGE in tokens
        save_output = _SAVE_OUTPUT in tokens
        expression = " ".join(t for t in tokens if t not in (_CLASS_MERGE, _SAVE_OUTPUT))
        partition = parse_partition(expression, self.dimensions)

        if args != self.last_group_command:
            self.breakdown_offset = 0
        self.last_group_command = args
        limit = _UNLIMITED if save_output else self.settings.get_int("max-results", 10)
        # Error breakdowns count failures, which have no meaningful medians.
        error_report = any(field in ("exception", "status_code") for field in partition.fields)
        extra = [c for c in self.breakdown_selected if c not in CALCULATED_COLUMNS]
        params = {
            "scope_id": self.scope_id,
            "partition": partition.fields_param(),
            "breakpoints": partition.breakpoints_param(),
            "limit": limit,
            "startfrom": self.breakdown_offset,
            "as_median": 0 if error_report else self.use_median(),
            "columns": ",".join(extra),
            "order_by": order_by,
            "desc": desc,
            "classmerge": int(class_merge),
            "cdf_mode": 0,
        }
        result = self.call("/scope/breakdown", params, self.timeout(60))
        if not result:
            self.error("the breakdown failed")
            self.recover()
            return
        self.sql = result.get("sql", "")
        self.report_kind = "breakdown"
        total = result.get("count", 0)
        first = self.breakdown_offset
        self.breakdown_offset += limit
        rows: list[dict[str, Any]] = result.get("histogram", [])
        if not rows:
            self.breakdown_offset = 0
            self.out("(end of results)")
            return
        self.dimension_values = {}

        if save_output:
            path = f"breakdown_{timestamp_slug()}.csv"
            write_csv(path, rows, delimiter="|")
            self.last_result = ResultTable(rows)
            self.out(f"saved {len(rows)} rows to {path}")
            return

        report = self._breakdown_report(partition, rows, order_by)
        self.print_gains_report(report, rows)

        if len(partition.fields) == 1:
            # Remember each row so the user can step into it by value.
            self.dimension = partition.fields[0]
            for row in rows:
                value = row.get(self.dimension, "")
                row["val"] = value
                self.dimension_values[str(value)] = DimensionValue.from_row(row)
        if total:
            self.out(f"[ {first} - {min(self.breakdown_offset, total)} of {total} rows ]")

    def _breakdown_report(
        self, partition: Partition, rows: list[dict[str, Any]], order_by: str
    ) -> Report:
        """Lay out the columns of a breakdown, hiding the ones without data."""
        report = self.new_report()
        key_width = self.settings.get_int("key-width", 15)
        for field in partition.fields:
            report.add_column(field, field, 25 if field == "ses" else key_width)
        if not partition.fields:
            report.add_column("val", "val", 20)
        report.add_column("%gain", "spd_gain", 8)
        if self.settings.get("gain-as-msec", 0) == 1:
            report.add_column("dfbu", "fbu_diff", 8)
            report.add_column("ddcu", "dcu_diff", 8)
        else:
            report.add_column("%fbu", "fbu_gain", 8)
            report.add_column("%dcu", "dcu_gain", 8)
        for column in self.breakdown_selected:
            report.add_column(column, column, len(column) + 1)
        report.add_column("acc_sz(25/50/75)", "acc_sz", 40)
        report.add_column("byp_sz(25/50/75)", "byp_sz", 40)
        for header, key in (
            ("#Acc", "acc_ct"),
            ("#Byp", "byp_ct"),
            ("#Ace", "ace_ct"),  # accelerated requests that errored
            ("#Bye", "bye_ct"),  # bypassed requests that errored
        ):
            report.add_column(header, key, 15)
        if order_by not in ("acc_ct", "byp_ct") and not report.has_column(order_by):
            report.add_column(order_by, order_by, 15)

        report.filter_empty_columns(rows)
        # When gains cannot be computed (e.g. one class is missing), show plain medians.
        if not report.has_column("%gain"):
            report.add_column("<speed>", "spd", 15)
        if not report.has_column("%fbu") and not report.has_column("dfbu"):
            report.add_column("<fbu>", "med_fbu", 8)
        if not report.has_column("%dcu") and not report.has_column("ddcu"):
            report.add_column("<dcu>", "med_dcu", 8)
        report.filter_empty_columns(rows)

        if not any(field in _ERROR_DIMENSIONS for field in partition.fields):
            if report.has_column("#Acc"):
                report.remove_column("#Ace")
            if report.has_column("#Byp"):
                report.remove_column("#Bye")
        for header in (self.settings.get_str("disabled-columns") or "").split(","):
            if header:
                report.remove_column(header)
        return report

    def do_group_by(self, arg: str) -> None:
        """Break the current scope down by one or more dimensions.

        Usage: group_by <dimension> [[breakpoints] <bp> ...] [<dimension> ...]
                        [classmerge] [save_output]

        Numeric dimensions are bucketed by the breakpoints; other dimensions are
        grouped by value. Each row compares the speed, time to first byte (fbu)
        and download time (dcu) of accelerated vs. bypassed traffic. Press Enter
        for the next page. After grouping by a single dimension, 'in <value>'
        steps into a row.

        classmerge   count errored requests with their traffic class
        save_output  write all rows to a CSV file instead of the screen

        Examples: group_by network
                  group_by size breakpoints 10000 100000 geo
                  group_by date 2024-05-01 2024-05-08
        """
        self.group_by(arg)

    def complete_group_by(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete dimensions, the ``breakpoints`` keyword and flags."""
        words = line[:begidx].split()[1:]
        used = {word for word in words if word in self.dimensions}
        candidates = [d for d in self.dimensions if d not in used]
        if words and words[-1] in (*NUMERIC_DIMENSIONS, *DATE_DIMENSIONS):
            candidates.insert(0, "breakpoints")
        candidates += [flag for flag in (_CLASS_MERGE, _SAVE_OUTPUT) if flag not in words]
        return [c for c in candidates if c.startswith(text)]

    # ------------------------------------------------------------------ #
    # Extra columns and sorting
    # ------------------------------------------------------------------ #

    def add_breakdown_columns(self, args: str) -> list[str]:
        """Add aggregate columns to subsequent breakdowns; returns the columns."""
        columns = self.aggregate_columns(args)
        for column in columns:
            if column not in self.breakdown_selected:
                self.breakdown_selected.append(column)
                self.breakdown_offset = 0
        return columns

    def select_breakdown(self, args: str) -> None:
        """Add aggregate columns (``median fbu``) to breakdowns."""
        if args.strip():
            self.add_breakdown_columns(args)

    def unselect_breakdown(self, args: str) -> None:
        """Remove aggregate columns from breakdowns (all of them without arguments)."""
        if not args.strip():
            self.breakdown_selected = []
            return
        for column in self.aggregate_columns(args):
            if column in self.breakdown_selected:
                self.breakdown_selected.remove(column)
                self.breakdown_offset = 0

    def do_order_by(self, arg: str) -> None:
        """Re-run the last breakdown sorted by a column.

        Usage: order_by <aggregate> <dimension> [desc]
               order_by <calculated column> [desc]
        Examples: order_by median fbu desc
                  order_by acc_ct desc
        """
        if not self.last_group_command:
            raise ValueError("order_by needs a group_by to sort")
        params = self.aggregate_params(arg, allow_desc=True)
        desc = int(DESCENDING in params)
        params.pop(DESCENDING, None)
        if not params:
            raise ValueError("order_by needs a column to sort by")
        keyword, values = next(iter(params.items()))
        if keyword in CALCULATED_COLUMNS:
            column = keyword
            if column != self.breakdown_order_by:
                self.breakdown_offset = 0
                self.breakdown_order_by = column
        else:
            arguments = as_list(values)
            if not arguments:
                raise ValueError(f"{keyword} needs a dimension, e.g. {keyword} fbu")
            self.add_breakdown_columns(f"{keyword} {arguments[0]}")
            column = f"{keyword}({arguments[0]})"
        self.group_by(self.last_group_command, column, desc)

    def complete_order_by(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete aggregate expressions, including ``desc``."""
        return self.complete_aggregates(line[:endidx], allow_desc=True)

    # ------------------------------------------------------------------ #
    # Clustering
    # ------------------------------------------------------------------ #

    def do_cluster(self, arg: str) -> None:
        """Split a numeric dimension into buckets of similar values.

        Usage: cluster <numeric dimension> [<number of buckets>=4]
        Useful for picking breakpoints for group_by.
        """
        tokens = arg.split()
        if not tokens:
            raise ValueError("cluster needs a numeric dimension")
        if not self.reconnect():
            return
        dimension = tokens[0]
        try:
            buckets = int(tokens[1]) if len(tokens) > 1 else 4
        except ValueError:
            raise ValueError(f"the number of buckets must be an integer: {tokens[1]}") from None
        params = {
            "scope_id": self.scope_id,
            "partition": dimension,
            "buckets": buckets,
            "limit": self.settings.get_int("cluster-limit", 10000),
        }
        self.out(f"clustering {dimension} into {buckets} buckets...")
        result = self.call("/scope/cluster", params, self.timeout(60))
        if not result:
            self.error("clustering failed")
            return
        self.sql = result.get("sql", "")
        rows: list[dict[str, Any]] = result.get("clusters", [])
        if not rows:
            self.out("no clusters")
            return
        report = self.new_report()
        for header in ("limit", "spread", "count", "percentage share"):
            report.add_column(header, header, 25)
        report.filter_empty_columns(rows)
        report.render(rows)
        self.last_result = ResultTable(rows, list(report.columns))

    def complete_cluster(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete numeric dimensions."""
        if len(line[:begidx].split()) > 1:
            return []
        return [d for d in NUMERIC_DIMENSIONS if d.startswith(text)]
