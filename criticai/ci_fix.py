"""Fix CI failures.

When CI fails on a PR, analyze the failure logs and either suggest a fix
or push one directly. Triggered via @criticai fix-ci command.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import requests

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient
    from criticai.providers.base import ModelProvider


def analyze_ci_failure(
    config: "Config",
    github: "GitHubClient",
) -> Optional[str]:
    """Fetch the latest failed CI run logs and analyze the failure.

    Returns a markdown analysis of what failed and how to fix it,
    or None if no failed runs are found.
    """
    # Get check runs for the PR's head SHA
    head_sha = github.get_pr_head_sha()
    if not head_sha:
        return None

    url = f"https://api.github.com/repos/{config.repository}/commits/{head_sha}/check-runs"
    resp = requests.get(url, headers={
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    })
    if resp.status_code != 200:
        return None

    check_runs = resp.json().get("check_runs", [])
    failed_runs = [
        r for r in check_runs
        if r.get("conclusion") == "failure"
        and r.get("name", "").lower() not in ("criticai", "criticai code review")
    ]

    if not failed_runs:
        return "No failed CI checks found on the current commit."

    # Fetch logs for the first failed run
    failed_run = failed_runs[0]
    run_name = failed_run.get("name", "Unknown")
    output = failed_run.get("output", {})
    summary = output.get("summary", "")
    text = output.get("text", "")
    annotations = output.get("annotations", []) if output else []

    # Build failure context
    failure_context = f"Failed check: {run_name}\n"
    if summary:
        failure_context += f"Summary: {summary[:2000]}\n"
    if text:
        failure_context += f"Details: {text[:3000]}\n"
    if annotations:
        failure_context += "Annotations:\n"
        for ann in annotations[:5]:
            failure_context += (
                f"  - {ann.get('path', '')}:{ann.get('start_line', '')}: "
                f"{ann.get('message', '')}\n"
            )

    # If no useful output in check_run, try fetching the Actions run log
    if not summary and not text and not annotations:
        failure_context += _fetch_actions_log(config, failed_run)

    return failure_context


def generate_ci_fix_suggestion(
    config: "Config",
    failure_context: str,
    diff: str,
) -> str:
    """Ask the model to analyze a CI failure and suggest a fix."""
    from criticai.providers.base import get_provider

    prompt = (
        "A CI check has failed on this pull request. Analyze the failure "
        "and suggest a fix.\n\n"
        f"CI FAILURE DETAILS:\n{failure_context}\n\n"
        f"CURRENT PR DIFF:\n{diff[:6000]}\n\n"
        "Based on the failure details and the code changes in the PR, explain:\n"
        "1. What caused the failure (1-2 sentences)\n"
        "2. How to fix it (specific code changes needed)\n"
        "3. If possible, provide the fix as a suggestion block:\n"
        "```suggestion\n<fixed code>\n```\n\n"
        "Be specific and actionable."
    )
    system = "You are CriticAI. Diagnose CI failures and suggest fixes concisely."

    provider = get_provider(config.model, config)
    return provider.invoke(config.model, system, prompt)


def _fetch_actions_log(config: "Config", check_run: dict) -> str:
    """Try to get log output from the associated GitHub Actions run."""
    # check_run may have details_url pointing to the Actions run
    details_url = check_run.get("details_url", "")
    if "actions/runs/" not in details_url:
        return "(No detailed logs available)\n"

    # Extract run ID from URL
    import re
    match = re.search(r"actions/runs/(\d+)", details_url)
    if not match:
        return "(Could not parse run ID from URL)\n"

    run_id = match.group(1)
    # Fetch the run's jobs to get step outputs
    url = f"https://api.github.com/repos/{config.repository}/actions/runs/{run_id}/jobs"
    resp = requests.get(url, headers={
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    })
    if resp.status_code != 200:
        return "(Could not fetch Actions run jobs)\n"

    jobs = resp.json().get("jobs", [])
    failed_steps = []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                failed_steps.append(f"  Job: {job['name']}, Step: {step['name']}")

    if failed_steps:
        return "Failed steps:\n" + "\n".join(failed_steps[:5]) + "\n"
    return "(No failed step details available)\n"
