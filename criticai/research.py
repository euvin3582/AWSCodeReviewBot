"""Codebase research agent.

Handles @criticai ask commands — lets users ask free-form questions about
the repository ("where is the auth middleware?", "what calls this function?",
"show me how errors are handled in the API layer"). The agent explores the
repo via the GitHub API (file tree, file contents) to answer.

This goes beyond reviewing diffs — it's a code research tool that lives
in your PR workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import requests

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient

from criticai.providers.base import get_provider


def research_codebase(config: "Config", github: "GitHubClient", question: str) -> str:
    """Answer a free-form question about the codebase.

    Strategy:
    1. Fetch the repo file tree (top-level + key directories)
    2. Identify which files are likely relevant to the question
    3. Fetch those files
    4. Ask the model to answer using the file contents as context

    Returns a markdown answer.
    """
    print(f"Research agent: answering '{question[:80]}...'")

    # Step 1: Get the repo file tree for context
    tree = _fetch_file_tree(config)

    # Step 2: Ask the model which files to look at
    relevant_files = _identify_relevant_files(config, tree, question)

    # Step 3: Fetch file contents
    file_contents: list[tuple[str, str]] = []
    for path in relevant_files[:6]:  # Max 6 files to stay in token budget
        content = github.get_file_content(path)
        if content:
            # Truncate large files
            if len(content) > 6000:
                content = content[:6000] + "\n... (truncated)"
            file_contents.append((path, content))

    # Step 4: Answer the question with full context
    return _answer_with_context(config, question, tree, file_contents)


def _fetch_file_tree(config: "Config") -> str:
    """Fetch a condensed file tree of the repository."""
    url = f"https://api.github.com/repos/{config.repository}/git/trees/HEAD"
    params = {"recursive": "1"}

    try:
        resp = requests.get(url, params=params, headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        })
        resp.raise_for_status()
        tree_data = resp.json().get("tree", [])

        # Filter to just files (not directories), skip node_modules/vendor
        paths = []
        for item in tree_data:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if any(skip in path for skip in ("node_modules/", "vendor/", ".git/", "dist/", "build/", "__pycache__/")):
                continue
            paths.append(path)

        # Limit to 200 paths to keep prompt size reasonable
        if len(paths) > 200:
            paths = paths[:200] + [f"... and {len(paths) - 200} more files"]

        return "\n".join(paths)
    except requests.RequestException as e:
        print(f"Warning: could not fetch file tree: {e}")
        return "(file tree unavailable)"


def _identify_relevant_files(config: "Config", tree: str, question: str) -> list[str]:
    """Ask the model which files are relevant to the question."""
    prompt = (
        f"Given this repository file tree:\n\n{tree}\n\n"
        f"A developer asked: \"{question}\"\n\n"
        "List up to 6 file paths (from the tree above) that are most likely "
        "to contain the answer. Output ONLY the file paths, one per line, "
        "nothing else. If you can't determine relevant files, output: NONE"
    )
    system = "You are a code navigation expert. Output only file paths, one per line."

    try:
        provider = get_provider(config.model, config)
        result = provider.invoke(config.model, system, prompt)

        if "NONE" in result.upper():
            return []

        paths = [
            line.strip().strip("`").strip("-").strip()
            for line in result.strip().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return [p for p in paths if "/" in p or "." in p][:6]
    except Exception as e:
        print(f"Warning: could not identify relevant files: {e}")
        return []


def _answer_with_context(
    config: "Config",
    question: str,
    tree: str,
    file_contents: list[tuple[str, str]],
) -> str:
    """Answer the question using fetched file contents as context."""
    context_parts = []
    for path, content in file_contents:
        context_parts.append(f"--- {path} ---\n{content}")

    files_context = "\n\n".join(context_parts) if context_parts else "(no files fetched)"

    prompt = (
        f"Repository file tree (condensed):\n{tree[:3000]}\n\n"
        f"Relevant file contents:\n{files_context}\n\n"
        f"Developer question: {question}\n\n"
        "Answer the question based on the code above. Be specific — reference "
        "file names, function names, and line ranges where relevant. If you "
        "can't find a definitive answer, say what you found and suggest where "
        "to look. Format as markdown."
    )
    system = (
        "You are CriticAI's research agent. Answer codebase questions "
        "accurately based on the provided file contents. Be concise but thorough."
    )

    provider = get_provider(config.model, config)
    return provider.invoke(config.model, system, prompt)
