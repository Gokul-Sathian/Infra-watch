"""check_device_status: infra-watch's one tool for verifying reachability.

Real implementation by default: pings the host with ping3 and measures
round-trip latency. Set INFRA_WATCH_USE_FIXTURES=1 (or set the module-level
USE_FIXTURES flag directly) to fall back to fixed canned results for a
known set of test hosts, for offline development/testing without real
network access.
"""
import os
from datetime import datetime, timezone

from ping3 import ping

TOOL_SCHEMA = {
    "name": "check_device_status",
    "description": (
        "Checks whether a network or server-room device is currently "
        "reachable. Use this for every device before reporting its status "
        "— never assume a device is up without calling this."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "host": {
                "type": "string",
                "description": "The device's IP address or hostname to check.",
            },
        },
        "required": ["host"],
    },
}

PING_TIMEOUT_SECONDS = 2
MAX_RETRIES_PER_DEVICE = 3

# Set INFRA_WATCH_USE_FIXTURES=1 to force fixture mode at startup. Read as a
# plain module attribute (not re-read from the environment per call) so
# tests can also flip it directly: `check_device_status.USE_FIXTURES = True`.
USE_FIXTURES = os.environ.get("INFRA_WATCH_USE_FIXTURES", "").strip().lower() in ("1", "true", "yes")

# --- fixture (offline) implementation ---

# host -> simulated outcome. A "timing out" host has no latency and its
# reachability was never confirmed, so it resolves to "unknown" — not
# "down", which would imply a confirmed refusal/no-route instead of a
# check that simply couldn't complete.
_FIXTURE_RESULTS = {
    "192.168.1.1": {"status": "up", "latency_ms": 3.2},          # core-switch-1
    "192.168.1.5": {"status": "down", "latency_ms": None},       # server-room-ap
    "192.168.1.20": {"status": "unknown", "latency_ms": None},   # nas-01, times out
    "192.168.1.30": {"status": "up", "latency_ms": 11.7},
    "192.168.1.99": {"status": "down", "latency_ms": None},
}

# Hosts that simulate a check that keeps erroring outright (e.g. a crashed
# probe, not a legitimate down/unknown result) — used to exercise the
# retry-then-give-up stop rule.
_ALWAYS_ERRORS = {"192.168.1.50"}  # flaky-sensor


def _check_device_status_fixture(host: str) -> dict:
    if host in _ALWAYS_ERRORS:
        raise TimeoutError(f"simulated check timeout while probing {host}")

    fixture = _FIXTURE_RESULTS.get(host, {"status": "unknown", "latency_ms": None})
    return {
        "host": host,
        "status": fixture["status"],
        "latency_ms": fixture["latency_ms"],
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


# --- real implementation ---

def _check_device_status_real(host: str) -> dict:
    """Ping host for real with a 2-second timeout.

    ping3.ping returns a float delay on a reply (up), None on a plain
    timeout — no reply at all, which is ambiguous (packet loss? blocked
    ICMP? actually down?) so it's reported as "unknown" rather than
    guessed as "down" — or False on a definitive protocol-level error
    (e.g. an ICMP destination-unreachable reply), a real negative signal
    reported as "down". Any other exception (permission error, malformed
    host, etc.) propagates so check_device_status_with_retries can retry
    it before giving up.
    """
    result = ping(host, timeout=PING_TIMEOUT_SECONDS, unit="ms")
    now = datetime.now(timezone.utc).isoformat()

    if result is None:
        return {"host": host, "status": "unknown", "latency_ms": None, "last_checked": now}
    if result is False:
        return {"host": host, "status": "down", "latency_ms": None, "last_checked": now}
    return {"host": host, "status": "up", "latency_ms": round(result, 2), "last_checked": now}


def check_device_status(host: str) -> dict:
    """Run the check_device_status tool for one host.

    Returns {"host", "status", "latency_ms", "last_checked"}. Raises if
    the check itself fails/errors (distinct from a completed check that
    legitimately reports "down" or "unknown") — callers that need to
    survive that should use check_device_status_with_retries.
    """
    if USE_FIXTURES:
        return _check_device_status_fixture(host)
    return _check_device_status_real(host)


def check_device_status_with_retries(host: str, max_retries: int = MAX_RETRIES_PER_DEVICE) -> dict:
    """Retry check_device_status up to max_retries times if it errors.

    A check that keeps failing to even complete must never be reported as
    "up" or "down" — after exhausting retries this gives up and reports
    "unknown", the same as any other unverifiable device.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return check_device_status(host)
        except Exception as exc:
            print(f"check_device_status({host!r}) attempt {attempt}/{max_retries} raised: {exc}")

    print(f"check_device_status({host!r}) failed after {max_retries} attempts — reporting unknown")
    return {
        "host": host,
        "status": "unknown",
        "latency_ms": None,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
