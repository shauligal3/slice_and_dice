import pytest

from slice_and_dice.partition import Partition, parse_partition


def test_empty_expression_is_an_empty_partition():
    assert parse_partition("") == Partition([], [])


def test_categorical_dimension_has_no_breakpoints():
    assert parse_partition("network") == Partition(["network"], [""])


def test_numeric_breakpoints_are_sorted_numerically():
    partition = parse_partition("size breakpoints 50000 9000 100000")
    assert partition.breakpoints == ["9000,50000,100000"]


def test_breakpoints_keyword_is_optional():
    assert parse_partition("size 200 100") == parse_partition("size breakpoints 100 200")


def test_several_dimensions():
    partition = parse_partition("size 10000 geo network")
    assert partition.fields == ["size", "geo", "network"]
    assert partition.fields_param() == "size;geo;network"
    assert partition.breakpoints_param() == "10000;;"


def test_date_breakpoints_are_parsed_and_sorted():
    partition = parse_partition("date 2024-05-08 2024-05-01")
    assert partition.breakpoints == ["2024-05-01,2024-05-08"]


def test_datetime_breakpoints():
    partition = parse_partition("datetime 2024-05-01_12:30")
    assert partition.breakpoints == ["2024-05-01 12:30:00"]


def test_textual_breakpoints_put_longest_prefix_first():
    partition = parse_partition("url_domain a.com cdn.a.com")
    assert partition.breakpoints == ["cdn.a.com,a.com"]


def test_bad_numeric_breakpoint():
    with pytest.raises(ValueError, match="must be integers"):
        parse_partition("size 10k")


def test_bad_date_breakpoint():
    with pytest.raises(ValueError, match="must look like"):
        parse_partition("date yesterday")


def test_expression_must_start_with_a_dimension():
    with pytest.raises(ValueError, match="expected a dimension, got: bogus"):
        parse_partition("bogus network")
