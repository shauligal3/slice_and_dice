"""Commands that run statistical reports on the server and save their results."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from slice_and_dice.export import write_csv
from slice_and_dice.formatting import pretty_print_records, timestamp_slug, to_json
from slice_and_dice.grammars import report_grammar
from slice_and_dice.partition import parse_partition
from slice_and_dice.policy_script import render_policy_scripts
from slice_and_dice.report import Column
from slice_and_dice.report_spec import ReportSpec
from slice_and_dice.result_table import ResultTable
from slice_and_dice.shell_base import ShellBase

#: Where best-policy results are written.
POLICY_DIR = Path("policy_files")
#: Where training sets are written.
DATASET_DIR = Path("datasets")

#: Cohorts with fewer requests than this are not trusted to rank policies.
_MIN_SAMPLE_SIZE = 500
#: A policy must beat the control group by this many percent to be recommended.
_GAIN_THRESHOLD = 5
#: Recommend at most this many policies per cohort.
_MAX_POLICIES = 5
#: Policies tested on fewer than this share of the cohorts are listed separately.
_POLICY_SCOPE_THRESHOLD = 0.1
#: Fields that a generated policy rule may match on, unless ``policy-from`` says otherwise.
_DEFAULT_POLICY_FROM = "cid,geo,network"


class ReportCommands(ShellBase):
    """Projection and best-policy reports, training sets and CSV export."""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def fetch_reports(self, name: str) -> list[dict[str, Any]]:
        """Return the saved reports whose names contain ``name``."""
        result = self.call("/scope/show_reports", {"report_name": name}, self.timeout(60))
        if result is None:
            raise ConnectionError("could not fetch the saved reports from the server")
        reports: list[dict[str, Any]] = result.get("reports", [])
        return reports

    def spec_from_document(self, document: dict[str, Any]) -> ReportSpec:
        """Build a :class:`ReportSpec`, resolving outcome expressions."""

        def outcome_columns(expression: str) -> list[str] | None:
            try:
                return self.aggregate_columns(expression)
            except ValueError:
                return None

        return ReportSpec.from_document(document, outcome_columns, self.dimensions)

    def spec_from_command(self, args: str) -> ReportSpec:
        """Build an ad-hoc :class:`ReportSpec` from ``build_report`` arguments.

        Raises:
            ValueError: If the arguments are invalid.
        """
        params, error = report_grammar().validate(args)
        if error:
            raise ValueError(error)
        return self.spec_from_document(ReportSpec.document_from_command(params))

    def complete_report_command(self, line: str) -> list[str]:
        """Complete ``build_report`` / ``projection_report`` arguments."""
        return report_grammar().complete(line)

    # ------------------------------------------------------------------ #
    # Saved reports
    # ------------------------------------------------------------------ #

    def do_show_reports(self, arg: str) -> None:
        """List the reports saved on the server: show_reports [<name filter>]."""
        if self.reconnect():
            pretty_print_records(self.fetch_reports(arg.strip()), stream=self.stdout)

    def run_projection(self, spec: ReportSpec) -> None:
        """Run a projection report: outcomes per cohort and policy, with gains."""
        self.out("Report:", spec.name)
        params = {"scope_id": self.scope_id, **spec.projection_params(), "as_median": 1}
        result = self.call("/scope/gen_report", params, self.timeout(120))
        if not result:
            self.error("the server failed to generate the report")
            return
        rows: list[dict[str, Any]] = result.get("report", [])
        if not rows:
            self.out("the report is empty")
            return

        report = self.new_report()
        for name, _ in spec.control + spec.policy:
            report.add_column(name, name, 20)
        for outcome in spec.outcomes:
            report.add_column(outcome, outcome, 20)
        for header, key in (
            ("%gain", "spd_gain"),
            ("%fbu", "fbu_gain"),
            ("%dcu", "dcu_gain"),
            ("#Acc", "acc_ct"),
            ("#Byp", "byp_ct"),
        ):
            report.add_column(header, key, 10)
        report.filter_empty_columns(rows)
        self.print_gains_report(report, rows)
        self.report_kind = "report"
        path = f"{spec.name}_{timestamp_slug()}.csv"
        write_csv(path, rows)
        self.out(f"{len(rows)} rows returned from the server, saved to {path}")

    def do_run_report(self, arg: str) -> None:
        """Run the saved projection reports whose names contain the argument.

        Usage: run_report <name filter>
        """
        if not arg.strip():
            raise ValueError("usage: run_report <name filter>")
        if not self.reconnect():
            return
        for document in self.fetch_reports(arg.strip()):
            self.run_projection(self.spec_from_document(document))

    def do_projection_report(self, arg: str) -> None:
        """Run an ad-hoc projection report.

        Usage: projection_report control <dims> policy <dims> [latent <dims>]
                                 [outcome <dims>] [bp_<dim> <breakpoints> ...]
        Example: projection_report control network policy max_burst outcome fbu
                                   bp_max_burst 3000 6000
        """
        if self.reconnect():
            self.run_projection(self.spec_from_command(arg))

    def complete_projection_report(
        self, text: str, line: str, begidx: int, endidx: int
    ) -> list[str]:
        """Complete report keywords and dimensions."""
        return self.complete_report_command(line[:endidx])

    # ------------------------------------------------------------------ #
    # Best policies
    # ------------------------------------------------------------------ #

    def find_best_policies(self, spec: ReportSpec) -> None:
        """Find the best policy per cohort and write the results to ``policy_files/``.

        Writes a human-readable summary (``.txt``), the raw results
        (``.json``), the per-cohort table (``.csv``) and a policy-editor script
        that A/B-tests the recommendations (``_pscript.txt``).
        """
        self.out("Report:", spec.name)
        params = {
            "scope_id": self.scope_id,
            **spec.best_policy_params(),
            "as_median": 1,
            "min_sample_size": _MIN_SAMPLE_SIZE,
            "gain_threshold": _GAIN_THRESHOLD,
            "max_policies": _MAX_POLICIES,
            "policy_scope_percentage_threshold": _POLICY_SCOPE_THRESHOLD,
        }
        result = self.call("/scope/best_policy", params, self.timeout(120))
        if not result:
            self.error("the server failed to find the best policies")
            return

        sections = {
            "best-policies": "Best Policies:",
            "recommended-policies": "Recommended Policies:",
            "no-gain-scopes": "Scopes where no policy worked:",
            "not-tested-policies": (
                "Policies with statistically significant data for less than "
                f"{_POLICY_SCOPE_THRESHOLD * 100:g}% of scopes:"
            ),
        }
        POLICY_DIR.mkdir(exist_ok=True)
        base = POLICY_DIR / f"{spec.name}_{timestamp_slug()}"
        summary_path = Path(f"{base}.txt")
        with summary_path.open("a", encoding="utf-8") as summary:
            pretty_print_records([], f"Scope: {self.describe_scope()}", self.stdout, summary)
            for key, title in sections.items():
                pretty_print_records(result.get(key, []), title, self.stdout, summary)

        json_path = Path(f"{base}.json")
        json_path.write_text(
            to_json([{"name": key, "data": result.get(key, [])} for key in sections]),
            encoding="utf-8",
        )

        match_fields = (self.settings.get_str("policy-from") or _DEFAULT_POLICY_FROM).split(",")
        scripts = render_policy_scripts(
            result.get("recommended-policies", []), self.equality_conditions(), match_fields
        )
        script_path = Path(f"{base}_pscript.txt")
        script_path.write_text("".join(scripts), encoding="utf-8")

        rows: list[dict[str, Any]] = result.get("report", [])
        report = self.new_report()
        for name, _ in spec.control_no_agg + spec.policy + spec.control_agg:
            report.add_column(name, name, 20)
        for outcome in spec.outcomes:
            report.add_column(outcome, outcome, 20)
        for header, key in (
            ("perc75(retxpercent)", "retxpercent"),
            ("perc75(rtocount)", "rto_count"),
            ("%gain", "spd_gain"),
            ("%fbu", "fbu_gain"),
            ("%dcu", "dcu_gain"),
            ("score", "obj_function"),
            ("#Acc", "acc_ct"),
            ("#Byp", "byp_ct"),
        ):
            report.add_column(header, key, 10)
        self.last_result = ResultTable(rows, list(report.columns))
        self.report_kind = "breakdown"
        csv_path = Path(f"{base}.csv")
        if rows:
            self.export_rows(csv_path, rows, report.columns)

        self.out(f"Summary saved to {summary_path}")
        self.out(f"Detailed report saved to {csv_path}")
        self.out(f"JSON results saved to {json_path}")
        self.out(f"Policy editor script saved to {script_path}")
        self.out()
        self.out("Total query time:", result.get("db_time", 0))
        self.out("Total time:", result.get("total_time", 0))

    def do_find_best_policy(self, arg: str) -> None:
        """Run a saved best-policy report: find_best_policy <name filter>.

        For each cohort of the control fields, finds the policy values with the
        largest gains over the control group; see 'build_report' for details.
        """
        if not arg.strip():
            raise ValueError("usage: find_best_policy <name filter>")
        if not self.reconnect():
            return
        reports = self.fetch_reports(arg.strip())
        if not reports:
            raise ValueError(f"no saved report matches {arg.strip()!r}")
        self.find_best_policies(self.spec_from_document(reports[0]))

    def do_build_report(self, arg: str) -> None:
        """Find the best policies with an ad-hoc report.

        Usage: build_report control <dims> policy <dims> [latent <dims>]
                            [outcome <dims>] [bp_<dim> <breakpoints> ...]
        control  dimensions defining comparable cohorts (shown in the output)
        latent   confounders that are controlled for but aggregated over
        policy   the knobs whose values are compared
        outcome  metrics to compare (medians)
        Example: build_report control network geo policy max_burst outcome fbu dcu
        """
        if self.reconnect():
            self.find_best_policies(self.spec_from_command(arg))

    def complete_build_report(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete report keywords and dimensions."""
        return self.complete_report_command(line[:endidx])

    def do_recommended_policies(self, arg: str) -> None:
        """Ask the server for recommended policies in the current scope.

        Usage: recommended_policies [<saved report name filter>]
        With a report, its non-aggregated control fields define the cohorts.
        """
        if not self.reconnect():
            return
        params: dict[str, Any] = {
            "scope_id": self.scope_id,
            "as_median": 1,
            "min_sample_size": _MIN_SAMPLE_SIZE,
        }
        if arg.strip():
            reports = self.fetch_reports(arg.strip())
            if not reports:
                raise ValueError(f"no saved report matches {arg.strip()!r}")
            spec = self.spec_from_document(reports[0])
            self.out("Report:", spec.name)
            best = spec.best_policy_params()
            params["control_fields_no_agg"] = best["control_fields_no_agg"]
            params["breakpoints_no_agg"] = best["breakpoints_no_agg"]
        result = self.call("/scope/recommended_policy", params, self.timeout(120))
        if result is not None:
            self.out(to_json(result, indent=2))

    def do_best_strategy(self, arg: str) -> None:
        """Experimental: find the best max_burst per response-size bucket."""
        params = {
            "scope_id": self.scope_id,
            "control_fields": "size",
            "control_breakpoints": "10000,20000,50000,200000",
            "policy_fields": "max_burst",
        }
        result = self.call("/scope/best_strategy", params, 120)
        if result is not None:
            self.out(to_json(result, indent=2))

    def do_visualize_performance(self, arg: str) -> None:
        """Have the server plot the performance of the current scope to a file."""
        if not self.reconnect():
            return
        params = {"scope_id": self.scope_id, "as_median": 1}
        result = self.call("/scope/vis_perf", params, self.timeout(120))
        if result is not None:
            self.out("File saved on the server:", result.get("file_name", ""))

    # ------------------------------------------------------------------ #
    # Training sets
    # ------------------------------------------------------------------ #

    def do_training_set(self, arg: str) -> None:
        """Export per-cohort gains as a training set for policy models.

        Usage: training_set [<partition>] [filename <prefix>]
        The partition is written like group_by's. Without one, a preview of the
        daily data is printed instead. Files go to datasets/<prefix>.csv and
        datasets/<prefix>.scope.txt.
        """
        if not self.reconnect():
            return
        tokens = arg.split()
        prefix = timestamp_slug()
        if "filename" in tokens:
            index = tokens.index("filename")
            if index + 1 >= len(tokens):
                raise ValueError("filename needs a value")
            prefix = tokens[index + 1]
            del tokens[index : index + 2]
        expression = " ".join(tokens)
        partition = parse_partition(expression, self.dimensions)

        params = {
            "scope_id": self.scope_id,
            "control_fields": partition.fields_param(),
            "breakpoints_control": partition.breakpoints_param(),
            "as_median": 1,
        }
        result = self.call("/scope/training_set", params, self.timeout(60))
        if not result:
            self.error("the server failed to build the training set")
            return
        rows: list[dict[str, Any]] = result.get("data", [])
        if not rows:
            self.out("no rows")
            return

        if not partition.fields:
            report = self.new_report()
            for header, key, width in (
                ("day", "day", 12),
                ("max_burst", "max_burst", 10),
                ("fbu_gain", "fbu_gain", 10),
                ("dcu_gain", "dcu_gain", 10),
                ("%retx", "retxpercent", 10),
                ("perc75 size", "perc75(size)", 12),
                ("acc_ct", "acc_ct", 10),
                ("byp_ct", "byp_ct", 10),
            ):
                report.add_column(header, key, width)
            report.render(rows)
            return

        DATASET_DIR.mkdir(exist_ok=True)
        base = DATASET_DIR / prefix
        scope_path = Path(f"{base}.scope.txt")
        scope_path.write_text(
            to_json({"scope": self.describe_scope(), "cmd": expression}), encoding="utf-8"
        )
        csv_path = Path(f"{base}.csv")
        write_csv(csv_path, rows, delimiter="|")
        self.out(f"Training set written to {csv_path}")
        self.out(f"Scope saved at {scope_path}")
        bad, total = result.get("bad_rows", -1), result.get("total_row_count", -1)
        self.out(f"{bad} out of {total} rows to be discarded")

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_rows(
        self, path: Path, rows: list[dict[str, Any]], columns: Sequence[Column]
    ) -> None:
        """Write rows as CSV, prefixed by the scope, using the export settings."""
        write_csv(
            path,
            rows,
            columns=columns,
            delimiter=self.settings.get_str("table-delimiter", "|") or "|",
            delimiter_replacement=self.settings.get_str("table-delimiter-replace", "-"),
            preamble=f"Scope:{self.describe_scope()}",
        )

    def do_save_output(self, arg: str) -> None:
        """Save the last table shown to a CSV file: save_output [<file name>].

        The delimiter is the 'table-delimiter' setting ('|' by default).
        """
        if self.last_result is None or not self.last_result.rows:
            raise ValueError("there is no result to save")
        name = arg.strip() or f"{self.report_kind or 'result'}_{timestamp_slug()}"
        path = Path(f"{name}.csv")
        self.export_rows(path, self.last_result.rows, self.last_result.columns)
        self.out(f"csv written to {path}")
