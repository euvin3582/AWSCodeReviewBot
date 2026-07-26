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

    # License check
    from criticai.license import check_license, LicenseError
    try:
        check_license(config)
    except LicenseError as e:
        print(str(e))
        sys.exit(1)

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

    elif command.type == CommandType.FIX_CI:
        _handle_fix_ci(github, config, event)

    elif command.type == CommandType.ASK:
        _handle_ask(github, config, command, event)

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
    """Generate and push a fix commit for the finding.

    Parses the suggestion block from the parent inline comment, fetches
    the target file from the PR branch, applies the replacement, and
    commits it directly to the branch.
    """
    import re
    import base64
    import requests

    comment_id = event["comment"]["id"]

    # Get the parent comment that contains the finding + suggestion
    in_reply_to = event.get("comment", {}).get("in_reply_to_id")
    parent_body = ""
    parent_path = ""
    parent_line = None

    if in_reply_to:
        # Try pull request review comment first (inline comments)
        url = f"https://api.github.com/repos/{config.repository}/pulls/comments/{in_reply_to}"
        resp = requests.get(url, headers={
            "Authorization": f"Bearer {config.github_token}",
            "Accept": "application/vnd.github+json",
        })
        if resp.status_code == 200:
            data = resp.json()
            parent_body = data.get("body", "")
            parent_path = data.get("path", "")
            parent_line = data.get("original_line") or data.get("line")
        else:
            # Try issue comment
            url = f"https://api.github.com/repos/{config.repository}/issues/comments/{in_reply_to}"
            resp = requests.get(url, headers={
                "Authorization": f"Bearer {config.github_token}",
                "Accept": "application/vnd.github+json",
            })
            if resp.status_code == 200:
                parent_body = resp.json().get("body", "")

    if not parent_body:
        _reply(github, config, comment_id,
               "I need more context to generate a fix. Please reply to a specific "
               "inline finding comment with `@criticai fix`.")
        return

    # Extract the suggestion block from the parent comment
    suggestion_match = re.search(
        r"```suggestion\n(.*?)\n```",
        parent_body,
        re.DOTALL,
    )

    if not suggestion_match:
        # No suggestion block — ask the model to generate a fix
        _generate_and_push_fix(github, config, event, parent_body, parent_path, parent_line)
        return

    suggested_code = suggestion_match.group(1)

    if not parent_path or not parent_line:
        _reply(github, config, comment_id,
               "Could not determine which file/line to fix. Please use "
               "'Apply suggestion' on the inline comment instead.")
        return

    # Get the PR branch name
    pr_url = f"https://api.github.com/repos/{config.repository}/pulls/{config.pr_number}"
    pr_resp = requests.get(pr_url, headers={
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    })
    if pr_resp.status_code != 200:
        _reply(github, config, comment_id, "Could not fetch PR details.")
        return

    pr_data = pr_resp.json()
    branch = pr_data["head"]["ref"]
    head_sha = pr_data["head"]["sha"]

    # Fetch the current file content
    file_url = f"https://api.github.com/repos/{config.repository}/contents/{parent_path}"
    file_resp = requests.get(file_url, params={"ref": branch}, headers={
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    })
    if file_resp.status_code != 200:
        _reply(github, config, comment_id,
               f"Could not fetch `{parent_path}` from branch `{branch}`.")
        return

    file_data = file_resp.json()
    file_sha = file_data["sha"]
    file_content = base64.b64decode(file_data["content"]).decode("utf-8")

    # Replace the specific line with the suggestion
    lines = file_content.split("\n")
    line_idx = parent_line - 1  # 0-indexed

    if line_idx < 0 or line_idx >= len(lines):
        _reply(github, config, comment_id,
               f"Line {parent_line} is out of range for `{parent_path}` "
               f"({len(lines)} lines). The file may have changed.")
        return

    # Replace the line (suggestion may be multi-line)
    suggestion_lines = suggested_code.split("\n")
    lines[line_idx:line_idx + 1] = suggestion_lines

    # Commit the fix
    new_content = "\n".join(lines)
    new_content_b64 = base64.b64encode(new_content.encode("utf-8")).decode("ascii")

    commit_msg = f"fix: apply CriticAI suggestion in {parent_path}:{parent_line}"
    put_resp = requests.put(file_url, json={
        "message": commit_msg,
        "content": new_content_b64,
        "sha": file_sha,
        "branch": branch,
    }, headers={
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    })

    if put_resp.status_code in (200, 201):
        new_sha = put_resp.json().get("commit", {}).get("sha", "")[:7]
        _reply(github, config, comment_id,
               f"✅ **Fix committed** — pushed `{new_sha}` to `{branch}`\n\n"
               f"Applied suggestion to `{parent_path}` line {parent_line}.")
    else:
        error_msg = put_resp.json().get("message", put_resp.text[:200])
        _reply(github, config, comment_id,
               f"❌ Could not push fix: {error_msg}\n\n"
               f"You can still click 'Apply suggestion' on the inline comment.")


def _generate_and_push_fix(github, config, event, finding_body, path, line):
    """When there's no suggestion block, ask the model to generate a fix."""
    comment_id = event["comment"]["id"]

    if not path:
        _reply(github, config, comment_id,
               "I can see the finding but can't determine which file to fix. "
               "Please reply to a specific inline comment with `@criticai fix`.")
        return

    # Ask the model to generate a fix
    prompt = (
        f"A code review finding needs to be fixed. Here is the finding:\n\n"
        f"{finding_body}\n\n"
        f"File: {path}, Line: {line}\n\n"
        f"Generate ONLY the corrected line(s) of code that fix this issue. "
        f"Output nothing else — just the replacement code, no explanation, "
        f"no markdown fencing."
    )
    system = "You are CriticAI. Output only the fixed code, nothing else."
    provider = get_provider(config.model, config)

    try:
        fix_code = provider.invoke(config.model, system, prompt).strip()
        _reply(github, config, comment_id,
               f"🔧 Here's the suggested fix for `{path}:{line}`:\n\n"
               f"```suggestion\n{fix_code}\n```\n\n"
               f"Click 'Apply suggestion' above to commit it, or reply "
               f"`@criticai fix` again on the inline comment to auto-push.")
    except Exception as e:
        _reply(github, config, comment_id,
               f"Could not generate a fix: {e}")


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


def _handle_ask(github, config, command, event):
    """Research the codebase to answer a free-form question."""
    from criticai.research import research_codebase

    comment_id = event["comment"]["id"]
    question = command.argument or command.raw_text

    if not question or len(question.strip()) < 5:
        _reply(github, config, comment_id,
               "Please provide a question, e.g. `@criticai ask where is the auth middleware defined?`")
        return

    try:
        answer = research_codebase(config, github, question)
        _reply(github, config, comment_id, answer)
    except Exception as e:
        _reply(github, config, comment_id,
               f"Could not research the codebase: {e}")


def _handle_fix_ci(github, config, event):
    """Analyze CI failures and suggest a fix."""
    from criticai.ci_fix import analyze_ci_failure, generate_ci_fix_suggestion

    comment_id = event["comment"]["id"]

    _reply(github, config, comment_id,
           "🔍 Analyzing CI failures... one moment.")

    failure_context = analyze_ci_failure(config, github)
    if not failure_context:
        _reply(github, config, comment_id,
               "No CI failures found on the current commit. All checks passing! ✅")
        return

    if failure_context == "No failed CI checks found on the current commit.":
        _reply(github, config, comment_id, failure_context)
        return

    # Get the current diff for context
    try:
        diff = github.get_pr_diff()
    except Exception:
        diff = ""

    try:
        suggestion = generate_ci_fix_suggestion(config, failure_context, diff)
        _reply(github, config, comment_id,
               f"🔧 **CI Failure Analysis**\n\n{suggestion}")
    except Exception as e:
        _reply(github, config, comment_id,
               f"Could not analyze CI failure: {e}")


if __name__ == "__main__":
    main()
