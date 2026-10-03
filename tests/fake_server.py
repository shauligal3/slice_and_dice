"""An in-process stand-in for the analytics server, used by the tests."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlsplit

Handler = Callable[[dict[str, str]], Any]

BREAKDOWN_ROWS = [
    {
        "network": "LTE",
        "scope_id": 101,
        "spd_gain": 12.5,
        "fbu_gain": 8.0,
        "dcu_gain": 10.0,
        "acc_ct": 900,
        "byp_ct": 100,
        "acc_spd": 2000.0,
        "byp_spd": 1700.0,
        "acc_fbu": 300.0,
        "byp_fbu": 330.0,
    },
    {
        "network": "WiFi",
        "scope_id": 102,
        "spd_gain": 3.0,
        "fbu_gain": 1.0,
        "dcu_gain": 2.0,
        "acc_ct": 450,
        "byp_ct": 50,
    },
    {
        "network": "3G",
        "scope_id": 103,
        "spd_gain": -1.0,
        "fbu_gain": -2.0,
        "dcu_gain": 0.5,
        "acc_ct": 90,
        "byp_ct": 10,
    },
]

SAMPLES = [
    {"ses": 1234567890, "speed": 1500, "size": 20000, "geo": "US", "fbu": 300, "dcu": 900},
    {"ses": 1234567891, "speed": 2500, "size": 40000, "geo": "US", "fbu": 200, "dcu": 600},
]

REPORT_DOCUMENT = {
    "name": "burst-by-network",
    "control-fields-no-agg": ["network"],
    "control-fields-agg": [{"size": [50000, 10000]}],
    "policy-fields": [{"max_burst": [6000, 3000]}],
    "outcome": ["median fbu"],
}


class FakeServer:
    """A threaded HTTP server answering like the analytics API.

    Every request is recorded in :attr:`requests` as ``(endpoint, params)``.
    Endpoints can be overridden per test through :attr:`handlers`.

    Args:
        password: The password clients must sign requests with.
    """

    def __init__(self, password: str = "secret") -> None:
        self.password = password
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.started = 1
        self._next_scope_id = 10
        self._lock = threading.Lock()
        self.handlers: dict[str, Handler] = {
            "/healthcheck": self._healthcheck,
            "/scope/narrow": self._narrow,
            "/scope/jump": self._narrow,
            "/scope/activity": self._activity,
            "/scope/breakdown": self._breakdown,
            "/scope/samples": self._samples,
            "/scope/track": lambda p: {"req_ct": 5000, "mau": 1200, "scope_id": p["scope_id"]},
            "/scope/cluster": lambda p: {
                "clusters": [{"limit": 1000, "spread": 10, "count": 7, "percentage share": 70}]
            },
            "/scope/show_reports": lambda p: {"reports": [REPORT_DOCUMENT]},
            "/scope/gen_report": lambda p: {"report": BREAKDOWN_ROWS},
            "/scope/best_policy": self._best_policy,
            "/scope/training_set": lambda p: {"data": BREAKDOWN_ROWS, "bad_rows": 0},
            "/server/info": lambda p: {"version": "test"},
        }
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )

    @property
    def port(self) -> int:
        """The TCP port the server listens on."""
        return int(self._httpd.server_address[1])

    def start(self) -> FakeServer:
        """Start serving in a background thread."""
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving."""
        self._httpd.shutdown()
        self._httpd.server_close()

    def endpoints(self) -> list[str]:
        """Return the endpoints called so far, in order."""
        return [endpoint for endpoint, _ in self.requests]

    def last(self, endpoint: str) -> dict[str, str]:
        """Return the parameters of the last call to ``endpoint``."""
        for called, params in reversed(self.requests):
            if called == endpoint:
                return params
        raise AssertionError(f"{endpoint} was never called; calls: {self.endpoints()}")

    # ------------------------------------------------------------------ #
    # Default endpoint behaviour
    # ------------------------------------------------------------------ #

    def _authorized(self, params: dict[str, str]) -> bool:
        expected = hashlib.sha256(f"{self.password}-{params.get('nonce')}".encode()).hexdigest()
        return params.get("cookie") == expected

    def _healthcheck(self, params: dict[str, str]) -> Any:
        if not self._authorized(params):
            return {"status": "unauthorized"}
        return {"status": "ok", "started": self.started}

    def _narrow(self, params: dict[str, str]) -> Any:
        with self._lock:
            self._next_scope_id += 1
            scope_id = self._next_scope_id
        return {"scope_id": scope_id, "count": 1000 * scope_id, "sql": "SELECT ..."}

    def _activity(self, params: dict[str, str]) -> Any:
        return {
            "histogram": [
                {"is_acc": 1, "scope_id": 501, "ses_ct": 40, "req_ct": 900, "speed": 2000},
                {"is_acc": 0, "scope_id": 502, "ses_ct": 5, "req_ct": 100, "speed": 1700},
            ]
        }

    def _breakdown(self, params: dict[str, str]) -> Any:
        start, limit = int(params["startfrom"]), int(params["limit"])
        rows = [dict(row) for row in BREAKDOWN_ROWS[start : start + limit]]
        return {"histogram": rows, "count": len(BREAKDOWN_ROWS), "sql": "SELECT network ..."}

    def _samples(self, params: dict[str, str]) -> Any:
        start, limit = int(params["startfrom"]), int(params["limit"])
        return {"samples": SAMPLES[start : start + limit]}

    def _best_policy(self, params: dict[str, str]) -> Any:
        return {
            "best-policies": [{"scope": {"network": "LTE"}, "max_burst": 6000}],
            "recommended-policies": [
                {"scope": {"network": "LTE"}, "max_burst": 5960, "max_bandwidth": 9_000_000}
            ],
            "no-gain-scopes": [],
            "not-tested-policies": [],
            "report": BREAKDOWN_ROWS,
            "db_time": 1.5,
            "total_time": 2.0,
        }

    # ------------------------------------------------------------------ #
    # HTTP plumbing
    # ------------------------------------------------------------------ #

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep-alive, like the real server
            disable_nagle_algorithm = True  # avoid delayed-ACK stalls between requests

            def do_GET(self) -> None:
                url = urlsplit(self.path)
                params = dict(parse_qsl(url.query, keep_blank_values=True))
                server.requests.append((url.path, params))
                handler = server.handlers.get(url.path, lambda p: {})
                answer = handler(params)
                status, payload = answer if isinstance(answer, tuple) else (200, answer)
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                """Keep test output quiet."""

        return RequestHandler
