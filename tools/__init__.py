"""Tool schemas and implementations available to the infra-watch agent."""
from tools.check_device_status import TOOL_SCHEMA as CHECK_DEVICE_STATUS_SCHEMA
from tools.check_device_status import check_device_status_with_retries

# Deliberately not re-exporting the bare `check_device_status` function
# here: a name in this package matching the submodule's own name
# (`tools.check_device_status`) would shadow the submodule attribute,
# breaking `import tools.check_device_status` for anyone reaching in to
# flip its USE_FIXTURES flag for offline testing.

# Gemini-format tools list, ready to pass straight into call_model(tools=...).
ALL_TOOLS = [{"function_declarations": [CHECK_DEVICE_STATUS_SCHEMA]}]

# name -> callable, for whatever executes tool calls once there's a loop.
# The retry-wrapped version is used here so a check that merely errors
# (as opposed to legitimately completing with "down"/"unknown") can't
# ever bubble up as an uncaught exception and crash the caller.
TOOL_FUNCTIONS = {
    "check_device_status": check_device_status_with_retries,
}
