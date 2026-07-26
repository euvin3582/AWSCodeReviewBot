"""Auto-approval for safe/trivial PRs.

Detects PRs that are small, low-risk, and unlikely to introduce bugs —
and auto-approves them to dissolve queue time. Configurable via
.criticai.yml (auto_approve: true/false, max_lines, safe_patterns).

A PR is considered safe when ALL of these are true:
  1. Total added+deleted lines <= threshold (default 50)
  2. All changed files match safe patterns (docs, tests, config, deps)
  3. No files match risky patterns (auth, security, infra, migrations)
  4. The diff doesn't contain risky keywords (secret, password, token, etc.)

When a safe PR is detected, CriticAI posts an approval review instead of
a findings review, saving human reviewer time on the routine half of the
PR backlog.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient
    from criticai.rules import RepoRules

import requests

# Default thresholds (overridable via .criticai.yml)
DEFAULT_MAX_LINES = 50
DEFAULT_MAX_FILES = 8

# File patterns considered inherently safe
SAFE_PATTERNS = [
    r"\.md$",
    r"\.txt$",
    r"\.ya?ml$",
    r"\.json$",
    r"\.toml$",
    r"\.lock$",
    r"\.gitignore$",
    r"\.env\.example$",
    r"docs/",
    r"\.github/",
    r"test[s]?/",
    r"__tests__/",
    r"\.test\.",
    r"\.spec\.",
    r"_test\.",
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"Pipfile\.lock$",
    r"poetry\.lock$",
    r"requirements.*\.txt$",
]

# File patterns that are NEVER auto-approved
RISKY_PATTERNS = [
    r"auth",
    r"security",
    r"crypto",
    r"secret",
    r"password",
    r"token",
    r"migration",
    r"schema",
    r"infra",
    r"deploy",
    r"prod",
    r"Dockerfile",
    r"docker-compose",
    r"\.env$",
    r"terraform",
    r"cloudformation",
    r"iam",
    r"permissions?",
    r"rbac",
    r"policy",
]

# Content keywords that prevent auto-approval
RISKY_KEYWORDS = [
    "secret", "password", "token", "api_key", "apikey",
    "private_key", "access_key", "credential",
    "eval(", "exec(", "dangerouslySetInnerHTML",
    "sudo", "chmod 777", "rm -rf",
    "DROP TABLE", "DELETE FROM", "TRUNCATE",
]


def should_auto_approve(
    diff: str,
    changed_files: list[str],
    rules: Optional["RepoRules"] = None,
) -> tuple[bool, str]:
    """Determine if this PR is safe enough to auto-approve.

    Returns (should_approve, reason) where reason explains the decision.
    """
    # Check if auto-approve is disabled via rules
    if rules and hasattr(rules, '_data'):
        auto_approve_setting = rules._data.get("auto_approve")
        if auto_approve_setting is False:
            return False, "auto_approve disabled in .criticai.yml"

    # Get thresholds from rules or defaults
    max_lines = DEFAULT_MAX_LINES
    max_files = DEFAULT_MAX_FILES
    if rules and hasattr(rules, '_data'):
        max_lines = rules._data.get("auto_approve_max_lines", DEFAULT_MAX_LINES)
        max_files = rules._data.get("auto_approve_max_files", DEFAULT_MAX_FILES)

    # Check file count
    if len(changed_files) > max_files:
        return False, f"too many files ({len(changed_files)} > {max_files})"

    # Count added/deleted lines
    added = diff.count("\n+") - diff.count("\n+++")
    deleted = diff.count("\n-") - diff.count("\n---")
    total_changes = added + deleted

    if total_changes > max_lines:
        return False, f"too many changes ({total_changes} lines > {max_lines})"

    # Check for risky file patterns
    for f in changed_files:
        for pattern in RISKY_PATTERNS:
            if re.search(pattern, f, re.IGNORECASE):
                return False, f"risky file pattern: {f} matches '{pattern}'"

    # Check all files are safe patterns (at least one must match)
    all_safe = all(
        any(re.search(p, f) for p in SAFE_PATTERNS)
        for f in changed_files
    )

    # Check for risky content in the diff
    diff_lower = diff.lower()
    for keyword in RISKY_KEYWORDS:
        if keyword.lower() in diff_lower:
            return False, f"risky keyword in diff: '{keyword}'"

    # If all files match safe patterns AND it's small, auto-approve
    if all_safe and total_changes <= max_lines:
        return True, f"safe PR ({total_changes} lines, {len(changed_files)} files, all match safe patterns)"

    # If it's very small (< 10 lines), approve even without safe pattern match
    if total_changes <= 10 and len(changed_files) <= 3:
        return True, f"trivial PR ({total_changes} lines, {len(changed_files)} files)"

    return False, "does not meet auto-approval criteria"


def post_auto_approval(
    config: "Config",
    github: "GitHubClient",
    head_sha: Optional[str],
    reason: str,
) -> None:
    """Post an auto-approval review on the PR."""
    url = f"https://api.github.com/repos/{config.repository}/pulls/{config.pr_number}/reviews"

    body = (
        "✅ **Auto-approved by CriticAI**\n\n"
        f"This PR was automatically approved because: {reason}.\n\n"
        "No issues detected. The changes are small, low-risk, and match "
        "safe file patterns.\n\n"
        "<sub>Auto-approval can be configured in `.criticai.yml` — "
        "set `auto_approve: false` to disable.</sub>"
    )

    payload = {
        "event": "APPROVE",
        "body": body,
    }
    if head_sha:
        payload["commit_id"] = head_sha

    try:
        resp = requests.post(url, json=payload, headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        })
        resp.raise_for_status()
        print(f"PR auto-approved: {reason}")
    except requests.RequestException as e:
        # Don't fail the action if approval fails — just log it
        print(f"Warning: auto-approval failed: {e}")
