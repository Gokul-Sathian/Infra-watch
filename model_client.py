"""Single choke point for every Gemini API call in infra-watch.

All other modules must call `call_model` instead of touching the
google-genai client directly, so model access, auth, and defaults
stay in one place.
"""
import os
from pathlib import Path

from google import genai

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


def call_model(system, messages, tools=None, model=DEFAULT_MODEL):
    """Run one Gemini generate_content call.

    system: system instruction string.
    messages: list of {"role": "user"|"model", "content": str} dicts.
    tools: optional list of function-calling tool definitions.
    model: model id, defaults to DEFAULT_MODEL.
    """
    contents = [
        {"role": m["role"], "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    config = {"system_instruction": system}
    if tools:
        config["tools"] = tools

    response = _get_client().models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return response.text
