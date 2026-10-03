import io

from slice_and_dice.report import Column, Report


def make_report(**kwargs):
    stream = io.StringIO()
    report = Report(stream=stream, **kwargs)
    report.add_column("name", "name", 6)
    report.add_column("count", "count", 7)
    return report, stream


def test_render_prints_header_and_rows():
    report, stream = make_report()
    report.render([{"name": "LTE", "count": 1500}])
    assert stream.getvalue().splitlines() == ["name  count  ", "LTE   1.5K   "]


def test_first_column_is_never_abbreviated():
    report, stream = make_report()
    report.render([{"name": 12345, "count": 1}])
    assert stream.getvalue().splitlines()[1].startswith("12345 ")


def test_delimiter_goes_between_columns():
    report, _ = make_report(delimiter="|")
    assert report.format_header() == "name  | count  "


def test_table_delimiter_also_frames_the_line():
    report, _ = make_report(table_delimiter="|")
    assert report.format_header() == "|name  | count  | "


def test_rows_without_any_data_are_skipped():
    report, stream = make_report()
    report.write_row({"other": 1})
    assert stream.getvalue() == ""


def test_filter_empty_columns_drops_columns_without_data():
    report, _ = make_report()
    report.add_column("zeros", "zeros", 5)
    removed = report.filter_empty_columns([{"name": "a", "count": 0, "zeros": "0"}])
    assert removed == ["count", "zeros"]
    assert report.columns == [Column("name", "name", 6)]


def test_columns_without_header_or_key_are_ignored():
    report = Report()
    report.add_column("", "key", 5)
    report.add_column("header", "", 5)
    assert report.columns == []


def test_has_and_remove_column():
    report, _ = make_report()
    assert report.has_column("count")
    report.remove_column("count")
    assert not report.has_column("count")
    report.remove_column("missing")  # no error
    assert [c.header for c in report.columns] == ["name"]
