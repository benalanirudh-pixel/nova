"""
Nova's brain: Ollama chat + tool calling.
"""

from __future__ import annotations

import re

import ollama

from tools import TOOL_SCHEMA, run_tool


MODEL = "qwen3.5:4b"

OPTIONS = {
    "num_ctx": 4096,
    "temperature": 0.3,
}

KEEP_ALIVE = "30m"

MAX_HISTORY = 20
MAX_TOOL_ROUNDS = 3


SYSTEM_PROMPT = (
    "You are Nova, a personal AI assistant for Ani. "

    "Speak naturally, clearly, and confidently, like a capable "
    "personal assistant. "

    "Reply in 1-2 short spoken sentences unless asked for detail. "

    "Plain text only: no markdown, no emojis, no lists. "

    "For current or factual information that can be obtained "
    "from an available tool, use the appropriate tool instead "
    "of guessing. "

    "For current time or date, always call get_time; never guess. "

    "For current market prices, indices, financial data, or "
    "other live market information, you MUST call the appropriate "
    "market-data tool before answering. "

    "For NIFTY 50 price, closing price, open, high, low, or "
    "today's market value, you MUST call get_market_data. "

    "Never answer a market-price question from memory. "

    "Never invent, estimate, or substitute a market number. "

    "Report market values returned by the tool exactly. "

    "If a tool fails or an app is unsupported, say so honestly."
)


history = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
]


class BrainError(Exception):
    """A problem the user can understand."""


def reset():
    """Reset conversation history while keeping the system prompt."""

    del history[1:]


def _clean(text) -> str:
    """Remove hidden reasoning tags before speaking."""

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text or "",
        flags=re.S,
    )

    return text.strip()


def _trim_history():
    """Keep conversation history within the configured limit."""

    body = history[1:]

    if len(body) <= MAX_HISTORY:
        return

    body = body[-MAX_HISTORY:]

    while body and body[0]["role"] != "user":
        body.pop(0)

    history[:] = [
        history[0]
    ] + body


def _chat(tools=None) -> dict:
    """Call Ollama and convert its response into a normal dict."""

    try:

        resp = ollama.chat(
            model=MODEL,
            messages=history,
            tools=tools,
            think=False,
            options=OPTIONS,
            keep_alive=KEEP_ALIVE,
        )

    except ConnectionError:

        raise BrainError(
            "I can't reach Ollama. "
            "Open the Ollama app or run 'ollama serve'."
        )

    except ollama.ResponseError as e:

        if e.status_code == 404:

            raise BrainError(
                f"Model '{MODEL}' is not installed. "
                f"Run: ollama pull {MODEL}"
            )

        raise BrainError(
            f"Ollama error: {e.error}"
        )

    return resp.message.model_dump(
        exclude_none=True
    )


def warmup():
    """Warm the model without affecting conversation history."""

    try:

        ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "hi",
                }
            ],
            think=False,
            options={
                **OPTIONS,
                "num_predict": 1,
            },
            keep_alive=KEEP_ALIVE,
        )

    except Exception:
        pass


def think(user_text: str) -> str:
    """
    Process one user request.

    Tool calling is handled in multiple rounds so Nova can:
    1. Decide whether a tool is needed.
    2. Execute the tool.
    3. Read the result.
    4. Produce the final spoken response.
    """

    _trim_history()

    start = len(history)

    history.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    last_result = ""

    try:

        for _ in range(MAX_TOOL_ROUNDS):

            msg = _chat(
                tools=TOOL_SCHEMA
            )

            history.append(msg)

            calls = msg.get("tool_calls") or []

            # No tool requested -> normal answer.
            if not calls:

                return (
                    _clean(
                        msg.get("content")
                    )
                    or last_result
                    or "Sorry, I didn't get a response."
                )

            # Execute every requested tool.
            for call in calls:

                fn = call["function"]

                tool_name = fn["name"]
                tool_args = fn.get("arguments")

                last_result = run_tool(
                    tool_name,
                    tool_args,
                )

                history.append(
                    {
                        "role": "tool",
                        "tool_name": tool_name,
                        "content": last_result,
                    }
                )

        # Final response after maximum tool rounds.
        msg = _chat(
            tools=None
        )

        history.append(msg)

        return (
            _clean(
                msg.get("content")
            )
            or last_result
            or "Done."
        )

    except BrainError:

        del history[start:]

        raise

    except Exception as e:

        del history[start:]

        raise BrainError(
            f"Unexpected error: {e}"
        )