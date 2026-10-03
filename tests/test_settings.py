import json
import stat

import pytest

from slice_and_dice.constants import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from slice_and_dice.settings import Settings, default_config_dir


def test_missing_file_yields_defaults(tmp_path):
    settings = Settings.load(tmp_path / "missing.json")
    assert settings.get("use-median") == 1
    assert settings.password is None


def test_corrupt_file_yields_defaults(tmp_path, caplog):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    settings = Settings.load(path)
    assert settings.get("max-prompt") == 80
    assert "malformed" in caplog.text


def test_non_object_file_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]")
    assert Settings.load(path).get("max-prompt") == 80


def test_legacy_password_key_is_migrated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"passwd": "old"}))
    assert Settings.load(path).password == "old"


def test_save_round_trips_with_owner_only_permissions(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    settings = Settings(path, {"timeout": 60})
    settings.password = "secret"
    assert settings.save()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    reloaded = Settings.load(path)
    assert reloaded.get("timeout") == 60
    assert reloaded.password == "secret"


def test_numeric_strings_are_returned_as_integers(tmp_path):
    settings = Settings(tmp_path / "s.json", {"max-results": "25", "delimiter": "|"})
    assert settings.get("max-results") == 25
    assert settings.get("delimiter") == "|"
    assert settings.get("missing") == 0
    assert settings.get("missing", None) is None


def test_get_int_falls_back_on_garbage(tmp_path):
    settings = Settings(tmp_path / "s.json", {"timeout": "soon"})
    assert settings.get_int("timeout", 30) == 30


def test_get_str_treats_empty_as_unset(tmp_path):
    settings = Settings(tmp_path / "s.json", {"delimiter": ""})
    assert settings.get_str("delimiter", "|") == "|"


def test_update_with_none_removes_the_setting(tmp_path):
    settings = Settings(tmp_path / "s.json", {"delimiter": "|"})
    settings.update({"delimiter": None, "timeout": 5})
    assert "delimiter" not in settings
    assert settings["timeout"] == 5


def test_public_view_masks_the_password(tmp_path):
    settings = Settings(tmp_path / "s.json", {"password": "secret"})
    assert settings.public_view()["password"] == "********"


def test_server_address(tmp_path):
    settings = Settings(tmp_path / "s.json")
    assert settings.server_address() == (DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT)
    settings.update({"api-server-host": "db.example.com", "api-server-port": "9000"})
    assert settings.server_address() == ("db.example.com", 9000)
    assert settings.server_address("other", 1) == ("other", 1)


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({"SLICE_AND_DICE_CONFIG_DIR": "/explicit"}, "/explicit"),
        ({"XDG_CONFIG_HOME": "/xdg"}, "/xdg/slice_and_dice"),
    ],
)
def test_default_config_dir(monkeypatch, environment, expected):
    monkeypatch.delenv("SLICE_AND_DICE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    assert str(default_config_dir()) == expected
