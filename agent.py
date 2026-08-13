"""infra-watch's agent loop: model -> tool call -> tool result -> model,
repeated until the model returns a normal (non-function-call) response.
"""
from model_client import call_model
from prompts.system_prompt import SYSTEM_PROMPT
from tools import TOOL_FUNCTIONS

MAX_TURNS = 10


def run_agent_loop(user_prompt, history=None, max_turns=MAX_TURNS):
    """Run the agent loop on one user prompt and return (answer, history).

    history: prior conversation as a list of Gemini Content entries (as
        returned by a previous call to this function). Pass it back in on
        the next call so a follow-up question can refer to earlier turns.
        Defaults to a fresh conversation.

    Prints a log line for each turn: any model reasoning text, each tool
    call the model requested, and that tool's result.
    """
    messages = list(history) if history else []
    messages.append({"role": "user", "parts": [{"text": user_prompt}]})

    for turn in range(1, max_turns + 1):
        response = call_model(system=SYSTEM_PROMPT, messages=messages)
        model_content = response.candidates[0].content
        messages.append(model_content)

        function_calls = []
        for part in model_content.parts:
            if part.text:
                print(f"[turn {turn}] model thought: {part.text.strip()}")
            if part.function_call:
                function_calls.append(part.function_call)

        if not function_calls:
            final_answer = response.text
            print(f"[turn {turn}] model final answer:\n{final_answer}")
            return final_answer, messages

        response_parts = []
        for call in function_calls:
            args = dict(call.args or {})
            print(f"[turn {turn}] tool called: {call.name}({args})")
            func = TOOL_FUNCTIONS.get(call.name)
            result = func(**args) if func else {"error": f"unknown tool {call.name}"}
            print(f"[turn {turn}] tool result: {result}")
            response_parts.append(
                {"function_response": {"name": call.name, "response": result}}
            )

        messages.append({"role": "user", "parts": response_parts})

    raise RuntimeError(f"agent loop did not converge after {max_turns} turns")
