"""Tool schemas and implementations available to the infra-watch agent."""
from tools.check_device_status import TOOL_SCHEMA as CHECK_DEVICE_STATUS_SCHEMA
from tools.check_device_status import check_device_status

# Gemini-format tools list, ready to pass straight into call_model(tools=...).
ALL_TOOLS = [{"function_declarations": [CHECK_DEVICE_STATUS_SCHEMA]}]

# name -> callable, for whatever executes tool calls once there's a loop.
TOOL_FUNCTIONS = {
    "check_device_status": check_device_status,
}
