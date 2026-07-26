"""Inline review comment parsing and formatting.

Parses structured findings from the model's JSON output into GitHub
review comment objects, complete with suggestion blocks for one-click
apply.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class InlineFinding:
    """A single finding that should be posted as an inline review comment."""
    path: str
    line: int
    severity: str        # e.g. "🔴 Critical", "🟠 Major", "🟡 Minor", "🔵 Nit"
    category: str        # e.g. "Security", "Performance", "Correctness"
    message: str         # explanation of the issue
    suggestion: Optional[str] = None  # suggested replacement code (for suggestion block)
    start_line: Optional[int] = None  # for multi-line suggestions
    confidence: Optional[str] = None  # "high", "medium", "low" — for noise control

    def format_body(self) -> str:
        """Format this finding as a GitHub review comment body.

        If a suggestion is provided, wraps it in a GitHub suggestion block
        so the user can click 'Apply suggestion' to commit it directly.
        """
        parts = [f"**{self.severity}** *{self.category}*\n\n{self.message}"]

        if self.suggestion:
            parts.append(f"\n\n```suggestion\n{self.suggestion}\n```")

        return "\n".join(parts)


@dataclass
class ReviewOutput:
    """Complete model output: summary markdown + structured inline findings."""
    summary: str
    findings: list[InlineFinding] = field(default_factory=list)


def parse_model_output(raw_output: str) -> ReviewOutput:
    """Parse the model's response into summary + structured findings.

    The model is prompted to output:
    1. A markdown review (Summary, Walkthrough, etc.)
    2. A JSON block with structured findings for inline comments

    The JSON block is fenced with ```json ... ``` at the end of the response.
    If no JSON block is found, returns the full output as summary with no
    inline findings (graceful degradation).
    """
    # Look for a JSON code block at the end of the output
    json_match = re.search(
        r"```json\s*\n(\[.*?\])\s*\n```\s*$",
        raw_output,
        re.DOTALL,
    )

    if not json_match:
        # No structured findings — return everything as summary
        return ReviewOutput(summary=raw_output.strip())

    # Split: everything before the JSON block is the summary
    summary = raw_output[:json_match.start()].strip()
    json_str = json_match.group(1)

    try:
        findings_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Warning: could not parse inline findings JSON: {e}")
        return ReviewOutput(summary=raw_output.strip())

    findings: list[InlineFinding] = []
    for item in findings_data:
        if not isinstance(item, dict):
            continue
        # Validate required fields
        path = item.get("path", "").strip()
        line = item.get("line")
        if not path or not isinstance(line, int):
            continue

        findings.append(InlineFinding(
            path=path,
            line=line,
            severity=item.get("severity", "🔵 Nit"),
            category=item.get("category", "General"),
            message=item.get("message", ""),
            suggestion=item.get("suggestion"),
            start_line=item.get("start_line"),
            confidence=item.get("confidence", "high"),
        ))

    return ReviewOutput(summary=summary, findings=findings)


def filter_by_confidence(
    findings: list[InlineFinding],
    min_confidence: str = "medium",
) -> list[InlineFinding]:
    """Filter findings by confidence threshold (noise control).

    Confidence levels: high > medium > low
    - "high": only post findings the model is very confident about
    - "medium": post high + medium confidence (default, balanced)
    - "low": post everything (maximum noise)

    Severity always overrides: Critical and Major findings are NEVER
    filtered regardless of confidence level.
    """
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    threshold = confidence_rank.get(min_confidence.lower(), 2)

    kept: list[InlineFinding] = []
    for f in findings:
        # Critical and Major are never filtered
        if "Critical" in f.severity or "Major" in f.severity:
            kept.append(f)
            continue

        finding_confidence = confidence_rank.get(
            (f.confidence or "high").lower(), 2
        )
        if finding_confidence >= threshold:
            kept.append(f)

    filtered_count = len(findings) - len(kept)
    if filtered_count > 0:
        print(f"  Noise control: suppressed {filtered_count} low-confidence finding(s)")

    return kept
