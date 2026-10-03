"""Commands that move around the scope stack: ``in``, ``out``, ``reset`` ..."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from typing import Any

from slice_and_dice.constants import (
    INITIAL_SCOPE_HOURS,
    OPERATOR_SYMBOLS,
    OPERATORS,
    TEST_MODE_CID,
    TRAFFIC_CLASSES,
    UNARY_OPERATORS,
)
from slice_and_dice.dimension_value import DimensionValue
from slice_and_dice.formatting import format_cell
from slice_and_dice.result_table import ResultTable
from slice_and_dice.scope import Scope
from slice_and_dice.shell_base import ShellBase

_CONJUNCTION = " and "


class ScopeCommands(ShellBase):
    """Narrowing the data set into scopes and moving between them."""

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #

    def reset_session(self) -> None:
        """Start over: tell the server which data set to use and rebuild the root scope.

        Raises:
            ConnectionError: If the server cannot be reached or rejects the password.
        """
        self.call("/scope/set_unittestmode", {"unittestmode": int(self.options.test_mode)}, 180)
        self.reset_state()
        if not self.options.empty_stack:
            self.enter_initial_scope()
        self.set_prompt()

    def enter_initial_scope(self) -> None:
        """Log in and start from the last day of data (or the test customer).

        Raises:
            ConnectionError: If the server cannot be reached or rejects the password.
        """
        self.out(f"Connecting {self.client.address}")
        status = self.call("/healthcheck", {"cid": self.cid or 0}, timeout=1000)
        if not status or status.get("status") != "ok":
            if status and not self.password_verified and self.settings.password:
                # The server answered but refused us: the saved password is stale.
                self.settings.password = None
                self.settings.save()
            raise ConnectionError(
                "failed to connect to the server: either an incorrect password, "
                "an out-of-sync clock or a server issue"
            )
        if self.options.remember_password and self.settings.password != self.client.password:
            self.settings.password = self.client.password
            self.settings.save()
        self.password_verified = True
        self.server_started = status.get("started", 0)

        if self.options.test_mode:
            self.step_in(Scope("cid", "eq", TEST_MODE_CID))
        else:
            start = datetime.now() - timedelta(hours=INITIAL_SCOPE_HOURS)
            self.step_in(Scope("datetime", "gt", start.date().isoformat()))

    def recover(self) -> bool:
        """Replay every condition of the stack on a (restarted) server."""
        if self.in_recovery:
            self.out("already recovering...")
            return False
        self.in_recovery = True
        try:
            # Server-side ids are stale, so every condition is evaluated again.
            scopes = [
                dataclasses.replace(scope, scope_id=0, dimension_value=None)
                for scope in self.all_scopes()
            ]
            self.reset_state()
            self.in_recovery = True
            for scope in scopes:
                self.out(f"recalc {scope} ...")
                if not self.step_in(scope):
                    return False
            return True
        finally:
            self.in_recovery = False

    # ------------------------------------------------------------------ #
    # Stepping in
    # ------------------------------------------------------------------ #

    def parse_scope(self, text: str) -> Scope:
        """Parse a condition typed by the user.

        Besides ``<dimension> [<op>] <value>``, the user may type a value of
        the dimension last grouped by (``LTE`` after ``group_by network``) or
        ``acc`` / ``byp`` after ``activity``; those reuse server-side ids.

        Raises:
            ValueError: If the condition is malformed.
        """
        text = text.strip()
        picked = self.dimension_values.get(text)
        if picked is not None:
            self.acc_ct, self.byp_ct = picked.acc_ct, picked.byp_ct
            if picked.scope_id:
                return Scope(
                    self.dimension or "",
                    "eq",
                    text,
                    scope_id=picked.scope_id,
                    dimension_value=picked,
                    count=picked.total_ct,
                )
        if text in TRAFFIC_CLASSES:
            is_acc = text == "acc"
            return Scope(
                "class",
                "eq",
                text,
                scope_id=self.acc_scope_id if is_acc else self.byp_scope_id,
                count=int(self.acc_ct if is_acc else self.byp_ct),
            )

        tokens = text.split()
        if len(tokens) < 2:
            raise ValueError(f"incomplete condition: {text!r}")
        key, op = tokens[0], tokens[1]
        if key not in self.dimensions:
            raise ValueError(f"illegal dimension: {key}")
        if op in UNARY_OPERATORS and len(tokens) == 2:
            return Scope(key, op, "")
        op = OPERATOR_SYMBOLS.get(op, op)
        if op in OPERATORS:
            if len(tokens) < 3:
                raise ValueError(f"missing a value: {text!r}")
            return Scope(key, op, " ".join(tokens[2:]))
        return Scope(key, "eq", " ".join(tokens[1:]))

    def step_in(self, scope: Scope) -> bool:
        """Narrow the current subset by ``scope`` and push the previous position.

        Returns:
            Whether the server accepted the condition.
        """
        level = self.current_level()
        if scope.is_mapped:
            self.scope_id = scope.scope_id
            self.count = scope.count
        else:
            if scope.key == "cid":
                self.healthcheck(scope.value)
                self.cid = scope.value
            params = {
                "scope_id": self.scope_id,
                "column": scope.key,
                "op": scope.op,
                "value": scope.value,
            }
            result = self.call("/scope/narrow", params, self.timeout(30))
            if not result:
                self.error(f"the server could not evaluate: {scope}")
                return False
            self.count = result.get("count", 0)
            self.scope_id = result.get("scope_id", 0)
            self.sql = result.get("sql", "")
        self.out(f"[:{self.scope_id} {scope}] Logs: {format_cell(self.count, 10)}")
        self.scope = scope
        self.scope_stack.append(level)
        self._entered(scope)
        return True

    def _entered(self, scope: Scope | None) -> None:
        """Reset per-scope state after entering a new scope."""
        self.clear_results()
        self.set_prompt()
        if self.settings.get("auto-fetch") and (scope is None or scope.key != "class"):
            self.show_activity(scope.dimension_value if scope else None)

    def do_in(self, arg: str) -> None:
        """Narrow the current scope by one or more conditions.

        Usage: in <dimension> [<op>] <value> [and <dimension> <op> <value> ...]
               in <value>      (a value of the dimension last grouped by)
               in acc | byp    (accelerated or bypassed traffic, after 'activity')

        Operators: = != > < >= <= ~ (like), or gt lt eq not like not-like gte lte;
        'is-null' and 'not-null' take no value. The operator defaults to '='.
        Examples: in geo = US and network LTE
                  in size > 100000
        """
        if not self.reconnect():
            return
        for part in arg.split(_CONJUNCTION):
            if part.strip() and not self.step_in(self.parse_scope(part)):
                return

    def complete_in(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete dimensions, breakdown values and operators."""
        words = line[:begidx].split()[1:]
        while "and" in words:
            words = words[words.index("and") + 1 :]
        if not words:
            candidates = [*self.dimensions, *self.dimension_values]
            class_ids = zip(TRAFFIC_CLASSES, self._class_ids(), strict=True)
            candidates += [name for name, scope_id in class_ids if scope_id]
        elif len(words) == 1 and words[0] in self.dimensions:
            candidates = list(OPERATORS)
        else:
            candidates = ["and"] if len(words) >= 2 else []
        return [c for c in candidates if c.startswith(text)]

    def _class_ids(self) -> tuple[int, int]:
        return self.acc_scope_id, self.byp_scope_id

    def do_jump_in(self, arg: str) -> None:
        """Like 'in', but let the server evaluate all the conditions in one query.

        Faster than 'in' for several conditions; the intermediate levels have no
        counts of their own.
        Usage: jump_in <dimension> <op> <value> [and ...]
        """
        if not self.reconnect():
            return
        scopes = [self.parse_scope(part) for part in arg.split(_CONJUNCTION) if part.strip()]
        if not scopes:
            raise ValueError("jump_in needs at least one condition")
        origin = self.current_level()
        saved_stack = list(self.scope_stack)
        for scope in scopes:
            level = self.current_level()
            if scope.key == "cid":
                self.healthcheck(scope.value)
                self.cid = scope.value
            self.count = 0
            self.scope_id = 0
            self.scope = scope
            self.scope_stack.append(level)

        params = {"scope_id": origin.scope_id, "query": arg}
        result = self.call("/scope/jump", params, self.timeout(30))
        if not result:
            self.scope_stack = saved_stack
            self.restore_level(origin)
            self.error(f"the server could not evaluate: {arg}")
            return
        self.count = result.get("count", 0)
        self.scope_id = result.get("scope_id", 0)
        self.sql = result.get("sql", "")
        self.out(f"[:{self.scope_id} {self.scope}] Logs: {format_cell(self.count, 10)}")
        self._entered(self.scope)

    # ------------------------------------------------------------------ #
    # Stepping out
    # ------------------------------------------------------------------ #

    def _pop_level(self) -> bool:
        if not self.scope_stack:
            self.out("top of stack")
            return False
        self.restore_level(self.scope_stack.pop())
        return True

    def _recalculate(self, scope: Scope) -> int | None:
        """Re-apply ``scope`` on top of the current subset; returns the new scope id."""
        params = {
            "scope_id": self.scope_id,
            "column": scope.key,
            "op": scope.op,
            "value": scope.value,
        }
        result = self.call("/scope/narrow", params, self.timeout(30))
        self.out(f"recalc {scope} ... {result.get('count', 0) if result else 'ERR'}")
        if not result:
            return None
        self.count = result.get("count", 0)
        self.scope_id = result.get("scope_id", 0)
        return self.scope_id

    def _remove_condition(self, key: str) -> bool:
        """Drop the outermost condition on ``key`` and re-apply the ones inside it."""
        position = next(
            (i for i, lvl in enumerate(self.scope_stack) if lvl.scope and lvl.scope.key == key),
            None,
        )
        if position is None:
            self.error(f"could not find a former level like {key}")
            return False
        parent_id = self.scope_stack[position - 1].scope_id if position else 0
        if not parent_id and position > 1:
            self.out("missing inner scopes, resetting")
            self.reset_session()
            return False

        del self.scope_stack[position]
        self.scope_id = parent_id
        for level in self.scope_stack[position:]:
            assert level.scope is not None  # only the root level has no scope
            if self._recalculate(level.scope) is None:
                self.reset_session()
                return False
            level.scope_id, level.count = self.scope_id, self.count
            level.acc_scope_id = level.byp_scope_id = 0
            level.dimension, level.dimension_values = None, {}
        if self.scope is not None and self._recalculate(self.scope) is None:
            self.reset_session()
            return False
        self.acc_scope_id = self.byp_scope_id = 0
        return True

    def do_out(self, arg: str) -> None:
        """Step out of the current scope, or drop one condition from the middle.

        Usage: out              (back to the previous scope)
               out <dimension>  (remove the condition on <dimension>, keep the rest)
        """
        if arg.strip():
            if not self._remove_condition(arg.strip()):
                return
        else:
            popped = self._pop_level()
            if not self.scope_id:
                self.reset_session()
                return
            if not popped:
                return
        self.clear_results()
        self.set_prompt()

    def complete_out(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete the dimensions that have a condition on the stack."""
        if len(line[:begidx].split()) > 1:
            return []
        keys = dict.fromkeys(lvl.scope.key for lvl in self.scope_stack if lvl.scope)
        return [key for key in keys if key.startswith(text)]

    def do_out_all(self, arg: str) -> None:
        """Step all the way out to the root scope."""
        while self.scope_stack:
            self._pop_level()
        self.clear_results()
        self.set_prompt()

    def do_reset(self, arg: str) -> None:
        """Forget the stack and start over from the initial scope."""
        self.reset_session()

    # ------------------------------------------------------------------ #
    # Summaries of the current scope
    # ------------------------------------------------------------------ #

    def do_track(self, arg: str) -> None:
        """Show monthly active users, request and exception counts and the time span."""
        if not self.reconnect():
            return
        params = {"scope_id": self.scope_id, "columns": "mau,req_ct,first_log,last_log,req_exc"}
        result = self.call("/scope/track", params, self.timeout(30))
        if not result:
            self.recover()
            return
        self.count = result.get("req_ct", 0)
        self.sql = result.get("sql", "")
        self.report_kind = "track"
        self.scope_id = result.get("scope_id", 0)
        self.out(
            f"{self.scope_id}: {self.scope}: "
            f"Monthly Active: {format_cell(result.get('mau', 0), 7)} "
            f"Logs: {format_cell(self.count, 9)} "
            f"Exceptions: {format_cell(result.get('req_exc', 0), 8)} "
            f"{result.get('first_log', '')} => {result.get('last_log', '')}"
        )

    def show_activity(self, picked: DimensionValue | None = None) -> None:
        """Print sessions, requests, bytes and medians, accelerated vs. bypassed.

        Args:
            picked: The breakdown row the current scope came from; its
                already-known request counts and medians are reused.
        """
        columns = ["ses_ct", "bytes", "len"]
        if picked is None:
            columns += ["req_ct", "speed"]
        params = {
            "scope_id": self.scope_id,
            "columns": ",".join(columns),
            "as_median": self.use_median(),
        }
        result = self.call("/scope/activity", params, self.timeout(30))
        if not result:
            return
        self.sql = result.get("sql", "")
        self.report_kind = "activity"
        rows: list[dict[str, Any]] = result.get("histogram", [])
        for row in rows:
            is_acc = bool(row.get("is_acc"))
            scope_id = int(str(row.get("scope_id") or 0))
            if is_acc:
                self.acc_scope_id = scope_id
            else:
                self.byp_scope_id = scope_id
            row["class"] = "acc" if is_acc else "byp"
            if picked is not None:
                row["req_ct"] = picked.acc_ct if is_acc else picked.byp_ct
                row["speed"] = picked.acc_spd if is_acc else picked.byp_spd
                row["fbu"] = picked.acc_fbu if is_acc else picked.byp_fbu

        report = self.new_report()
        for header, key in (
            ("class", "class"),
            ("<speed>", "speed"),
            ("<fbu>", "fbu"),
            ("#ses", "ses_ct"),
            ("#req", "req_ct"),
            ("#bytes", "bytes"),
            ("<len>", "len"),
        ):
            report.add_column(header, key, 8)
        empty = report.filter_empty_columns(rows)
        if empty:
            self.out("empty columns:", ", ".join(empty))
        report.render(rows)
        self.last_result = ResultTable(rows, list(report.columns))

    def do_activity(self, arg: str) -> None:
        """Compare accelerated (acc) and bypassed (byp) traffic in the current scope.

        Afterwards 'in acc' / 'in byp' step into either class.
        """
        if self.reconnect():
            self.show_activity()

    # ------------------------------------------------------------------ #
    # Saved scopes
    # ------------------------------------------------------------------ #

    def do_save_scope(self, arg: str) -> None:
        """Save the current scope under a name: save_scope <name>."""
        name = arg.strip()
        if not name:
            raise ValueError("provide a name to save the scope under")
        self.scope_library.save(name, self.describe_scope())
        self.out(f"Saved scope {name} to {self.scope_library.path}")

    def do_get_scope(self, arg: str) -> None:
        """Return to a saved scope: get_scope <name>."""
        name = arg.strip()
        if not name:
            raise ValueError("provide the name of a saved scope")
        expression = self.scope_library.get(name)
        if expression is None:
            raise ValueError(f"unknown scope name: {name}")
        self.out(f"Found saved scope {name}: {expression}")
        self.do_out_all("")
        if expression != "all":
            self.do_in(expression)

    def complete_get_scope(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete the names of saved scopes."""
        try:
            names = self.scope_library.load()
        except (OSError, ValueError):
            return []
        return [name for name in names if name.startswith(text)]
