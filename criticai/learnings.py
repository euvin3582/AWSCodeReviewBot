"""Knowledge base / team learnings.

Tracks findings that have been dismissed via @criticai ignore and avoids
re-flagging the same patterns. Uses a .criticai-learnings.json file stored
in the repo's default branch to persist learnings across PRs.

This is lightweight persistence without a database — the file is small
(just fingerprints of dismissed findings) and updated rarely (only when
someone explicitly dismisses a finding).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient


LEARNINGS_PATH = ".criticai-learnings.json"


def load_learnings(github: "GitHubClient", head_sha: Optional[str]) -> set[str]:
    """Load the set of dismissed finding fingerprints from the repo.

    Returns an empty set if the file doesn't exist or can't be read.
    """
    content = github.get_file_content(LEARNINGS_PATH, ref=head_sha)
    if not content:
        return set()

    try:
        data = json.loads(content)
        return set(data.get("dismissed", []))
    except (json.JSONDecodeError, TypeError):
        return set()


def fingerprint_finding(finding_text: str) -> str:
    """Generate a stable fingerprint for a finding.

    Normalizes whitespace and line numbers, then hashes — so the same
    conceptual finding on a slightly different line still matches.
    """
    # Strip line numbers, whitespace, and severity emojis for stable matching
    normalized = re.sub(r"line \d+", "line N", finding_text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"[🔴🟠🟡🔵]", "", normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def should_suppress(finding_text: str, dismissed: set[str]) -> bool:
    """Check if a finding should be suppressed based on team learnings."""
    return fingerprint_finding(finding_text) in dismissed


def build_suppression_prompt(dismissed: set[str]) -> str:
    """Build a prompt addition telling the model about suppressed patterns.

    We don't tell the model the specific fingerprints (meaningless to it),
    but we do tell it the count, so it knows some things have been dismissed.
    """
    if not dismissed:
        return ""

    return (
        f"NOTE: The team has previously dismissed {len(dismissed)} finding(s) "
        f"on this codebase. If you encounter patterns similar to previously "
        f"dismissed findings, consider whether they represent intentional "
        f"team decisions rather than bugs, and note them as 🔵 Nit at most "
        f"rather than higher severity.\n\n"
    )
