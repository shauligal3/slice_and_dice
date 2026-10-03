import pytest

from slice_and_dice.report_spec import ReportSpec


def parse_outcome(expression):
    aggregate, _, dimension = expression.partition(" ")
    return [f"{aggregate}({dimension})"] if dimension else None


DOCUMENT = {
    "name": "burst",
    "control-fields-no-agg": ["network", {"size": [50000, 10000]}, "not_a_dimension"],
    "control-fields-agg": ["hour", "network"],
    "policy-fields": [{"max_burst": [6000, 3000]}],
    "outcome": ["median fbu", {"median dcu": 1}, "garbage"],
}


def test_from_document():
    spec = ReportSpec.from_document(DOCUMENT, parse_outcome)
    assert spec.name == "burst"
    assert spec.outcomes == ["median(fbu)", "median(dcu)"]
    assert spec.control_no_agg == [("network", ""), ("size", "10000,50000")]
    # "network" is already a non-aggregated control field.
    assert spec.control_agg == [("hour", "")]
    assert spec.policy == [("max_burst", "3000,6000")]


def test_datetime_control_needs_breakpoints():
    with pytest.raises(ValueError, match="datetime"):
        ReportSpec.from_document({"control-fields-agg": ["datetime"]}, parse_outcome)


def test_projection_params():
    params = ReportSpec.from_document(DOCUMENT, parse_outcome).projection_params()
    assert params == {
        "control_fields": "hour;network;size",
        "breakpoints_control": ";;10000,50000",
        "outcome_fields": "median(fbu),median(dcu)",
        "policy_fields": "max_burst",
        "policy_fields_breakpoints": "3000,6000",
    }


def test_best_policy_params():
    params = ReportSpec.from_document(DOCUMENT, parse_outcome).best_policy_params()
    assert params["control_fields_agg"] == "hour"
    assert params["control_fields_no_agg"] == "network;size"
    assert params["breakpoints_no_agg"] == ";10000,50000"


def test_document_from_command():
    document = ReportSpec.document_from_command(
        {
            "control": ["network", "size"],
            "policy": "max_burst",
            "outcome": "fbu",
            "bp_size": [10000, 50000],
        }
    )
    assert document == {
        "name": "ad-hoc",
        "timeout": 120,
        "control-fields-no-agg": ["network", {"size": [10000, 50000]}],
        "policy-fields": ["max_burst"],
        "outcome": ["median fbu"],
    }
