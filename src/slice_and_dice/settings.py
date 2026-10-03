"""Persistent user settings, stored as JSON in the configuration directory."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from slice_and_dice.constants import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT, DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

_PASSWORD_KEY = "password"
_LEGACY_PASSWORD_KEY = "passwd"
_MASK = "********"


def default_config_dir() -> Path:
    """Return the directory holding settings and saved scopes.

    Resolution order: ``$SLICE_AND_DICE_CONFIG_DIR``, then
    ``$XDG_CONFIG_HOME/slice_and_dice``, then ``~/.config/slice_and_dice``.
    """
    explicit = os.environ.get("SLICE_AND_DICE_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base).expanduser() / "slice_and_dice"


class Settings(Mapping[str, Any]):
    """Key/value settings backed by a JSON file.

    Values typed at the prompt arrive as strings; :meth:`get` transparently
    converts purely numeric strings back to integers.

    The file may hold the server password, so it is always written with
    owner-only permissions.

    Args:
        path: The JSON file the settings are saved to.
        values: Initial values; :data:`DEFAULT_SETTINGS` fill in the gaps.
    """

    def __init__(self, path: Path, values: Mapping[str, Any] | None = None) -> None:
        self.path = path
        self._values: dict[str, Any] = dict(values or {})
        if _LEGACY_PASSWORD_KEY in self._values:
            self._values.setdefault(_PASSWORD_KEY, self._values.pop(_LEGACY_PASSWORD_KEY))
        for key, value in DEFAULT_SETTINGS.items():
            self._values.setdefault(key, value)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: Path) -> Settings:
        """Load settings from ``path``; a missing or corrupt file yields defaults."""
        values: dict[str, Any] = {}
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.debug("no settings file at %s, using defaults", path)
        except OSError as exc:
            logger.warning("cannot read settings file %s: %s", path, exc)
        else:
            try:
                loaded = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError as exc:
                logger.warning("ignoring malformed settings file %s: %s", path, exc)
            else:
                if isinstance(loaded, dict):
                    values = loaded
                else:
                    logger.warning("ignoring settings file %s: not a JSON object", path)
        return cls(path, values)

    def save(self) -> bool:
        """Write the settings to disk with owner-only permissions.

        Returns:
            Whether the file was written.
        """
        data = json.dumps(self._values, indent=2, sort_keys=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(data)
            os.chmod(self.path, 0o600)  # tighten files created by older versions
        except OSError as exc:
            logger.error("failed to save settings to %s: %s", self.path, exc)
            return False
        logger.debug("written %d bytes to %s", len(data), self.path)
        return True

    # ------------------------------------------------------------------ #
    # Access
    # ------------------------------------------------------------------ #

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = 0) -> Any:
        """Return a setting, converting numeric strings to ``int``."""
        value = self._values.get(key, default)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return value

    def get_int(self, key: str, default: int) -> int:
        """Return a setting as an integer, falling back to ``default``."""
        value = self.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("setting %s=%r is not a number, using %d", key, value, default)
            return default

    def get_str(self, key: str, default: str | None = None) -> str | None:
        """Return a setting as a string, or ``default`` when unset or empty."""
        value = self._values.get(key)
        return str(value) if value not in (None, "") else default

    def update(self, changes: Mapping[str, Any]) -> None:
        """Apply changes; keys mapped to ``None`` are removed (reset to unset)."""
        for key, value in changes.items():
            if value is None:
                self._values.pop(key, None)
            else:
                self._values[key] = value

    @property
    def password(self) -> str | None:
        """The saved server password, if any."""
        return self.get_str(_PASSWORD_KEY)

    @password.setter
    def password(self, value: str | None) -> None:
        self.update({_PASSWORD_KEY: value})

    def server_address(self, host: str | None = None, port: int | None = None) -> tuple[str, int]:
        """Return the server's ``(host, port)``.

        Args:
            host: Overrides the ``api-server-host`` setting when given.
            port: Overrides the ``api-server-port`` setting when given.
        """
        return (
            host or self.get_str("api-server-host") or DEFAULT_SERVER_HOST,
            port or self.get_int("api-server-port", DEFAULT_SERVER_PORT),
        )

    def public_view(self) -> dict[str, Any]:
        """Return the settings with secrets masked, for display."""
        return {k: (_MASK if k == _PASSWORD_KEY else v) for k, v in sorted(self._values.items())}
