
#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


BLOCKED_MULTI_CHAR_TOKENS = (
    "&&",
    "||",
    "|&",
    "|",
    ";",
    "$(",
    "`",
)


def _previous_char(command: str, index: int) -> str:
    return command[index - 1] if index > 0 else ""


def _next_char(command: str, index: int) -> str:
    return command[index + 1] if index + 1 < len(command) else ""


def find_compound_token(command: str) -> str | None:
    quote: str | None = None
    escaped = False
    i = 0

    while i < len(command):
        char = command[i]

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\":
            escaped = True
            i += 1
            continue

        if quote is not None:
            if char == quote:
                quote = None
            i += 1
            continue

        if char in ("'", '"'):
            quote = char
            i += 1
            continue

        if char in ("\n", "\r"):
            return "newline"

        for token in BLOCKED_MULTI_CHAR_TOKENS:
            if command.startswith(token, i):
                return token

        # Block background/call operator usage, but allow common redirections:
        #   2>&1
        #   1>&2
        if char == "&":
            previous_char = _previous_char(command, i)
            next_char = _next_char(command, i)

            if previous_char not in (">", "<") and next_char != "&":
                return "&"

        i += 1

    return None


def deny(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name")
    if tool_name not in {"Bash", "PowerShell"}:
        return 0

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")

    if not isinstance(command, str) or not command.strip():
        return 0

    token = find_compound_token(command)

    if token is None:
        return 0

    return deny(
        "Command rejected by project policy. "
        f"Detected compound shell token: {token!r}. "
        "Run exactly one command per tool call. "
        "Do not use &&, ||, ;, pipes, background operators, command substitution, or multiline commands."
    )


if __name__ == "__main__":
    raise SystemExit(main())

