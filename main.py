from model_client import call_model
from prompts.system_prompt import SYSTEM_PROMPT


def main():
    reply = call_model(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Are you online? Reply in one sentence."}],
    )
    print(reply)


if __name__ == "__main__":
    main()
