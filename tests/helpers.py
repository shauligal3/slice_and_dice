"""Helpers to drive a shell in tests."""

from __future__ import annotations

import io

from slice_and_dice.shell import Shell


def output(shell: Shell) -> str:
    """Return and clear what the shell printed."""
    stream = shell.stdout
    assert isinstance(stream, io.StringIO)
    text = stream.getvalue()
    stream.seek(0)
    stream.truncate()
    return text


def run(shell: Shell, *commands: str) -> str:
    """Run commands the way the interactive loop does and return their output."""
    output(shell)
    for command in commands:
        shell.onecmd(shell.precmd(command))
    return output(shell)
