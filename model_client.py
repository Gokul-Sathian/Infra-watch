"""Single choke point for every Gemini API call in infra-watch.

All other modules must call `call_model` instead of touching the
google-genai client directly, so model access, auth, and defaults
stay in one place.
"""
import os
from pathlib import Path

from google import genai

from tools import ALL_TOOLS

DEFAULT_MODEL = "gemini-flash-latest"

_ENV_PATH = Path(__file__).resolve().parent / ".env"
_client = None


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(_ENV_PATH)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def call_model(system, messages, tools=ALL_TOOLS, model=DEFAULT_MODEL):
    """Run one Gemini generate_content call and return the raw response.

    system: system instruction string.
    messages: list of Gemini Content entries, e.g.
        {"role": "user", "parts": [{"text": "..."}]},
        {"role": "user", "parts": [{"function_response": {...}}]}, or a
        previous response's `candidate.content` passed straight through
        (its role is already "model"). Callers own the conversation
        history so multi-turn tool calling can be layered on top.
    tools: function-calling tool definitions, registered by default so
        every call has access to check_device_status. Pass None/[] to
        call without tools.
    model: model id, defaults to DEFAULT_MODEL.

    Returns the full GenerateContentResponse — inspect
    `response.candidates[0].content.parts` for function_call parts, or
    `response.text` when the model answered directly.
    """
    config = {"system_instruction": system}
    if tools:
        config["tools"] = tools

    return _get_client().models.generate_content(
        model=model,
        contents=messages,
        config=config,
    )
