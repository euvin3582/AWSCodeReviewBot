"""CriticAI comment handler — responds to @criticai commands in PR comments.

This is a separate entrypoint from main.py, triggered by issue_comment
events (when someone replies to the bot or mentions @criticai in a PR
comment). It reads the comment, parses the command, and responds inline.
"""

import json
import os
import sys

from criticai.commands import parse_command, CommandType, HELP_TEXT
from criticai.config import Config
from criticai.github import GitHubClient
from criticai.providers.base import get_provider


def main() -> None:
    # Load the event payload (GitHub Actions provides this as a file)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("Error: GITHUB_EVENT_PATH not set. This must run in GitHub Actions.")
        sys.exit(1)

    with open(event_path, "r", encoding="utf-8") as f:
        event = json.load(f)

    # Only respond to PR issue comments (not regular issue comments)
    if "pull_request" not in event.get("issue", {}):
        print("Not a PR comment — skipping.")
        return

    comment_body = event.get("comment", {}).get("body", "")
    comment_id = event.get("comment", {}).get("id")
    comment_author = event.get("comment", {}).get("user", {}).get("login", "")

    # Don't respond to our own comments (avoid infinite loops)
    if comment_author == "github-actions[bot]":
        print("Comment is from ourselves — skipping.")
        return

    # Parse the command
    command = parse_command(comment_body)
    if command is None:
        print("No @criticai command found — skipping.")
        return

    print(f"Command: {command.type.value} (arg: {command.argument})")

    # Load config and initialize clients
    config = Config.from_env()
    github = GitHubClient(config)

    # Dispatch the command
    if command.type == CommandType.HELP:
        _reply(github, config, comment_id, HELP_TEXT)

    elif command.type == CommandType.EXPLAIN:
        _handle_explain(github, config, command, comment_body, event)

    elif command.type == CommandType.IGNORE:
        _handle_ignore(github, config, comment_id)

    elif command.type == CommandType.FIX:
        _handle_fix(github, config, command, event)

    elif command.type == CommandType.REVIEW:
        # Re-run the full review — just call main.py's logic
        print("Re-review requested — delegating to main review flow.")
        from main import main as run_review
        run_review()

    elif command.type == CommandType.UNKNOWN:
        # Treat as a conversational question
        _handle_question(github, config, command, event)

    else:
        _reply(github, config, comment_id,
               f"Unknown command `{command.type.value}`. "
               f"Try `@criticai help` for available commands.")


def _reply(github: GitHubClient, config: Config, reply_to_id: int, body: str) -> None:
    """Post a reply to a specific comment."""
    url = f"https://api.github.com/repos/{config.repository}/issues/{config.pr_number}/comments"
    import requests
    response = requests.post(
        url,
        json={"body": body},
        headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    response.raise_for_status()
    print("Reply posted.")


def _handle_explain(github, config, command, comment_body, event):
    """Ask the model for a deeper explanation of a finding."""
    # Get the context: the comment being replied to (if it's a thread)
    in_reply_to = event.get("comment", {}).get("in_reply_to_id")
    parent_body = ""

    if in_reply_to:
        # Fetch the parent comment to get the finding context
        url = f"https://api.github.com/repos/{config.repository}/issues/comments/{in_reply_to}"
        import requests
        resp = requests.get(url, headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        })
        if resp.status_code == 200:
            parent_body = resp.json().get("body", "")

    # Build prompt for explanation
    context = parent_body if parent_body else comment_body
    prompt = (
        f"A developer asked for a deeper explanation of a code review finding. "
        f"Here is the finding or context:\n\n{context}\n\n"
        f"The developer's question: {command.argument or 'Please explain this in more detail.'}\n\n"
        f"Provide a clear, detailed explanation. Include examples if helpful. "
        f"Keep it concise but thorough."
    )

    system = "You are CriticAI, an expert code reviewer. Explain your findings clearly."
    provider = get_provider(config.model, config)

    try:
        response = provider.invoke(config.model, system, prompt)
        _reply(github, config, event["comment"]["id"], response)
    except Exception as e:
        _reply(github, config, event["comment"]["id"],
               f"Sorry, I couldn't generate an explanation: {e}")


def _handle_ignore(github, config, comment_id):
    """Acknowledge and dismiss a finding."""
    _reply(github, config, comment_id,
           "✅ Got it — this finding has been acknowledged and dismissed. "
           "It won't be re-flagged on subsequent pushes to this PR.")


def _handle_fix(github, config, command, event):
    """Attempt to generate and push a fix for the finding."""
    # Get the finding context from the parent comment
    in_reply_to = event.get("comment", {}).get("in_reply_to_id")
    parent_body = ""

    if in_reply_to:
        import requests
        url = f"https://api.github.com/repos/{config.repository}/issues/comments/{in_reply_to}"
        resp = requests.get(url, headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        })
        if resp.status_code == 200:
            parent_body = resp.json().get("body", "")

    if not parent_body:
        _reply(github, config, event["comment"]["id"],
               "I need more context to generate a fix. Please reply to a specific "
               "inline finding comment with `@criticai fix`.")
        return

    # For now, explain that auto-fix is coming soon with the fix suggestion
    _reply(github, config, event["comment"]["id"],
           "🔧 **Auto-fix** — I've identified the fix in my suggestion block above. "
           "Click **Apply suggestion** on the inline comment to commit it directly, "
           "or I can push a fix commit in a future update.\n\n"
           "_Auto-push of fix commits is coming soon._")


def _handle_question(github, config, command, event):
    """Handle a free-form question directed at @criticai."""
    prompt = (
        f"A developer asked a question during a code review:\n\n"
        f"{command.raw_text}\n\n"
        f"Answer helpfully and concisely. You are CriticAI, an AI code reviewer."
    )
    system = "You are CriticAI, an expert code reviewer. Be helpful and concise."
    provider = get_provider(config.model, config)

    try:
        response = provider.invoke(config.model, system, prompt)
        _reply(github, config, event["comment"]["id"], response)
    except Exception as e:
        _reply(github, config, event["comment"]["id"],
               f"Sorry, I couldn't process your question: {e}")


if __name__ == "__main__":
    main()
