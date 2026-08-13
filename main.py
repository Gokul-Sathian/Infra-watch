from agent import run_agent_loop

INVENTORY_PROMPT = """Here is today's device inventory. Run a check cycle and report status.

[
  {"name": "core-switch-1", "host": "192.168.1.1", "type": "switch"},
  {"name": "server-room-ap", "host": "192.168.1.5", "type": "access_point"},
  {"name": "nas-01", "host": "192.168.1.20", "type": "server"}
]
"""


def main():
    run_agent_loop(INVENTORY_PROMPT)


if __name__ == "__main__":
    main()
