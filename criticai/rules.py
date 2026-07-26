"""Custom rules per repository (.criticai.yml).

Reads a .criticai.yml file from the repo root (if it exists) and injects
team-specific coding standards, focus areas, and ignore patterns into the
review prompt. This lets teams customize what CriticAI cares about without
modifying the action configuration.

Example .criticai.yml:
```yaml
# Focus the review on these areas
focus:
  - security
  - error handling
  - TypeScript strict mode compliance

# Custom rules the reviewer should enforce
rules:
  - "All async functions must have try/catch error handling"
  - "Never use 'any' type in TypeScript — use 'unknown' if unsure"
  - "API responses must be validated with zod schemas"

# Files/patterns to skip (never review these)
ignore:
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "generated/**"
  - "*.lock"

# Severity threshold — only report findings at this level or above
# Options: critical, major, minor, nit
min_severity: minor

# Language for review output (overrides action input)
# language: Spanish
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import fnmatch

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient


def load_rules(github: "GitHubClient", config: "Config", head_sha: Optional[str]) -> Optional["RepoRules"]:
    """Load .criticai.yml from the repository. Returns None if not found."""
    content = github.get_file_content(".criticai.yml", ref=head_sha)
    if not content:
        # Try alternate name
        content = github.get_file_content(".criticai.yaml", ref=head_sha)
    if not content:
        return None

    try:
        import yaml
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return None
        return RepoRules(data)
    except ImportError:
        # PyYAML not installed — parse minimally
        return _parse_minimal(content)
    except Exception as e:
        print(f"Warning: could not parse .criticai.yml: {e}")
        return None


class RepoRules:
    """Parsed repository-level review rules."""

    def __init__(self, data: dict) -> None:
        self.focus: list[str] = data.get("focus", [])
        self.rules: list[str] = data.get("rules", [])
        self.ignore: list[str] = data.get("ignore", [])
        self.min_severity: str = data.get("min_severity", "nit")
        self.language: Optional[str] = data.get("language")

    def should_ignore_file(self, path: str) -> bool:
        """Check if a file should be skipped based on ignore patterns."""
        for pattern in self.ignore:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def build_prompt_addition(self) -> str:
        """Build additional prompt text from the rules configuration."""
        parts: list[str] = []

        if self.focus:
            parts.append(
                "FOCUS AREAS (prioritize findings in these categories):\n"
                + "\n".join(f"  - {f}" for f in self.focus)
            )

        if self.rules:
            parts.append(
                "CUSTOM RULES (enforce these team standards):\n"
                + "\n".join(f"  - {r}" for r in self.rules)
            )

        severity_map = {"critical": 1, "major": 2, "minor": 3, "nit": 4}
        sev_level = severity_map.get(self.min_severity.lower(), 4)
        if sev_level < 4:
            threshold_name = self.min_severity.capitalize()
            parts.append(
                f"SEVERITY THRESHOLD: Only report findings at {threshold_name} "
                f"level or above. Ignore Nit-level issues."
            )

        if not parts:
            return ""

        return "\n\n".join(parts) + "\n\n"


def _parse_minimal(content: str) -> Optional[RepoRules]:
    """Minimal YAML-like parser for when PyYAML isn't available.

    Only handles flat lists under known keys. Good enough for the common
    case without adding a dependency.
    """
    import re
    data: dict = {}

    # Extract list items under known keys
    for key in ("focus", "rules", "ignore"):
        pattern = rf"^{key}:\s*\n((?:\s+-\s+.+\n?)+)"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            items = re.findall(r"^\s+-\s+[\"']?(.+?)[\"']?\s*$", match.group(1), re.MULTILINE)
            data[key] = items

    # Extract scalar values
    for key in ("min_severity", "language"):
        match = re.search(rf"^{key}:\s*(.+?)\s*$", content, re.MULTILINE)
        if match:
            data[key] = match.group(1).strip("\"'")

    if not data:
        return None
    return RepoRules(data)
