"""infra-watch's agent loop: model -> tool call -> tool result -> model,
repeated until the model returns a normal (non-function-call) response.

Two safety controls live here, enforced in code rather than only in the
prompt:
1. Guardrail — a device can only end up "up" in the final answer if
   check_device_status actually confirmed it during this turn. Applied by
   _apply_up_guardrail before the answer is returned.
2. Stop rule — check_device_status may be called at most
   MAX_TOOL_CALLS_PER_TURN times in one turn. Once hit, further requested
   calls are not executed and the model is told to answer with what it
   has; if it asks for tools again anyway on the very next turn, the loop
   forces a final answer itself from whatever was actually verified,
   rather than trusting the model to comply or looping until MAX_TURNS.
"""
import json

from model_client import call_model
from prompts.system_prompt import SYSTEM_PROMPT
from status import enforce_verified_up
from tools import TOOL_FUNCTIONS

MAX_TURNS = 10
MAX_TOOL_CALLS_PER_TURN = 5


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

    verified_status = {}  # host -> status actually confirmed this turn
    tool_call_count = 0
    warned = False

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
            final_answer = _apply_up_guardrail(response.text, verified_status)
            print(f"[turn {turn}] model final answer:\n{final_answer}")
            return final_answer, messages

        if warned:
            # Already told it once (previous turn) to stop calling tools and
            # answer; it asked for more anyway. Enforce the stop in code —
            # don't call the model again, answer from what's actually
            # verified so far.
            final_answer = _apply_up_guardrail(_fallback_answer(verified_status), verified_status)
            print(
                f"[turn {turn}] STOP RULE: model kept requesting tool calls past the "
                f"{MAX_TOOL_CALLS_PER_TURN}-call limit — forcing final answer:\n{final_answer}"
            )
            return final_answer, messages

        response_parts = []
        for call in function_calls:
            args = dict(call.args or {})

            if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
                print(f"[turn {turn}] tool call SKIPPED (limit {MAX_TOOL_CALLS_PER_TURN}/turn reached): {call.name}({args})")
                result = {
                    "error": (
                        f"check_device_status call limit ({MAX_TOOL_CALLS_PER_TURN} per turn) "
                        "reached. Do not call it again — answer now with the results already gathered."
                    )
                }
            else:
                tool_call_count += 1
                print(f"[turn {turn}] tool called ({tool_call_count}/{MAX_TOOL_CALLS_PER_TURN}): {call.name}({args})")
                func = TOOL_FUNCTIONS.get(call.name)
                result = func(**args) if func else {"error": f"unknown tool {call.name}"}
                print(f"[turn {turn}] tool result: {result}")
                if call.name == "check_device_status" and "host" in args and "status" in result:
                    verified_status[args["host"]] = result["status"]

            response_parts.append(
                {"function_response": {"name": call.name, "response": result}}
            )

        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN and not warned:
            response_parts.append({
                "text": (
                    f"STOP RULE: {MAX_TOOL_CALLS_PER_TURN} check_device_status calls have "
                    "been used this turn. Do not call it again. Answer now using only the "
                    "results already gathered, and report any device you did not confirm "
                    "as \"unknown\"."
                )
            })
            warned = True

        messages.append({"role": "user", "parts": response_parts})

    raise RuntimeError(f"agent loop did not converge after {max_turns} turns")


def _fallback_answer(verified_status):
    """Last-resort answer when the model won't stop calling tools past the
    per-turn limit. Built only from what was actually verified, so it
    can't misreport a device that was never (successfully) checked.
    """
    if not verified_status:
        return (
            "I reached the check-call limit for this turn before confirming "
            "any device, so I don't have verified results to report."
        )
    lines = "\n".join(f"{host}: {status}" for host, status in verified_status.items())
    return "Reached the check-call limit for this turn. Verified before stopping:\n" + lines


def _apply_up_guardrail(answer_text, verified_status):
    """Never let an "up" claim through unless check_device_status actually
    confirmed it this turn — checked in code against the model's proposed
    result, not only via the prompt.

    Only structured answers (a JSON list of device dicts, the format a
    check-cycle reply uses) can be safely rewritten mechanically; plain
    chat prose is returned unchanged since there's no reliable way to
    mechanically correct a specific claim inside free text.
    """
    if answer_text is None:
        return answer_text
    try:
        parsed = json.loads(answer_text)
    except (json.JSONDecodeError, TypeError):
        return answer_text
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        return answer_text

    corrected = enforce_verified_up(parsed, verified_status)
    if corrected != parsed:
        print(f"[guardrail] forced unverified \"up\" claim(s) to \"unknown\": {parsed} -> {corrected}")
    return json.dumps(corrected, indent=2)
