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

CHECK_INTERVAL_SECONDS = 10
_SEVERITY_FOR_STATUS = {"up": "ok", "down": "critical", "unknown": "warning"}

_status_lock = threading.Lock()
_latest_status = []


def run_check_cycle():
    """One full sweep of the inventory via check_device_status, then stop
    — never loops back over a device a second time within the same cycle.

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
    results = []
    verified_status = {}
    for device in INVENTORY:
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
