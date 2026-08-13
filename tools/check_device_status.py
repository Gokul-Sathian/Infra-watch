"""check_device_status: infra-watch's one tool for verifying reachability.

Offline stub for now — returns fixed fixture data for a known set of test
hosts (up, down, and timed-out cases) so checks are deterministic and need
no real network access. A host outside the fixture set is unverifiable and
comes back "unknown", never guessed as "up".
"""
from datetime import datetime, timezone

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

MAX_RETRIES_PER_DEVICE = 3


def check_device_status(host: str) -> dict:
    """Run the check_device_status tool for one host.

    Returns {"host", "status", "latency_ms", "last_checked"}. Any host
    outside the fixture set is unverifiable and comes back "unknown".
    Raises if the check itself fails/errors (distinct from a completed
    check that legitimately reports "down" or "unknown") — callers that
    need to survive that should use check_device_status_with_retries.
    """
    if host in _ALWAYS_ERRORS:
        raise TimeoutError(f"simulated check timeout while probing {host}")

    fixture = _FIXTURE_RESULTS.get(host, {"status": "unknown", "latency_ms": None})
    return {
        "host": host,
        "status": fixture["status"],
        "latency_ms": fixture["latency_ms"],
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


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
