"""Generation of policy-editor scripts from recommended acceleration policies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

#: Server spellings of network types mapped to the policy editor's spelling.
_NETWORK_NAMES = {"HSPA-Plus": "HSPA+", "Wifi": "WiFi"}

#: The smallest burst size (bytes) a generated strategy may use.
_MIN_BURST = 3000

#: Burst sizes are rounded up to this granularity (bytes), plus two steps of headroom.
_BURST_STEP = 100

#: Bandwidth caps are rounded to this many Mbps.
_BANDWIDTH_STEP_MBPS = 5

#: The two strategies of a policy differ by this many bytes of burst (an A/B split).
_BURST_SPREAD = 1000

_TEMPLATE = """
rm {name}
set {name} from cid {cid}
set {name} from geo {geo}
set {name} from network {network}
set {name} then strategies mb_{burst_a}_{bandwidth} server max-bandwidth-mbps {bandwidth}
set {name} then strategies mb_{burst_a}_{bandwidth} server max-burst {burst_a}
set {name} then strategies mb_{burst_a}_{bandwidth} weight 5
set {name} then strategies mb_{burst_b}_{bandwidth} server max-bandwidth-mbps {bandwidth}
set {name} then strategies mb_{burst_b}_{bandwidth} server max-burst {burst_b}
set {name} then strategies mb_{burst_b}_{bandwidth} weight 5
set {name} then on-match override
"""


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def burst_size(recommended: float) -> int:
    """Round a recommended max-burst (bytes) up to a safe, coarse value."""
    return int(max(_MIN_BURST, (round(recommended / _BURST_STEP) + 2) * _BURST_STEP))


def bandwidth_mbps(recommended_bps: float) -> int:
    """Convert a recommended bandwidth (bps) to a rounded cap in Mbps."""
    step_bps = _BANDWIDTH_STEP_MBPS * 1_000_000
    return _BANDWIDTH_STEP_MBPS * int(1 + round(recommended_bps / step_bps))


def render_policy_scripts(
    policies: Iterable[Mapping[str, Any]],
    base_scope: Mapping[str, str],
    match_fields: Sequence[str],
) -> list[str]:
    """Translate recommended policies into policy-editor commands.

    Each policy becomes a rule matching a customer/geo/network cohort that
    splits traffic evenly between two max-burst strategies, so the
    recommendation can be validated in production.

    Args:
        policies: Policies as returned by the server's best-policy endpoint,
            each with a ``scope`` mapping and ``max_burst``/``max_bandwidth``.
        base_scope: Equality conditions of the shell's current scope; the
            policy's own scope takes precedence over them.
        match_fields: Dimensions a rule may match on (e.g. cid, geo, network).

    Returns:
        One script per policy whose scope involves at least one match field.
    """
    base = {k: v for k, v in base_scope.items() if k in match_fields}
    scripts = []
    for policy in policies:
        policy_scope = {k: v for k, v in (policy.get("scope") or {}).items() if k in match_fields}
        if not policy_scope:
            continue
        where = {**base, **policy_scope}
        cid = where.get("cid", 0)
        geo = where.get("geo", "")
        network = _NETWORK_NAMES.get(str(where.get("network", "")), where.get("network", ""))
        burst = burst_size(_number(policy.get("max_burst")))
        scripts.append(
            _TEMPLATE.format(
                name=f"cid{cid}-{geo}-{network}",
                cid=cid,
                geo=geo,
                network=network,
                burst_a=burst,
                burst_b=burst + _BURST_SPREAD,
                bandwidth=bandwidth_mbps(_number(policy.get("max_bandwidth"))),
            )
        )
    return scripts
