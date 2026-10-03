import pytest

from slice_and_dice.command_grammar import CommandGrammar
from slice_and_dice.command_param import CommandParam
from slice_and_dice.grammars import aggregate_grammar, report_grammar, settings_grammar
from slice_and_dice.parsed_command import ParsedCommand, as_list


@pytest.fixture
def grammar():
    g = CommandGrammar("demo")
    g.add_param(CommandParam("median", max_vals=3, options=["fbu", "dcu", "speed"]))
    g.add_param(CommandParam("max", max_vals=1, options=["fbu", "dcu"]))
    g.add_param(CommandParam("limit", options=[]))
    g.add_param(CommandParam("desc", min_vals=0, max_vals=0))
    g.add_param(CommandParam("mode", required=True, options=["fast", "slow"]))
    return g


def test_validate_collects_values_per_keyword(grammar):
    params, error = grammar.validate("median fbu dcu max fbu mode fast")
    assert error == ""
    assert params == {"median": ["fbu", "dcu"], "max": "fbu", "mode": "fast"}


def test_numeric_values_become_integers(grammar):
    params, _ = grammar.validate("limit 25 mode fast")
    assert params["limit"] == 25


def test_flags_take_no_value(grammar):
    params, error = grammar.validate("desc mode slow")
    assert error == ""
    assert params == {"desc": None, "mode": "slow"}


def test_missing_required_keyword_is_an_error(grammar):
    _, error = grammar.validate("median fbu")
    assert error == "missing a required parameter: mode"


def test_missing_value_is_an_error(grammar):
    _, error = grammar.validate("mode")
    assert "missing a value for keyword: mode" in error


def test_unknown_keyword_is_an_error(grammar):
    _, error = grammar.validate("bogus mode fast")
    assert error == "error found in command keyword: bogus"


def test_value_outside_options_is_an_error(grammar):
    _, error = grammar.validate("max speed mode fast")
    assert error == "error found in command parameter: speed"


def test_partial_word_followed_by_more_words_is_an_error(grammar):
    _, error = grammar.validate("med fbu mode fast")
    assert error == "error found in command keyword: med"


def test_arithmetic_expressions_bypass_options(grammar):
    params, error = grammar.validate("max fbu-dcu mode fast")
    assert error == ""
    assert params["max"] == "fbu-dcu"


def test_completes_keywords_after_a_space(grammar):
    assert grammar.complete("demo ") == ["median", "max", "limit", "desc", "mode"]


def test_completes_partial_keyword(grammar):
    assert grammar.complete("demo m") == ["median", "max", "mode"]


def test_completes_options_after_keyword(grammar):
    assert grammar.complete("demo median ") == ["fbu", "dcu", "speed"]


def test_completes_partial_option(grammar):
    assert grammar.complete("demo median d") == ["dcu"]


def test_offers_remaining_options_and_keywords_after_a_value(grammar):
    completions = grammar.complete("demo median fbu ")
    assert completions == ["max", "limit", "desc", "mode", "dcu", "speed"]


def test_no_completion_without_trailing_space(grammar):
    assert grammar.complete("demo median fbu") == []


def test_inactive_keywords_are_hidden(grammar):
    grammar.get_param("desc").is_active = False
    assert "desc" not in grammar.complete("demo ")
    _, error = grammar.validate("desc mode fast")
    assert error


def test_parsed_command_accumulates_values():
    parsed = ParsedCommand()
    parsed.append_value("k", "a")
    assert parsed.params["k"] == "a"
    parsed.append_value("k", "b")
    parsed.append_value("k", "c")
    assert parsed.params["k"] == ["a", "b", "c"]
    assert parsed.value_count("k") == 3
    assert parsed.value_count("missing") == 0


def test_parsed_command_joins_errors():
    parsed = ParsedCommand()
    parsed.append_error("")
    parsed.append_error("one")
    parsed.append_error("two")
    assert parsed.error == "one\ntwo"


def test_as_list():
    assert as_list(None) == []
    assert as_list("a") == ["a"]
    assert as_list(["a", "b"]) == ["a", "b"]


def test_aggregate_grammar():
    params, error = aggregate_grammar().validate("median fbu dcu perc95 speed acc_ct")
    assert error == ""
    assert params == {"median": ["fbu", "dcu"], "perc95": "speed", "acc_ct": None}


def test_aggregate_grammar_rejects_non_numeric_dimensions():
    _, error = aggregate_grammar().validate("median geo")
    assert error


def test_settings_grammar_allows_resetting_a_setting():
    params, error = settings_grammar().validate("max-results 20 delimiter")
    assert error == ""
    assert params == {"max-results": 20, "delimiter": None}


def test_report_grammar_requires_control_and_policy():
    _, error = report_grammar().validate("outcome fbu")
    assert "control" in error
    assert "policy" in error
