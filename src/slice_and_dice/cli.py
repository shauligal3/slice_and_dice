"""Command-line entry point: ``slice-and-dice [options]``."""

from __future__ import annotations

import argparse
import atexit
import contextlib
import getpass
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from slice_and_dice import __version__
from slice_and_dice.api_client import ApiClient
from slice_and_dice.keepalive import KeepAlive
from slice_and_dice.scope_library import ScopeLibrary
from slice_and_dice.settings import Settings, default_config_dir
from slice_and_dice.shell import Shell
from slice_and_dice.shell_options import ShellOptions

logger = logging.getLogger("slice_and_dice")

#: Environment variable that supplies the password non-interactively.
PASSWORD_ENV = "SLICE_AND_DICE_PASSWORD"

SETTINGS_FILE = "settings.json"
SAVED_SCOPES_FILE = "saved_scopes.json"
HISTORY_FILE = "history"


class _MessageFormatter(logging.Formatter):
    """Plain messages for info, ``level: message`` for warnings and errors."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if record.levelno >= logging.WARNING:
            return f"{record.levelname.lower()}: {message}"
        return message


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the command-line options."""
    parser = argparse.ArgumentParser(
        prog="slice-and-dice",
        description="Interactively slice, dice and compare network performance data.",
        epilog=f"The password may also be given in ${PASSWORD_ENV}.",
    )
    parser.add_argument("--host", help="analytics server host (default: from settings)")
    parser.add_argument("--port", type=int, help="analytics server port (default: from settings)")
    parser.add_argument("--cid", help="customer id to start with")
    parser.add_argument(
        "--config-dir",
        type=Path,
        help="directory of settings, saved scopes and history (default: %(default)s)",
        default=default_config_dir(),
    )
    parser.add_argument("--test-mode", action="store_true", help="use the server's test data set")
    parser.add_argument(
        "--no-stack",
        action="store_true",
        help="start at the root scope instead of the last 24 hours",
    )
    parser.add_argument(
        "--no-save-password",
        action="store_true",
        help="do not save the password to the settings file",
    )
    parser.add_argument(
        "--keepalive",
        type=float,
        default=180,
        metavar="SECONDS",
        help="ping the server this often to keep the session alive; 0 disables (default: 180)",
    )
    parser.add_argument(
        "-c",
        "--command",
        action="append",
        metavar="COMMAND",
        help="run this command and exit (may be repeated); e.g. -c 'group_by network'",
    )
    parser.add_argument("--debug", action="store_true", help="verbose logging and tracebacks")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def configure_logging(debug: bool) -> logging.Handler:
    """Send the package's log messages to standard error.

    Returns:
        The installed handler, so that it can be removed again.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_MessageFormatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    return handler


def configure_readline(history_path: Path) -> None:
    """Enable tab completion and persistent history, where readline exists."""
    try:
        import readline  # noqa: PLC0415 - unavailable on some platforms (e.g. Windows)
    except ImportError:
        return
    # Let completion treat "not-null" or "a/b" as a single word.
    delimiters = readline.get_completer_delims().replace("-", "").replace("/", "")
    readline.set_completer_delims(delimiters)
    if "libedit" in (readline.__doc__ or ""):  # macOS ships libedit instead of GNU readline
        readline.parse_and_bind("bind ^I rl_complete")
    with contextlib.suppress(OSError):  # no history yet
        readline.read_history_file(history_path)
    readline.set_history_length(1000)

    def save_history() -> None:
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(history_path)
        except OSError:
            logger.debug("could not save the command history to %s", history_path)

    atexit.register(save_history)


def run_loop(shell: Shell) -> None:
    """Run the interactive loop; Ctrl-C abandons the current line, Ctrl-D exits."""
    while True:
        try:
            shell.cmdloop()
            return
        except KeyboardInterrupt:
            shell.out("^C")
            shell.intro = ""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the shell.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        The process exit status.
    """
    args = build_parser().parse_args(argv)
    handler = configure_logging(args.debug)
    try:
        return _run(args)
    finally:
        logger.removeHandler(handler)


def _run(args: argparse.Namespace) -> int:
    """Run the shell with parsed arguments."""
    config_dir: Path = args.config_dir
    settings = Settings.load(config_dir / SETTINGS_FILE)
    env_password = os.environ.get(PASSWORD_ENV)
    password = env_password or settings.password
    if not password:
        try:
            password = getpass.getpass("Password: ")
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 1

    options = ShellOptions(
        host=args.host,
        port=args.port,
        cid=args.cid,
        test_mode=args.test_mode,
        empty_stack=args.no_stack,
        remember_password=not (args.no_save_password or env_password),
        debug=args.debug,
    )
    client = ApiClient(*settings.server_address(args.host, args.port), password=password)
    shell = Shell(client, settings, ScopeLibrary(config_dir / SAVED_SCOPES_FILE), options=options)

    try:
        shell.start()
    except (ConnectionError, OSError) as exc:
        logger.error("%s", exc)
        return 1

    keepalive = KeepAlive(args.keepalive, shell.ping) if args.keepalive > 0 else None
    if keepalive is not None:
        keepalive.start()
    try:
        if args.command:
            for command in args.command:
                shell.onecmd(shell.precmd(command))
        else:
            configure_readline(config_dir / HISTORY_FILE)
            run_loop(shell)
    finally:
        if keepalive is not None:
            keepalive.stop()
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
