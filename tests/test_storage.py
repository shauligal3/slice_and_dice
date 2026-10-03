import pytest

from slice_and_dice.export import write_csv
from slice_and_dice.report import Column
from slice_and_dice.scope_library import ScopeLibrary


def test_scope_library_round_trip(tmp_path):
    library = ScopeLibrary(tmp_path / "dir" / "scopes.json")
    assert library.load() == {}
    library.save("us", "geo = US")
    library.save("lte", "network = LTE")
    assert library.get("us") == "geo = US"
    assert library.get("missing") is None
    assert set(library.load()) == {"us", "lte"}


def test_scope_library_rejects_malformed_files(tmp_path):
    path = tmp_path / "scopes.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        ScopeLibrary(path).load()


def test_write_csv_with_columns(tmp_path):
    path = tmp_path / "out.csv"
    rows = [{"network": "LTE|4G", "acc_ct": 5, "ignored": 1}]
    count = write_csv(
        path,
        rows,
        columns=[Column("net", "network", 5), Column("#Acc", "acc_ct", 5)],
        delimiter="|",
        delimiter_replacement="-",
        preamble="Scope:all",
    )
    assert count == 1
    assert path.read_text().splitlines() == ["Scope:all", "net|#Acc", "LTE-4G|5"]


def test_write_csv_without_columns_exports_every_key(tmp_path):
    path = tmp_path / "out.csv"
    write_csv(path, [{"a": 1}, {"b": 2}])
    assert path.read_text().splitlines() == ["a,b", "1,", ",2"]
