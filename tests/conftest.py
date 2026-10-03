"""Shared fixtures."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import pytest

from fake_server import FakeServer
from slice_and_dice.api_client import ApiClient
from slice_and_dice.scope_library import ScopeLibrary
from slice_and_dice.settings import Settings
from slice_and_dice.shell import Shell
from slice_and_dice.shell_options import ShellOptions

PASSWORD = "secret"


@pytest.fixture
def server() -> Iterator[FakeServer]:
    """A running fake analytics server."""
    fake = FakeServer(PASSWORD).start()
    yield fake
    fake.stop()


@pytest.fixture
def client(server: FakeServer) -> Iterator[ApiClient]:
    """A client connected to the fake server."""
    api = ApiClient("127.0.0.1", server.port, PASSWORD)
    yield api
    api.close()


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """An empty configuration directory."""
    directory = tmp_path / "config"
    directory.mkdir()
    return directory


@pytest.fixture
def make_shell(
    client: ApiClient, config_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """Build a started shell whose output can be read with ``output()``.

    Files the shell writes (CSV exports, policy files) land in ``tmp_path``.
    """
    monkeypatch.chdir(tmp_path)

    def build(**options: object) -> Shell:
        settings = Settings.load(config_dir / "settings.json")
        stdout = io.StringIO()
        shell = Shell(
            client,
            settings,
            ScopeLibrary(config_dir / "saved_scopes.json"),
            options=ShellOptions(**options),  # type: ignore[arg-type]
            stdout=stdout,
        )
        shell.start()
        return shell

    return build
