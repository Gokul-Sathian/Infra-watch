# infra-watch

An agent that monitors the health and availability of network and
server-room devices, and reports status through a local 3D dashboard and
a chat box — no external channel, everything runs on your own machine.

It takes a device inventory (host/IP, type) and a check-cycle trigger,
and returns a structured per-device status report: `up` / `down` /
`unknown`, latency, last-checked time, and severity. It's built to never
report a device as `up` unless a real check actually confirmed it —
enforced in code, not just prompted for.

## Features

- **Real reachability checks** via ICMP ping (`ping3`), 2-second timeout,
  measured round-trip latency.
- **3D dashboard** (Three.js, no build step) — each device renders as a
  1U rack-switch chassis with a status LED (green/red/gray, pulsing on
  up, hard-blinking on down). Click a device for a detail panel.
- **Chat** — ask questions about current status in plain language,
  answered by a Gemini-backed agent that calls the same reachability
  check tool rather than guessing. Remembers the conversation so far
  (single local session).
- **Safety controls**, enforced in code:
  - A device can only appear `up` if a real check confirmed it this
    cycle/turn — never taken on the model's word alone.
  - A failing check retries up to 3 times before giving up and reporting
    `unknown`.
  - The chat loop caps tool calls at 5 per turn and force-stops with
    whatever it has confirmed, rather than looping indefinitely.
- **Tiny eval harness** (`eval_check_cycle.py`) covering 5 scenarios:
  all-up, one-down, all-unreachable, mixed, and a check that keeps
  erroring until it gives up.

## Project layout

```
main.py                    FastAPI app: GET /status, POST /chat, serves the dashboard
agent.py                   Agent loop: model -> tool call -> tool result -> model
model_client.py            Single wrapper around every Gemini API call
status.py                  DeviceStatus contract, validator, up-guardrail
prompts/system_prompt.py   The agent's system prompt
tools/check_device_status.py   Real (ping3) + fixture reachability check
static/index.html          The 3D dashboard + chat UI
eval_check_cycle.py        Check-cycle eval (5 scenarios, pass/fail + total)
ROADMAP.md                 Planned work and known gaps
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your real GEMINI_API_KEY
```

Edit `INVENTORY` in `main.py` to point at the devices you actually want
to monitor (host/IP, name, type).

## Running

```bash
python3 -m uvicorn main:app --reload
```

Then open `http://localhost:8000`.

By default this pings real devices. To test against fixed, deterministic
mock data instead (no real network access needed — useful for a first
look, or for offline development), set:

```bash
INFRA_WATCH_USE_FIXTURES=1 python3 -m uvicorn main:app --reload
```

## Testing

```bash
python3 eval_check_cycle.py
```

Runs the 5 built-in scenarios against the real check-cycle logic and
prints pass/fail per case plus a total.

## Current limitations

No auth on the dashboard/chat (fine on `localhost`, not once exposed
further), no persisted history (in-memory only, lost on restart), and
SNMP / other subnets / CCTV aren't integrated yet. See `ROADMAP.md` for
the full list and what's next.
