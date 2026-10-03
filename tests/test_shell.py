"""End-to-end tests of the shell against the fake server."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from helpers import output, run
from slice_and_dice.api_client import ApiClient
from slice_and_dice.scope_library import ScopeLibrary
from slice_and_dice.settings import Settings
from slice_and_dice.shell import Shell
from slice_and_dice.shell_options import ShellOptions

YESTERDAY = (datetime.now() - timedelta(hours=24)).date().isoformat()


# --------------------------------------------------------------------------- #
# Start-up
# --------------------------------------------------------------------------- #


def test_starts_with_the_last_day_of_data(make_shell, server, config_dir):
    shell = make_shell()
    assert shell.prompt == f"[11:datetime > {YESTERDAY}] "
    assert server.last("/scope/narrow") == {
        **server.last("/scope/narrow"),
        "scope_id": "0",
        "column": "datetime",
        "op": "gt",
        "value": YESTERDAY,
    }
    assert server.last("/scope/set_unittestmode")["unittestmode"] == "0"
    saved = json.loads((config_dir / "settings.json").read_text())
    assert saved["password"] == "secret"


def test_password_is_not_saved_when_asked_not_to(make_shell, config_dir):
    make_shell(remember_password=False)
    assert not (config_dir / "settings.json").exists()


def test_test_mode_starts_with_the_test_customer(make_shell, server):
    shell = make_shell(test_mode=True)
    assert server.last("/scope/set_unittestmode")["unittestmode"] == "1"
    assert server.last("/scope/narrow")["value"] == "3533"
    assert shell.cid == "3533"


def test_empty_stack_starts_at_the_root(make_shell, server):
    shell = make_shell(empty_stack=True)
    assert shell.prompt == "[0:all] "
    assert "/scope/narrow" not in server.endpoints()


def test_wrong_password_fails_and_forgets_the_saved_one(server, config_dir):
    settings = Settings(config_dir / "settings.json", {"password": "stale"})
    shell = Shell(
        ApiClient("127.0.0.1", server.port, "stale"),
        settings,
        ScopeLibrary(config_dir / "scopes.json"),
        options=ShellOptions(),
        stdout=__import__("io").StringIO(),
    )
    with pytest.raises(ConnectionError, match="incorrect password"):
        shell.start()
    assert settings.password is None


# --------------------------------------------------------------------------- #
# Scope navigation
# --------------------------------------------------------------------------- #


def test_in_and_out(make_shell):
    shell = make_shell()
    text = run(shell, "in geo = US and network LTE")
    assert "[:12 geo = US] Logs: 12.0K" in text
    assert shell.describe_scope() == f"datetime > {YESTERDAY} and geo = US and network = LTE"
    run(shell, "out")
    assert shell.describe_scope() == f"datetime > {YESTERDAY} and geo = US"
    assert shell.scope_id == 12
    run(shell, "out_all")
    assert shell.prompt == "[0:all] "


def test_in_accepts_symbolic_and_named_operators(make_shell, server):
    shell = make_shell()
    run(shell, "in size >= 1000")
    assert server.last("/scope/narrow")["op"] == "gte"
    run(shell, "in dns is-null")
    assert server.last("/scope/narrow")["op"] == "is-null"


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("in bogus = 1", "error: illegal dimension: bogus"),
        ("in geo", "error: incomplete condition"),
        ("in size gt", "error: missing a value"),
    ],
)
def test_in_reports_bad_conditions(make_shell, command, message):
    shell = make_shell()
    assert message in run(shell, command)


def test_out_of_a_middle_condition_recalculates_the_inner_ones(make_shell, server):
    shell = make_shell()
    run(shell, "in geo = US", "in network = LTE")
    text = run(shell, "out geo")
    assert "recalc network = LTE" in text
    assert server.last("/scope/narrow")["scope_id"] == "11"  # re-applied on the day scope
    assert shell.describe_scope() == f"datetime > {YESTERDAY} and network = LTE"
    assert "could not find" in run(shell, "out os")


def test_jump_in_evaluates_the_whole_query_at_once(make_shell, server):
    shell = make_shell()
    run(shell, "jump_in geo = US and os = ios")
    assert server.last("/scope/jump") == {
        **server.last("/scope/jump"),
        "scope_id": "11",
        "query": "geo = US and os = ios",
    }
    assert shell.describe_scope().endswith("geo = US and os = ios")


def test_show_stack_and_scope(make_shell):
    shell = make_shell()
    run(shell, "in geo = US")
    lines = run(shell, "show stack").splitlines()
    assert lines[0] == "[0] all #ct=0"
    assert lines[-1] == "[12] geo = US #ct=12000"
    assert run(shell, "show scope").strip() == shell.describe_scope()


def test_saved_scopes(make_shell, config_dir):
    shell = make_shell()
    run(shell, "in geo = US", "save_scope us")
    assert "us" in json.loads((config_dir / "saved_scopes.json").read_text())
    run(shell, "out_all")
    assert "Found saved scope us" in run(shell, "get_scope us")
    assert shell.describe_scope() == f"datetime > {YESTERDAY} and geo = US"
    assert "unknown scope name" in run(shell, "get_scope nope")
    assert shell.complete_get_scope("u", "get_scope u", 10, 11) == ["us"]


def test_activity_then_step_into_a_traffic_class(make_shell, server):
    shell = make_shell()
    lines = run(shell, "activity").splitlines()
    assert lines[0] == "empty columns: <fbu>, #bytes, <len>"
    assert lines[1].split() == ["class", "<speed>", "#ses", "#req"]
    assert lines[2].split() == ["acc", "2.0K", "40", "900"]
    narrows = server.endpoints().count("/scope/narrow")
    run(shell, "in acc")
    assert server.endpoints().count("/scope/narrow") == narrows  # id already known
    assert shell.scope_id == 501


def test_track(make_shell):
    shell = make_shell()
    assert "Logs: 5.0K" in run(shell, "track")


# --------------------------------------------------------------------------- #
# Breakdowns
# --------------------------------------------------------------------------- #


def test_group_by_then_step_into_a_value(make_shell, server):
    shell = make_shell()
    text = run(shell, "group_by network")
    assert "LTE" in text
    assert "[ 0 - 3 of 3 rows ]" in text
    params = server.last("/scope/breakdown")
    assert (params["partition"], params["breakpoints"], params["scope_id"]) == ("network", "", "11")

    narrows = server.endpoints().count("/scope/narrow")
    run(shell, "in LTE")
    assert server.endpoints().count("/scope/narrow") == narrows
    assert shell.scope_id == 101
    assert shell.describe_scope().endswith("network = LTE")


def test_group_by_pages_with_enter(make_shell, server):
    shell = make_shell()
    run(shell, "set max-results 2")
    assert "[ 0 - 2 of 3 rows ]" in run(shell, "group_by network")
    assert "[ 2 - 3 of 3 rows ]" in run(shell, "")
    assert server.last("/scope/breakdown")["startfrom"] == "2"
    assert "(end of results)" in run(shell, "")


def test_enter_does_not_repeat_other_commands(make_shell):
    shell = make_shell()
    run(shell, "in geo = US")
    run(shell, "")
    assert shell.describe_scope().count("geo") == 1


def test_group_by_with_breakpoints_and_flags(make_shell, server):
    shell = make_shell()
    run(shell, "group_by size 50000 10000 geo classmerge")
    params = server.last("/scope/breakdown")
    assert params["partition"] == "size;geo"
    assert params["breakpoints"] == "10000,50000;"
    assert params["classmerge"] == "1"


def test_group_by_save_output_writes_a_csv(make_shell, tmp_path):
    shell = make_shell()
    assert "saved 3 rows to breakdown_" in run(shell, "group_by network save_output")
    assert len(list(tmp_path.glob("breakdown_*.csv"))) == 1


def test_group_by_rejects_bad_breakpoints(make_shell):
    shell = make_shell()
    assert "error: breakpoints of size must be integers" in run(shell, "group_by size big")


def test_select_and_order_by(make_shell, server):
    shell = make_shell()
    run(shell, "select median fbu perc95 speed")
    assert shell.breakdown_selected == ["median(fbu)", "perc95(speed)"]
    run(shell, "group_by network")
    assert server.last("/scope/breakdown")["columns"] == "median(fbu),perc95(speed)"

    run(shell, "order_by median dcu desc")
    params = server.last("/scope/breakdown")
    assert (params["order_by"], params["desc"]) == ("median(dcu)", "1")
    run(shell, "order_by acc_ct")
    params = server.last("/scope/breakdown")
    assert (params["order_by"], params["desc"]) == ("acc_ct", "0")

    run(shell, "unselect median fbu")
    assert "median(fbu)" not in shell.breakdown_selected
    run(shell, "unselect")
    assert shell.breakdown_selected == []


def test_order_by_needs_a_breakdown(make_shell):
    shell = make_shell()
    assert "order_by needs a group_by" in run(shell, "order_by acc_ct")


def test_cluster(make_shell, server):
    shell = make_shell()
    text = run(shell, "cluster speed 3")
    assert server.last("/scope/cluster")["buckets"] == "3"
    assert "percentage share" in text
    assert "must be an integer" in run(shell, "cluster speed many")


def test_save_output_exports_the_last_table(make_shell, tmp_path):
    shell = make_shell()
    assert "there is no result to save" in run(shell, "save_output")
    run(shell, "group_by network")
    assert "csv written to net.csv" in run(shell, "save_output net")
    lines = (tmp_path / "net.csv").read_text().splitlines()
    assert lines[0] == f"Scope:datetime > {YESTERDAY}"
    assert lines[1].startswith("network|%gain")


# --------------------------------------------------------------------------- #
# Samples
# --------------------------------------------------------------------------- #


def test_samples_hide_columns_fixed_by_the_scope(make_shell, server):
    shell = make_shell()
    header = run(shell, "samples").splitlines()[0].split()
    assert {"ses", "speed", "geo"} <= set(header)
    run(shell, "in geo = US")
    header = run(shell, "samples").splitlines()[0].split()
    assert "geo" not in header


def test_samples_order_by_and_paging(make_shell, server):
    shell = make_shell()
    run(shell, "set max-results 1", "samples order-by speed desc")
    params = server.last("/scope/samples")
    assert (params["order_by"], params["desc"], params["startfrom"]) == ("speed", "1", "0")
    run(shell, "")
    assert server.last("/scope/samples")["startfrom"] == "1"
    assert "usage: samples" in run(shell, "samples speed")


def test_select_reorders_samples(make_shell):
    shell = make_shell()
    run(shell, "samples")
    header = run(shell, "select size").splitlines()[0].split()
    assert header[0] == "size"
    header = run(shell, "unselect").splitlines()[0].split()
    assert header[0] != "size"


def test_timelines(make_shell):
    shell = make_shell()
    lines = run(shell, "timelines").splitlines()
    assert lines[0].split() == ["speed", "size", "timeline"]
    assert "dcu" in lines[1]


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def test_run_saved_projection_report(make_shell, server, tmp_path):
    shell = make_shell()
    text = run(shell, "run_report burst")
    params = server.last("/scope/gen_report")
    assert params["control_fields"] == "size;network"
    assert params["breakpoints_control"] == "10000,50000;"
    assert params["outcome_fields"] == "median(fbu)"
    assert "3 rows returned" in text
    assert len(list(tmp_path.glob("burst-by-network_*.csv"))) == 1


def test_find_best_policy_writes_its_results(make_shell, server, tmp_path):
    shell = make_shell()
    run(shell, "in network = LTE")
    text = run(shell, "find_best_policy burst")
    assert "Recommended Policies:" in text
    params = server.last("/scope/best_policy")
    assert params["policy_fields_breakpoints"] == "3000,6000"
    names = [path.name for path in (tmp_path / "policy_files").iterdir()]
    suffixes = sorted(name.split("_", 1)[1][len("2024-05-01_13-45-10") :] for name in names)
    assert suffixes == [".csv", ".json", ".txt", "_pscript.txt"]
    script = next((tmp_path / "policy_files").glob("*_pscript.txt")).read_text()
    assert "rm cid0--LTE" in script


def test_build_ad_hoc_report(make_shell, server):
    shell = make_shell()
    run(shell, "build_report control network policy max_burst outcome fbu bp_max_burst 6000 3000")
    params = server.last("/scope/best_policy")
    assert params["control_fields_no_agg"] == "network"
    assert params["policy_fields_breakpoints"] == "3000,6000"
    assert params["outcome_fields"] == "median(fbu)"
    assert "missing a required parameter: policy" in run(shell, "build_report control network")


def test_training_set(make_shell, server, tmp_path):
    shell = make_shell()
    run(shell, "training_set network filename ts")
    assert (tmp_path / "datasets" / "ts.csv").exists()
    scope = json.loads((tmp_path / "datasets" / "ts.scope.txt").read_text())
    assert scope == {"scope": f"datetime > {YESTERDAY}", "cmd": "network"}
    assert "filename needs a value" in run(shell, "training_set network filename")


# --------------------------------------------------------------------------- #
# Settings, help and robustness
# --------------------------------------------------------------------------- #


def test_set_and_save(make_shell, config_dir):
    shell = make_shell()
    run(shell, "set max-results 25 delimiter |")
    assert shell.settings.get("max-results") == 25
    assert "settings saved" in run(shell, "save")
    saved = json.loads((config_dir / "settings.json").read_text())
    assert saved["delimiter"] == "|"
    run(shell, "set delimiter")
    assert "delimiter" not in shell.settings
    assert "error found in command keyword: bogus" in run(shell, "set bogus 1")


def test_show_settings_masks_the_password(make_shell):
    shell = make_shell()
    text = run(shell, "show settings")
    assert "secret" not in text
    assert '"password": "********"' in text


def test_help(make_shell):
    shell = make_shell()
    text = run(shell, "help in")
    assert text.startswith("Narrow the current scope")
    assert "\nUsage: in <dimension>" in text  # docstring indentation removed
    assert "group_by" in run(shell, "help")


def test_unknown_command(make_shell):
    shell = make_shell()
    assert "error: unknown command: frobnicate" in run(shell, "frobnicate now")


def test_unexpected_errors_are_reported_not_raised(make_shell, monkeypatch):
    shell = make_shell()

    def boom(*args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(shell, "show_activity", boom)
    text = run(shell, "activity")
    assert "unexpected RuntimeError: kaboom" in text
    assert "--debug" in text


def test_server_restart_rebuilds_the_stack(make_shell, server):
    shell = make_shell()
    run(shell, "in geo = US")
    server.started = 2
    text = run(shell, "group_by network")
    assert "restarted" in text
    assert "recalc geo = US" in text
    assert shell.describe_scope() == f"datetime > {YESTERDAY} and geo = US"


def test_server_down(make_shell, server):
    shell = make_shell()
    server.stop()
    shell.client.close()  # drop the kept-alive connection too
    assert "error: the server is down" in run(shell, "in geo = US")


def test_echo_mode(make_shell):
    shell = make_shell()
    run(shell, "echo")
    assert run(shell, "print hello") == "print hello\nhello\n"


def test_exit_and_eof_stop_the_loop(make_shell):
    shell = make_shell()
    assert shell.onecmd("exit") is True
    assert shell.onecmd("EOF") is True
    output(shell)


# --------------------------------------------------------------------------- #
# Completion
# --------------------------------------------------------------------------- #


def test_complete_in(make_shell):
    shell = make_shell()
    assert "geo" in shell.complete_in("ge", "in ge", 3, 5)
    assert shell.complete_in("", "in geo ", 7, 7)[:3] == ["gt", "lt", "eq"]
    assert "network" in shell.complete_in("net", "in geo = US and net", 16, 19)
    run(shell, "group_by network")
    assert shell.complete_in("LT", "in LT", 3, 5) == ["LTE"]


def test_complete_group_by(make_shell):
    shell = make_shell()
    assert shell.complete_group_by("", "group_by size ", 14, 14)[0] == "breakpoints"
    assert "network" not in shell.complete_group_by("", "group_by network ", 17, 17)


def test_complete_select_and_set(make_shell):
    shell = make_shell()
    assert shell.complete_select("me", "select me", 7, 9) == ["median"]
    assert shell.complete_set("max-res", "set max-res", 4, 11) == ["max-results"]
    assert shell.complete_show("se", "show se", 5, 7) == ["settings", "selected", "server"]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("show_reports burst", "'name': 'burst-by-network'"),
        ("projection_report control network policy max_burst outcome fbu", "3 rows returned"),
        ("recommended_policies", "{}"),
        ("recommended_policies burst", "Report: burst-by-network"),
        ("best_strategy", "{}"),
        ("visualize_performance", "File saved on the server:"),
        ("session 123 click", "{}"),
        ("policyd status", "None"),
        ("show server", '"version": "test"'),
        ("show rest", "/scope/narrow?scope_id=0"),
        ("show sql", "SELECT"),
        ("show iter", "samples 0 breakdown 0"),
        ("show selected", "(none)"),
        ("training_set", "max_burst"),
        ("reset", "Connecting"),
    ],
)
def test_other_commands(make_shell, command, expected):
    shell = make_shell()
    text = run(shell, command)
    assert expected in text
    assert "error" not in text


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("show nothing", "show what?"),
        ("session abc", "usage: session"),
        ("run_report", "usage: run_report"),
        ("find_best_policy", "usage: find_best_policy"),
        ("save_scope", "provide a name"),
        ("jump_in", "needs at least one condition"),
        ("cluster", "needs a numeric dimension"),
        ("set", "usage: set"),
    ],
)
def test_command_usage_errors(make_shell, command, message):
    shell = make_shell()
    assert message in run(shell, command)


def test_complete_out(make_shell):
    shell = make_shell()
    run(shell, "in geo = US", "in os = ios")
    assert shell.complete_out("", "out ", 4, 4) == ["datetime", "geo"]
    assert shell.complete_out("g", "out g", 4, 5) == ["geo"]
