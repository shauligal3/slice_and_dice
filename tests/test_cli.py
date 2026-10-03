import pytest

from slice_and_dice import __version__
from slice_and_dice.cli import main


@pytest.fixture
def base_args(server, config_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SLICE_AND_DICE_PASSWORD", "secret")
    return [
        "--host",
        "127.0.0.1",
        "--port",
        str(server.port),
        "--config-dir",
        str(config_dir),
        "--keepalive",
        "0",
    ]


def test_runs_commands_and_exits(base_args, capsys, config_dir):
    status = main([*base_args, "-c", "group_by network", "-c", "show scope"])
    out = capsys.readouterr().out
    assert status == 0
    assert "Connecting 127.0.0.1" in out
    assert "LTE" in out
    # A password from the environment is never written to disk.
    assert not (config_dir / "settings.json").exists()


def test_wrong_password_exits_with_an_error(base_args, capsys, monkeypatch):
    monkeypatch.setenv("SLICE_AND_DICE_PASSWORD", "wrong")
    assert main([*base_args, "-c", "show scope"]) == 1
    assert "error: failed to connect" in capsys.readouterr().err


def test_keepalive_runs_alongside_commands(base_args, server):
    base_args[-1] = "60"
    assert main([*base_args, "-c", "print hi"]) == 0


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out
