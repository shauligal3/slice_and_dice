"""A background thread that pings the server so idle sessions stay alive."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class KeepAlive:
    """Run ``ping`` every ``interval`` seconds until :meth:`stop` is called.

    The server forgets the scopes of idle clients; pinging it periodically
    keeps the user's scope stack valid while they read results. The thread is
    a daemon, so it never prevents the process from exiting.

    Args:
        interval: Seconds between pings.
        ping: The callable to run; exceptions are logged and swallowed.
    """

    def __init__(self, interval: float, ping: Callable[[], object]) -> None:
        self.interval = interval
        self._ping = ping
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name="keepalive", daemon=True)

    def start(self) -> None:
        """Start pinging."""
        self._thread.start()

    def stop(self) -> None:
        """Stop pinging; returns immediately."""
        self._stopped.set()

    def _run(self) -> None:
        while not self._stopped.wait(self.interval):
            try:
                self._ping()
            except Exception:  # never let the background thread die silently
                logger.exception("keep-alive ping failed")
