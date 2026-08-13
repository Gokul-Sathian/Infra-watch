# infra-watch roadmap

Where things stand and what's next, as of the current build (real ping3
checks, guardrail + stop-rule safety controls, FastAPI dashboard + chat,
tiny eval harness). Nothing below is implemented yet unless noted.

## Blocked on external access — not yet monitored

- **SNMP interface/port-level stats** — once SNMP is confirmed enabled on
  the real switch. Until then, port-level detail stays out of scope;
  `check_device_status` only reports whole-device reachability.
- **Other subnets / CCTV** — once network access to those segments
  exists. Honest status in the meantime: **not yet monitored**, not
  silently assumed fine.

## Buildable now, not yet built

- **Persistence (SQLite)** — currently `_latest_status` is an in-memory
  list, overwritten every cycle; nothing survives a restart or shows
  trends over time. Adding a checks table (timestamp, host, status,
  latency) is straightforward and needs no new external dependency.
- **Scheduling robustness** — `_background_check_loop` in `main.py`
  currently has no error handling around `run_check_cycle()`. Today an
  unexpected exception there (not a per-device check failure, which is
  already handled — an actual bug in the loop itself) would silently kill
  the daemon thread, and `/status` would just stop updating with no
  visible error. Worth wrapping the loop body in try/except + log, so one
  bad cycle can't take down all future ones.
- **Observability** — logging today is `print()` only: visible in the
  terminal, gone on restart. Every check run, tool call, and guardrail
  correction (the `[guardrail]`/`STOP RULE` lines already emitted) should
  land somewhere durable (a log file at minimum; the SQLite table above
  could double as this).
- **Broader evals** — `eval_check_cycle.py` covers 5 cases today (all-up,
  one-down, all-unreachable, mixed, one-times-out). Natural next cases:
  more devices per inventory, a flapping device (status changes between
  consecutive cycles), and partial outages (some ports/services down on
  an otherwise-up device — this one depends on the SNMP work above for
  real port-level signal).
- **Access control** — the dashboard and `/chat` currently have zero
  auth. Fine on `localhost` only; a real gap the moment this is reachable
  from anywhere else on the network. Worth a login (even HTTP basic
  auth) before this is ever exposed beyond your own PC.

## Deferred by design

- **Live push (WebSocket) instead of polling** — the dashboard polls
  `/status` every 5s. Not worth the added complexity unless that delay
  actually becomes a problem in practice.
- **Nicer visuals** — swap the procedural rack-switch boxes for a CC0
  rack shell (Kenney.nl / Quaternius) once the functional dashboard is
  solid. The port-light meshes stay procedural regardless, since those
  have to stay driven by live status data, not a static model.
- **Deployment to the Ubuntu VM** — move off your PC and run as a
  background service (e.g. systemd) near the server room, once stable.
  This has to happen on your actual machine/VM — not something buildable
  from this sandbox.
