"""Static vocabulary of the shell: dimensions, operators, aggregates and settings.

The analytics server exposes request logs as a wide table. Every column the
shell knows about is a *dimension*; a subset of them are numeric and can be
bucketed with breakpoints or aggregated (``median speed``, ``perc95 fbu``).

Metric naming follows a ``<event><vantage point>`` convention, e.g. ``fbu`` is
*first byte* as seen by the *user* and ``dco`` is *download complete* as seen
at the *origin*; see the README for the full glossary.
"""

from __future__ import annotations

from typing import Final

#: Every column the shell can filter on, group by or display.
ALL_DIMENSIONS: Final[tuple[str, ...]] = (
    # identity & request properties
    "cid", "geo", "dns_geo", "url_domain", "network", "size", "datetime",
    "speed", "dcu", "fbu", "fbp", "sampling", "app_version",
    "carrier", "device", "os", "region", "class", "event_name", "sdk_version",
    "city", "timezone", "content_type", "access_ip", "access_ip_16", "access_ip_24",
    "origin_ip", "ses",
    "exception", "status_code", "fbo", "dco", "url_schema",
    "persistent", "dns", "cou", "coo", "fbh", "dch", "app", "app_guid_int", "org_id",
    "cpu", "csu",
    # transport-level measurements
    "access_rtt", "origin_rtt", "retx_bytes", "rto_count", "pulsar",
    "retx_bytes_false", "retx_fast", "org_cached", "warm_ct", "btl_warm_ct",
    # acceleration policy knobs
    "max_bandwidth", "max_burst", "upgraded_burst", "url_param", "kickstart",
    "http_client", "retx_timeout", "hops", "median_pulse", "median2x_pulses", "ott_pulses",
    # time buckets & misc
    "hour", "day", "date", "week", "minute", "parent_content_type", "model", "penalty",
    "max_https_pool",
    "access_network", "asn", "method", "sf_datacenter", "sf_region",
)  # fmt: skip

#: Dimensions holding numbers: they accept numeric breakpoints and aggregates.
NUMERIC_DIMENSIONS: Final[tuple[str, ...]] = (
    "speed", "fbo", "fbu", "fbh", "dco", "dch", "dcu", "coo", "cou", "dns", "fbp", "cpu",
    "size", "retx_bytes", "retx_bytes_false", "rto_count", "access_rtt",
    "origin_rtt", "persistent", "org_cached", "hops", "median_pulse", "median2x_pulses",
    "ott_pulses",
    "max_burst", "upgraded_burst", "max_bandwidth", "warm_ct", "btl_warm_ct", "retx_timeout",
    "hour", "day", "minute", "penalty", "csu", "max_https_pool",
)  # fmt: skip

#: Columns the server computes per breakdown row (counts and per-class medians).
CALCULATED_COLUMNS: Final[tuple[str, ...]] = (
    "total_ct", "acc_ct", "byp_ct", "byp_fbu", "byp_dcu",
    "byp_spd", "acc_fbu", "acc_dcu", "acc_spd", "ace_ct", "bye_ct",
)  # fmt: skip

#: Dimensions whose breakpoints are dates (``date``) or timestamps (``datetime``).
DATE_DIMENSIONS: Final[tuple[str, ...]] = ("datetime", "date")

#: Comparison operators accepted by ``in <dimension> <op> <value>``.
OPERATORS: Final[tuple[str, ...]] = (
    "gt", "lt", "eq", "not", "like", "not-like", "is-null", "not-null", "gte", "lte",
)  # fmt: skip

#: Operators that take no value.
UNARY_OPERATORS: Final[tuple[str, ...]] = ("is-null", "not-null")

#: Symbolic shorthands for :data:`OPERATORS`.
OPERATOR_SYMBOLS: Final[dict[str, str]] = {
    ">": "gt",
    "<": "lt",
    "=": "eq",
    "!=": "not",
    "~": "like",
    ">=": "gte",
    "<=": "lte",
}

#: Aggregate functions usable in ``select`` / ``order_by`` (``median fbu``).
AGGREGATES: Final[tuple[str, ...]] = (
    "count", "avg", "median", "min", "max", "sum", "perc05", "perc25", "perc75", "perc95",
)  # fmt: skip

#: Characters that mark a parameter value as an arithmetic expression.
EXPRESSION_CHARS: Final[tuple[str, ...]] = ("+", "-", "*", "/", "(", ")")

#: Every key accepted by the ``set`` command.
SETTINGS: Final[tuple[str, ...]] = (
    "max-prompt", "max-results", "use-median", "auto-fetch", "max-report-line",
    "api-server-host", "api-server-port", "abbreviate-numbers",
    "timeout", "delimiter", "table-delimiter", "table-delimiter-replace", "gain-as-msec",
    "cluster-limit", "key-width", "policy-from",
    "disabled-columns", "min-total-samples", "min-acc-samples", "min-byp-samples",
)  # fmt: skip

#: Settings that change how breakdowns are rendered; changing one restarts paging.
BREAKDOWN_RENDER_SETTINGS: Final[tuple[str, ...]] = (
    "use-median", "delimiter", "table-delimiter", "gain-as-msec", "abbreviate-numbers",
    "key-width",
)  # fmt: skip

#: Settings that point at the server; changing one drops the open connection.
SERVER_SETTINGS: Final[tuple[str, ...]] = ("api-server-host", "api-server-port")

#: Default values applied when a setting is missing from the configuration file.
DEFAULT_SETTINGS: Final[dict[str, object]] = {
    "use-median": 1,
    "max-report-line": 100,
    "max-prompt": 80,
    "abbreviate-numbers": 1,
    "cluster-limit": 10000,
}

#: Topics accepted by the ``show`` command.
SHOW_TOPICS: Final[tuple[str, ...]] = (
    "stack", "scope", "sql", "settings", "rest", "selected", "iter", "server",
)  # fmt: skip

#: Traffic classes produced by the server: accelerated vs. bypassed (control).
TRAFFIC_CLASSES: Final[tuple[str, ...]] = ("acc", "byp")

DEFAULT_SERVER_HOST: Final = "localhost"
DEFAULT_SERVER_PORT: Final = 8080

#: Customer the server's test fixture is loaded under (``--test-mode``).
TEST_MODE_CID: Final = "3533"

#: How far back the initial scope reaches when the shell starts.
INITIAL_SCOPE_HOURS: Final = 24
