"""ASCII timelines showing where the time of a single request went."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Minimum round-trip time assumed between the user and the proxy (ms).
_MIN_ACCESS_RTT = 50

#: Number of dashes the longest gap between two events is drawn with.
_ARROW_SCALE = 10


def _ms(sample: Mapping[str, Any], key: str) -> int:
    value = sample.get(key) or 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def event_times(sample: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Place the events of one request on a common time axis.

    Events are named ``<event><vantage point>``: ``co`` = connected,
    ``fb`` = first byte, ``dc`` = download complete, ``dns`` = name resolved;
    ``u`` = user device, ``h`` = acceleration proxy, ``o`` = origin server.
    Proxy- and origin-side timings are relative to the moment the proxy
    received the request, which is estimated from the user's download time
    and half the access round trip.

    Args:
        sample: One request log record.

    Returns:
        ``(event, milliseconds)`` pairs in chronological order.
    """
    dcu = _ms(sample, "dcu")
    dch = _ms(sample, "dch")
    rtt = max(_MIN_ACCESS_RTT, _ms(sample, "access_rtt"))
    proxy_start = dcu - dch + rtt // 2
    fbo = proxy_start + _ms(sample, "fbo")
    # (time, tie-breaker) so simultaneous events keep a causal order.
    events: dict[str, tuple[int, int]] = {
        "cou": (_ms(sample, "cou"), 0),
        "dcu": (dcu, 2),
        "coh": (proxy_start, 0),
        "dns": (proxy_start + _ms(sample, "dns"), 1),
        "coo": (proxy_start + _ms(sample, "coo"), 2),
        "fbo": (fbo, 3),
        "dco": (proxy_start + _ms(sample, "dco"), 4),
        "fbh": (proxy_start + _ms(sample, "fbh"), 0),
        "dch": (proxy_start + dch, 1),
        # The user cannot see a byte before the proxy got it from the origin.
        "fbu": (max(_ms(sample, "fbu"), fbo + 1), 1),
    }
    ordered = sorted(events.items(), key=lambda item: item[1])
    return [(name, moment) for name, (moment, _) in ordered]


def render_timeline(sample: Mapping[str, Any]) -> str:
    """Draw a request's events as arrows whose length is proportional to the gaps.

    Example output: ``" -->0 cou -->40 coh ---->160 dns ... ----------->950 dcu"``
    """
    events = event_times(sample)
    previous = 0
    largest_gap = 0
    for _, moment in events:
        largest_gap = max(largest_gap, moment - previous)
        previous = moment
    factor = max(1, largest_gap // _ARROW_SCALE)

    parts = []
    previous = 0
    for name, moment in events:
        gap = max(0, moment - previous)
        parts.append(f" {'-' * (gap // factor + 1)}>{moment} {name}")
        previous = moment
    return "".join(parts)
