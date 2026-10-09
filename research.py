"""Nova research helpers (Stage 4A).

classify() decides whether a request needs LIVE web information.
Rule of thumb: a word like "current" or "today" alone is NOT enough
("current in a circuit", "how are you today"). It must be a freshness cue.
"""
import re

# Requests that other tools already handle: never web-search these.
_TOOL_COMMANDS = re.compile(
    r"^(?:open|launch)\s+(?!source\b)"                      # open chrome, launch notepad
    r"|^play\b"
    r"|^(?:what(?:'s|s| is)?|tell me|whats)\s+(?:the\s+)?(?:current\s+)?(?:time|date)"
    r"(?:\s+(?:is it|now|today|right now))?\s*[?.!]*$"      # what's the time / date
    r"|^what time is it\b(?!\s+in\b)"                       # "...in Tokyo" is a web question
    r"|\btoday'?s date\b"
    r"|\bwhat day is (?:it|today)\b"
    r"|\byoutube\b"                                         # handled by search_youtube
    r"|\b(?:in|on) (?:the |my )?browser\b",                 # explicit browser requests
    re.I,
)

# Signals that the answer depends on live information.
_WEB_HINTS = re.compile(
    r"\b(?:"
    r"latest|news|headlines|breaking|"
    r"right now|tonight|yesterday|currently|"
    r"this (?:week|month|year)|"
    r"today'?s (?:news|weather|headlines|market|markets|score|scores|price|prices|forecast)|"
    r"(?:news|weather|forecast|score|scores|price|prices|market|headlines)\b.{0,30}\btoday|"
    r"current (?:price|prices|weather|score|status|president|prime minister|ceo|champion|"
    r"version|rate|rates|temperature|news|trend|trends)|"
    r"recent (?:news|updates?|developments|events)|"
    r"(?:price|cost) of|(?:stock|share) price|stock market (?:today|now)|"
    r"weather|forecast|"
    r"who won|score of|(?:match|game) score|release date|released|"
    r"updates? (?:on|about)|what happened|"
    r"look up|look into|search for|research\w*|find out|"
    r"2025|2026|"
    r"time (?:is it )?in \w+|date in \w+"
    r")\b",
    re.I,
)


def classify(text: str) -> str:
    """Return 'tool', 'web', or 'unsure'."""
    t = " ".join(str(text or "").split())
    t = t.replace("\u2019", "'").replace("\u2018", "'")      # Whisper often outputs curly quotes
    if _TOOL_COMMANDS.search(t):
        return "tool"
    if _WEB_HINTS.search(t):
        return "web"
    return "unsure"


if __name__ == "__main__":
    tests = [
        "what's the latest news on Nvidia",
        "what time is it",
        "what is today's date",
        "open chrome",
        "weather in Bengaluru right now",
        "who won the match yesterday",
        "explain how a transformer works",
        "tell me a joke",
        "research electric cars for me",
        "what is current in a series circuit",
        "what time is it in Tokyo",
    ]
    for t in tests:
        print(f"{classify(t):6} <- {t}")