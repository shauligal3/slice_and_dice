from datetime import datetime

from slice_and_dice.formatting import (
    abbreviate_number,
    format_cell,
    pretty_print_records,
    timestamp_slug,
    to_json,
)


def test_abbreviate_number_scales_large_values():
    assert abbreviate_number(1_234_567_890) == "1.23G"
    assert abbreviate_number(2_500_000) == "2.50M"
    assert abbreviate_number(1_234) == "1.2K"
    assert abbreviate_number(12) == "12"
    assert abbreviate_number(12.5) == "12.50"


def test_abbreviate_number_handles_negative_values():
    assert abbreviate_number(-2_500_000) == "-2.50M"


def test_format_cell_pads_to_width():
    assert format_cell("abc", 6) == "abc   "


def test_format_cell_truncates_and_keeps_a_separating_space():
    assert format_cell("abcdefgh", 5) == "abcd "


def test_format_cell_abbreviates_numbers_only_when_asked():
    assert format_cell(1500, 8) == "1.5K    "
    assert format_cell(1500, 8, abbreviate=False) == "1500    "


def test_format_cell_does_not_treat_booleans_as_numbers():
    assert format_cell(True, 6) == "True  "


def test_pretty_print_records_writes_title_and_records(tmp_path):
    copy_path = tmp_path / "copy.txt"
    import io

    screen = io.StringIO()
    with copy_path.open("w") as copy:
        pretty_print_records([{"a": 1}], "Title", stream=screen, copy_to=copy)
    assert screen.getvalue() == "Title\n{'a': 1}\n\n"
    assert copy_path.read_text() == "Title\n{'a': 1}\n"


def test_to_json_stringifies_unknown_types():
    class ObjectId:
        def __str__(self):
            return "abc123"

    text = to_json({"id": ObjectId(), "when": datetime(2024, 5, 1, 12, 0)})
    assert text == '{"id": "abc123", "when": "2024-05-01T12:00:00"}'


def test_timestamp_slug_is_filesystem_friendly():
    assert timestamp_slug(datetime(2024, 5, 1, 13, 45, 10)) == "2024-05-01_13-45-10"
