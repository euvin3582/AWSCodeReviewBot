"""Sequence/architecture diagrams for the Walkthrough section.

Generates Mermaid sequence diagrams showing the call flow introduced
by the PR changes. GitHub renders Mermaid diagrams natively in markdown.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from criticai.config import Config

from criticai.providers.base import get_provider


def generate_diagram(config: "Config", diff: str) -> Optional[str]:
    """Generate a Mermaid sequence diagram from the PR diff.

    Asks the model to identify the key interactions/call flows in the
    changed code and produce a compact Mermaid diagram. Returns the
    fenced mermaid block, or None if the diff is too trivial.
    """
    # Don't generate diagrams for tiny diffs
    if diff.count("\n") < 15:
        return None

    prompt = (
        "Analyze this code diff and generate a Mermaid sequence diagram "
        "showing the key interactions or call flow introduced by the changes. "
        "Output ONLY a fenced mermaid code block, nothing else. Keep it "
        "compact (max 15 participants, max 20 interactions). If the changes "
        "are too simple for a meaningful diagram (e.g. just config changes, "
        "renames, or single-function edits), output exactly: SKIP\n\n"
        f"{diff[:6000]}"
    )
    system = "Output only a ```mermaid diagram or the word SKIP. Nothing else."

    try:
        provider = get_provider(config.model, config)
        result = provider.invoke(config.model, system, prompt).strip()

        if result.upper() == "SKIP" or "SKIP" in result[:10]:
            return None

        # Ensure it's properly fenced
        if "```mermaid" not in result:
            result = f"```mermaid\n{result}\n```"

        return result
    except Exception as e:
        print(f"Warning: diagram generation failed: {e}")
        return None
