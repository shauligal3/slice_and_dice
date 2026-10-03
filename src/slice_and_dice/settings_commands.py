"""Commands that change and persist the user's settings."""

from __future__ import annotations

from slice_and_dice.constants import BREAKDOWN_RENDER_SETTINGS, SERVER_SETTINGS
from slice_and_dice.grammars import settings_grammar
from slice_and_dice.shell_base import ShellBase


class SettingsCommands(ShellBase):
    """``set`` and ``save``."""

    def do_set(self, arg: str) -> None:
        """Change settings for this session; 'save' makes them permanent.

        Usage: set <setting> [<value>] [<setting> [<value>] ...]
        A setting given without a value is reset to its default.
        Example: set max-results 25 delimiter |
        'show settings' lists the current values.
        """
        params, error = settings_grammar().validate(arg)
        if error:
            raise ValueError(error)
        if not params:
            raise ValueError("usage: set <setting> [<value>]")
        if any(key in BREAKDOWN_RENDER_SETTINGS for key in params):
            self.breakdown_offset = 0
        self.settings.update(params)
        if any(key in SERVER_SETTINGS for key in params):
            self.client.set_address(
                *self.settings.server_address(self.options.host, self.options.port)
            )
        self.set_prompt()
        self.on_settings_changed()

    def complete_set(self, text: str, line: str, begidx: int, endidx: int) -> list[str]:
        """Complete setting names."""
        return settings_grammar().complete(line[:endidx])

    def do_save(self, arg: str) -> None:
        """Save the current settings to the settings file."""
        if self.settings.save():
            self.out(f"settings saved to {self.settings.path}")
        else:
            self.error(f"could not save the settings to {self.settings.path}")
