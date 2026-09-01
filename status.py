"""Output contract for infra-watch device status reports.

Every check result the agent produces must conform to DeviceStatus and pass
validate_device_status before it reaches the dashboard or chat — so a
device that couldn't be verified can never surface as "up".
"""
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

Status = Literal["up", "down", "unknown"]
Severity = Literal["ok", "warning", "critical"]

VALID_STATUSES = ("up", "down", "unknown")
VALID_SEVERITIES = ("ok", "warning", "critical")
REQUIRED_FIELDS = ("name", "host", "status", "latency_ms", "last_checked", "severity")


@dataclass
class DeviceStatus:
    name: str
    host: str
    status: Status
    latency_ms: Optional[float]
    last_checked: str
    severity: Severity
    # Simulated fixture data only, not real per-port telemetry — real
    # per-port status requires SNMP polling (planned as a later step, see
    # ROADMAP.md). Optional: [] means no per-port data for this device.
    ports: list = field(default_factory=list)
    # From the inventory entry, e.g. "switch"/"access_point" — display only.
    type: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class InvalidDeviceStatus(ValueError):
    """Raised when a raw result fails the infra-watch output contract."""


def validate_device_status(result: dict) -> DeviceStatus:
    """Validate a raw dict against the DeviceStatus contract.

    Rejects (raises InvalidDeviceStatus) any result that is missing a
    required field, uses a status/severity value outside the fixed sets, or
    has a negative latency_ms. Never coerces a missing or invalid value into
    "up" or "ok" — the caller must treat a rejected result as unverified.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in result]
    if missing:
        raise InvalidDeviceStatus(f"missing field(s): {', '.join(missing)}")

    name, host, status, latency_ms, last_checked, severity = (
        result[f] for f in REQUIRED_FIELDS
    )

    if not isinstance(name, str) or not name:
        raise InvalidDeviceStatus(f"name must be a non-empty string, got {name!r}")

    if not isinstance(host, str) or not host:
        raise InvalidDeviceStatus(f"host must be a non-empty string, got {host!r}")

    if status not in VALID_STATUSES:
        raise InvalidDeviceStatus(f"invalid status: {status!r}, must be one of {VALID_STATUSES}")

    if severity not in VALID_SEVERITIES:
        raise InvalidDeviceStatus(f"invalid severity: {severity!r}, must be one of {VALID_SEVERITIES}")

    if latency_ms is not None:
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
            raise InvalidDeviceStatus(f"latency_ms must be numeric or null, got {latency_ms!r}")
        if latency_ms < 0:
            raise InvalidDeviceStatus(f"latency_ms must not be negative, got {latency_ms}")

    if not isinstance(last_checked, str) or not last_checked:
        raise InvalidDeviceStatus(f"last_checked must be a non-empty string, got {last_checked!r}")

    ports = result.get("ports", [])
    if not isinstance(ports, list):
        raise InvalidDeviceStatus(f"ports must be a list, got {ports!r}")
    for entry in ports:
        if not isinstance(entry, dict) or "port" not in entry or "status" not in entry:
            raise InvalidDeviceStatus(f"invalid port entry: {entry!r}, must be {{'port': ..., 'status': ...}}")
        if entry["status"] not in VALID_STATUSES:
            raise InvalidDeviceStatus(f"invalid port status: {entry['status']!r}, must be one of {VALID_STATUSES}")

    device_type = result.get("type", "")
    if not isinstance(device_type, str):
        raise InvalidDeviceStatus(f"type must be a string, got {device_type!r}")

    return DeviceStatus(
        name=name,
        host=host,
        status=status,
        latency_ms=latency_ms,
        last_checked=last_checked,
        severity=severity,
        ports=ports,
        type=device_type,
    )


def enforce_verified_up(reports: list, verified_status: dict) -> list:
    """Guardrail: force any "up" claim to "unknown" unless it's backed by
    a real check this cycle/turn.

    reports: proposed DeviceStatus-shaped dicts (from a check cycle or a
        model's structured answer) — not yet trusted.
    verified_status: {host: status} built only from actual
        check_device_status results gathered this cycle/turn — the ground
        truth. A host absent from this dict was never checked at all.

    A report is only left as "up" if verified_status confirms that exact
    host as "up". Everything else claiming "up" — an unchecked host, or
    one a real check reported down/unknown — is rewritten to "unknown"
    with severity recomputed. Does not mutate the input; a "down" or
    "unknown" claim always passes through unchanged (only "up" claims are
    ever downgraded, never upgraded).
    """
    corrected = []
    for report in reports:
        report = dict(report)
        if report.get("status") == "up" and verified_status.get(report.get("host")) != "up":
            report["status"] = "unknown"
            report["latency_ms"] = None
            report["severity"] = "warning"
            report["ports"] = []  # the whole claim was unverified; its port data goes with it
        corrected.append(report)
    return corrected
