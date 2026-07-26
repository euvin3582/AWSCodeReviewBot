"""Command parsing and dispatch for conversational interaction.

Users can reply to CriticAI's review comment (or any inline comment)
with @criticai commands. This module parses those commands and returns
structured actions for the handler to execute.

Supported commands:
    @criticai explain       - Deeper explanation of the finding in context
    @criticai explain <N>   - Explain finding number N specifically
    @criticai ignore        - Dismiss/acknowledge a finding (mark as intentional)
    @criticai fix           - Generate and push a fix commit for the finding
    @criticai fix-ci        - Analyze and fix CI failures
    @criticai review        - Re-run the full review on the current diff
    @criticai help          - Show available commands
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CommandType(Enum):
    EXPLAIN = "explain"
    IGNORE = "ignore"
    FIX = "fix"
    FIX_CI = "fix-ci"
    REVIEW = "review"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Command:
    """A parsed @criticai command."""
    type: CommandType
    argument: Optional[str] = None  # e.g. finding number, custom text
    raw_text: str = ""              # the full comment body for context


# Pattern: @criticai <command> [optional argument]
# Supports hyphenated commands like fix-ci
_COMMAND_PATTERN = re.compile(
    r"@criticai\s+([\w-]+)(?:\s+(.+))?",
    re.IGNORECASE,
)


def parse_command(comment_body: str) -> Optional[Command]:
    """Parse a @criticai command from a comment body.

    Returns None if the comment doesn't contain a @criticai mention.
    """
    match = _COMMAND_PATTERN.search(comment_body)
    if not match:
        return None

    cmd_str = match.group(1).lower()
    argument = match.group(2).strip() if match.group(2) else None

    cmd_type = {
        "explain": CommandType.EXPLAIN,
        "ignore": CommandType.IGNORE,
        "dismiss": CommandType.IGNORE,
        "fix": CommandType.FIX,
        "resolve": CommandType.FIX,
        "fix-ci": CommandType.FIX_CI,
        "fixci": CommandType.FIX_CI,
        "review": CommandType.REVIEW,
        "re-review": CommandType.REVIEW,
        "help": CommandType.HELP,
    }.get(cmd_str, CommandType.UNKNOWN)

    return Command(type=cmd_type, argument=argument, raw_text=comment_body)


HELP_TEXT = """\
**CriticAI Commands** — reply to any CriticAI comment with:

| Command | Description |
|---------|-------------|
| `@criticai explain` | Get a deeper explanation of this finding |
| `@criticai explain <N>` | Explain finding number N from the summary |
| `@criticai ignore` | Dismiss this finding (mark as intentional) |
| `@criticai fix` | Generate and push a fix commit for this finding |
| `@criticai fix-ci` | Analyze CI failures and suggest a fix |
| `@criticai review` | Re-run the full review on the current diff |
| `@criticai help` | Show this help message |

You can also reply with a plain question (mentioning `@criticai`) and \
the bot will respond conversationally.
"""
