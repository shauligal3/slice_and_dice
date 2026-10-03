"""HTTP client for the analytics server's JSON API."""

from __future__ import annotations

import hashlib
import http.client
import json
import logging
import socket
import threading
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

JsonObject = dict[str, Any]


def auth_cookie(password: str, nonce: int) -> str:
    """Return the authentication cookie the server expects for ``nonce``.

    The server shares the password and checks ``sha256("<password>-<nonce>")``
    where the nonce is the client's current Unix time, so a captured cookie
    is only replayable for a short window and the password never travels in
    the clear. Both sides need reasonably synchronized clocks.
    """
    return hashlib.sha256(f"{password}-{nonce}".encode()).hexdigest()


class ApiClient:
    """A small, thread-safe client for the server's ``GET``-based JSON API.

    Each call is a ``GET /<endpoint>?<params>`` request answered with a JSON
    object. One HTTP connection is kept alive and reused; it is dropped and
    transparently re-opened after any network error.

    Args:
        host: Server host name.
        port: Server TCP port.
        password: Shared secret used to sign every request.
    """

    def __init__(self, host: str, port: int, password: str) -> None:
        self._host = host
        self._port = port
        self.password = password
        self.last_request = ""
        self._connection: http.client.HTTPConnection | None = None
        # The keep-alive timer calls the server from a background thread.
        self._lock = threading.Lock()

    @property
    def address(self) -> str:
        """``host:port`` of the server."""
        return f"{self._host}:{self._port}"

    def set_address(self, host: str, port: int) -> None:
        """Point the client at another server, closing the current connection."""
        if (host, port) != (self._host, self._port):
            self._host, self._port = host, port
            self.close()

    def close(self) -> None:
        """Close the open connection, if any."""
        with self._lock:
            self._close_unlocked()

    def build_query(self, params: Mapping[str, Any] | None = None) -> str:
        """Return the signed, URL-encoded query string for ``params``.

        ``None`` values are omitted.
        """
        signed = {k: v for k, v in (params or {}).items() if v is not None}
        nonce = int(time.time())
        signed["nonce"] = nonce
        signed["cookie"] = auth_cookie(self.password, nonce)
        return urlencode({k: str(v) for k, v in signed.items()}, quote_via=quote, safe="")

    def call(
        self,
        endpoint: str,
        params: Mapping[str, Any] | None = None,
        timeout: float = 30,
    ) -> JsonObject | None:
        """Call an API endpoint.

        Args:
            endpoint: Path of the endpoint, e.g. ``"/scope/narrow"``.
            params: Query parameters.
            timeout: Socket timeout in seconds.

        Returns:
            The decoded JSON object, or ``None`` when the request failed. The
            failure is logged, so callers only need to bail out.
        """
        uri = f"{endpoint}?{self.build_query(params)}"
        with self._lock:
            self.last_request = uri
            try:
                return self._request(uri, timeout)
            except (OSError, http.client.HTTPException) as exc:
                # OSError covers socket.timeout and refused connections.
                logger.error("request to %s%s failed: %r", self.address, endpoint, exc)
                self._close_unlocked()
                return None
            except KeyboardInterrupt:
                # The response may still be in flight; the connection is unusable.
                self._close_unlocked()
                raise

    # ------------------------------------------------------------------ #
    # Internals (called with the lock held)
    # ------------------------------------------------------------------ #

    def _request(self, uri: str, timeout: float) -> JsonObject | None:
        if self._connection is None:
            self._connection = http.client.HTTPConnection(self._host, self._port, timeout=timeout)
        self._connection.request("GET", uri)
        sock = self._connection.sock
        if isinstance(sock, socket.socket):
            sock.settimeout(timeout)
        response = self._connection.getresponse()
        body = response.read()
        if response.status >= 300:
            logger.error(
                "server answered %d %s: %s",
                response.status,
                response.reason,
                body[:200].decode("utf-8", "replace"),
            )
            return None
        try:
            decoded = json.loads(body)
        except ValueError as exc:
            logger.error("server sent a response that is not JSON: %s", exc)
            return None
        if not isinstance(decoded, dict):
            logger.error("server sent a JSON %s instead of an object", type(decoded).__name__)
            return None
        return decoded

    def _close_unlocked(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
