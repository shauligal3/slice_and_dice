"""Start-up options of the shell, usually taken from the command line."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShellOptions:
    """How the shell connects and where it starts.

    Attributes:
        host: Server host; overrides the ``api-server-host`` setting.
        port: Server port; overrides the ``api-server-port`` setting.
        cid: Customer id to open the session with.
        test_mode: Ask the server to serve its test fixture and start scoped
            to the fixture's customer.
        empty_stack: Start at the root scope instead of the last 24 hours.
        remember_password: Save the password to the settings file after the
            first successful login.
        debug: Print tracebacks of unexpected errors.
    """

    host: str | None = None
    port: int | None = None
    cid: str | None = None
    test_mode: bool = False
    empty_stack: bool = False
    remember_password: bool = True
    debug: bool = False
