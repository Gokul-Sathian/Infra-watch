import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import run_agent_loop
from status import enforce_verified_up, validate_device_status
from tools import check_device_status_with_retries

INVENTORY = [
    {"name": "core-switch-1", "host": "192.168.1.1", "type": "switch"},
    {"name": "server-room-ap", "host": "192.168.1.5", "type": "access_point"},
    {"name": "nas-01", "host": "192.168.1.20", "type": "server"},
    # Always errors (simulated) — exercises the retry-then-give-up stop rule.
    {"name": "flaky-sensor", "host": "192.168.1.50", "type": "sensor"},
]

# Fixture/manually-defined network topology for now — NOT auto-discovered.
# Real topology discovery via SNMP/LLDP is planned as a later step (see
# ROADMAP.md). core-switch-1 is the hub; source_port is the port on the
# source device that the target device is plugged into.
CONNECTIONS = [
    {"source": "core-switch-1", "source_port": 1, "target": "server-room-ap"},
    {"source": "core-switch-1", "source_port": 2, "target": "nas-01"},
    {"source": "core-switch-1", "source_port": 3, "target": "flaky-sensor"},
]

CHECK_INTERVAL_SECONDS = 10
_SEVERITY_FOR_STATUS = {"up": "ok", "down": "critical", "unknown": "warning"}

_status_lock = threading.Lock()
_latest_status = []


def run_check_cycle(inventory=None):
    """One full sweep of the inventory via check_device_status, then stop
    — never loops back over a device a second time within the same cycle.

    inventory defaults to the module-level INVENTORY; callers (e.g. the
    eval harness) can pass a different device list through the same
    logic without duplicating it.

    Uses check_device_status_with_retries so a device whose check errors
    outright gets up to 3 attempts before the cycle gives up on it and
    moves to the next device, reporting "unknown" rather than guessing.

    Deliberately deterministic rather than routed through the agent loop:
    it runs every 10 seconds and must never let a model mistake (like the
    stray "none" severity value seen in Step 6) or hallucination put an
    unverified device on the dashboard as "up". enforce_verified_up is
    applied anyway, as the single canonical guardrail shared with the
    chat path, even though it's a no-op here by construction.
    """
    if inventory is None:
        inventory = INVENTORY

    results = []
    verified_status = {}
    for device in inventory:
        check = check_device_status_with_retries(device["host"])
        verified_status[device["host"]] = check["status"]
        results.append(
            {
                "name": device["name"],
                "host": device["host"],
                "status": check["status"],
                "latency_ms": check["latency_ms"],
                "last_checked": check["last_checked"],
                "severity": _SEVERITY_FOR_STATUS[check["status"]],
                "type": device.get("type", ""),
                # Simulated fixture data only, not real per-port telemetry
                # (that needs SNMP polling — planned later). See ROADMAP.md.
                "ports": check.get("ports", []),
            }
        )

    results = enforce_verified_up(results, verified_status)
    return [validate_device_status(r).to_dict() for r in results]


def _background_check_loop():
    global _latest_status
    while True:
        results = run_check_cycle()
        with _status_lock:
            _latest_status = results
        time.sleep(CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _latest_status
    with _status_lock:
        _latest_status = run_check_cycle()
    thread = threading.Thread(target=_background_check_loop, daemon=True)
    thread.start()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


@app.get("/status")
def get_status():
    with _status_lock:
        return _latest_status


@app.get("/topology")
def get_topology():
    """Fixture network topology plus each device's current status.

    Reuses _latest_status as-is (the same guardrailed, validated data
    /status serves) rather than recomputing anything — this endpoint adds
    no new status logic, only the manually-defined connections list.
    """
    with _status_lock:
        devices = _latest_status
    return {"connections": CONNECTIONS, "devices": devices}


@app.post("/ping/{host}")
def ping_device(host: str):
    """On-demand probe triggered by the drawer's PING button.

    Runs the exact same check_device_status_with_retries used by the
    background check cycle — a real check, not a simulated one — but
    does not write into _latest_status; the next scheduled cycle still
    owns that shared state, so this is a read-only-to-the-dashboard probe.
    """
    return check_device_status_with_retries(host)


class ChatRequest(BaseModel):
    message: str


# Single global chat session, in-memory only (per-process, lost on
# restart) — fine for one local user. A real multi-user deployment would
# key this dict by a session id from the request instead.
_chat_lock = threading.Lock()
_chat_history = []


@app.post("/chat")
def chat(request: ChatRequest):
    with _status_lock:
        current_status = _latest_status
    prompt = (
        "Current cached device status from the last check cycle:\n"
        f"{current_status}\n\n"
        f"User question: {request.message}"
    )
    with _chat_lock:
        reply, updated_history = run_agent_loop(prompt, history=_chat_history)
        _chat_history[:] = updated_history
    return {"reply": reply}
