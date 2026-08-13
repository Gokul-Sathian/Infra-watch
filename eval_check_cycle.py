"""Tiny eval for infra-watch's check-cycle logic.

Five example inventories with known expected outcomes, run through the
real run_check_cycle (retries + guardrail + Step 2's validate_device_status,
all reused as-is — nothing here reimplements that logic). Forces fixture
mode so results are deterministic and need no real network access.

Run: python3 eval_check_cycle.py
"""
import tools.check_device_status as check_device_status_module

check_device_status_module.USE_FIXTURES = True

from main import run_check_cycle  # noqa: E402  (import after forcing fixtures)
from status import InvalidDeviceStatus, validate_device_status  # noqa: E402

CASES = [
    {
        "name": "all-up",
        "inventory": [
            {"name": "switch-a", "host": "192.168.1.1", "type": "switch"},
            {"name": "switch-b", "host": "192.168.1.30", "type": "switch"},
        ],
        "expected": {
            "192.168.1.1": "up",
            "192.168.1.30": "up",
        },
    },
    {
        "name": "one-down",
        "inventory": [
            {"name": "switch-a", "host": "192.168.1.1", "type": "switch"},
            {"name": "ap-b", "host": "192.168.1.5", "type": "access_point"},
            {"name": "switch-c", "host": "192.168.1.30", "type": "switch"},
        ],
        "expected": {
            "192.168.1.1": "up",
            "192.168.1.5": "down",
            "192.168.1.30": "up",
        },
    },
    {
        "name": "all-unreachable",
        "inventory": [
            {"name": "ap-a", "host": "192.168.1.5", "type": "access_point"},
            {"name": "ap-b", "host": "192.168.1.99", "type": "access_point"},
        ],
        "expected": {
            "192.168.1.5": "down",
            "192.168.1.99": "down",
        },
    },
    {
        "name": "mixed",
        "inventory": [
            {"name": "switch-a", "host": "192.168.1.1", "type": "switch"},
            {"name": "ap-b", "host": "192.168.1.5", "type": "access_point"},
            {"name": "nas-c", "host": "192.168.1.20", "type": "server"},
        ],
        "expected": {
            "192.168.1.1": "up",
            "192.168.1.5": "down",
            "192.168.1.20": "unknown",
        },
    },
    {
        "name": "one-times-out",
        "inventory": [
            {"name": "switch-a", "host": "192.168.1.1", "type": "switch"},
            {"name": "flaky-sensor", "host": "192.168.1.50", "type": "sensor"},
        ],
        "expected": {
            "192.168.1.1": "up",
            "192.168.1.50": "unknown",  # errors on every attempt; retries exhaust to unknown
        },
    },
]


def run_case(case):
    reports = run_check_cycle(inventory=case["inventory"])
    by_host = {r["host"]: r for r in reports}
    problems = []

    for host, expected_status in case["expected"].items():
        report = by_host.get(host)
        if report is None:
            problems.append(f"{host}: missing from report")
            continue

        # Reuse the Step 2 validator explicitly, even though run_check_cycle
        # already validates internally — a case only passes if the report
        # is schema-valid AND matches the expected status.
        try:
            validate_device_status(report)
        except InvalidDeviceStatus as exc:
            problems.append(f"{host}: failed schema validation: {exc}")
            continue

        if report["status"] != expected_status:
            problems.append(f"{host}: expected {expected_status!r}, got {report['status']!r}")

    return problems, reports


def main():
    total = len(CASES)
    passed = 0

    for case in CASES:
        problems, reports = run_case(case)
        status_line = ", ".join(f"{r['name']}={r['status']}" for r in reports)
        if problems:
            print(f"FAIL  {case['name']:<16} [{status_line}]")
            for problem in problems:
                print(f"        - {problem}")
        else:
            print(f"PASS  {case['name']:<16} [{status_line}]")
            passed += 1

    print(f"\n{passed}/{total} cases passed")
    return passed == total


if __name__ == "__main__":
    import sys

    sys.exit(0 if main() else 1)
