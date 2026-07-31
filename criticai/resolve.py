"""Auto-resolve outdated review threads.

When a user pushes a fix, GitHub marks the inline review comment as
"outdated" (the diff position no longer exists). This module detects
those threads and resolves them automatically so the developer doesn't
have to click "Resolve conversation" on each one manually.

Uses the GitHub GraphQL API because resolving review threads is not
available via the REST API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from criticai.config import Config
    from criticai.github import GitHubClient


GRAPHQL_URL = "https://api.github.com/graphql"

# GraphQL query to fetch all review threads on a PR
_QUERY_THREADS = """
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          comments(first: 1) {
            nodes {
              author {
                login
              }
              body
            }
          }
        }
      }
    }
  }
}
"""

# GraphQL mutation to add a reply to a thread
_MUTATION_REPLY = """
mutation($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
    comment {
      id
    }
  }
}
"""

# GraphQL mutation to resolve a review thread
_MUTATION_RESOLVE = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread {
      isResolved
    }
  }
}
"""


def resolve_outdated_threads(github: "GitHubClient", config: "Config") -> int:
    """Find and resolve all outdated review threads posted by this bot.

    Returns the number of threads resolved.
    """
    owner, repo = config.repository.split("/", 1)
    pr_number = int(config.pr_number)

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {config.github_token}",
        "Content-Type": "application/json",
    })

    # Resolve the bot's login to only touch our own threads
    bot_login = github._resolve_bot_login()

    # Fetch all review threads
    response = session.post(GRAPHQL_URL, json={
        "query": _QUERY_THREADS,
        "variables": {"owner": owner, "repo": repo, "pr": pr_number},
    })

    if response.status_code != 200:
        print(f"Warning: could not fetch review threads (HTTP {response.status_code})")
        return 0

    data = response.json()
    errors = data.get("errors")
    if errors:
        print(f"Warning: GraphQL errors fetching threads: {errors[0].get('message', '')}")
        return 0

    threads = (
        data.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )

    resolved_count = 0

    for thread in threads:
        # Skip already-resolved threads
        if thread.get("isResolved"):
            continue

        # Only resolve threads that are outdated (code no longer at that position)
        if not thread.get("isOutdated"):
            continue

        # Only resolve threads authored by this bot
        comments = thread.get("comments", {}).get("nodes", [])
        if not comments:
            continue
        first_comment = comments[0]
        author = (first_comment.get("author") or {}).get("login", "")
        if author != bot_login:
            continue

        thread_id = thread["id"]

        # Reply with a resolution message
        reply_response = session.post(GRAPHQL_URL, json={
            "query": _MUTATION_REPLY,
            "variables": {
                "threadId": thread_id,
                "body": "✅ Fixed — this finding no longer applies to the current code.",
            },
        })
        if reply_response.status_code != 200:
            print(f"  Warning: could not reply to thread {thread_id}")
            continue

        # Resolve the thread
        resolve_response = session.post(GRAPHQL_URL, json={
            "query": _MUTATION_RESOLVE,
            "variables": {"threadId": thread_id},
        })
        if resolve_response.status_code != 200:
            print(f"  Warning: could not resolve thread {thread_id}")
            continue

        resolve_data = resolve_response.json()
        if resolve_data.get("data", {}).get("resolveReviewThread", {}).get("thread", {}).get("isResolved"):
            resolved_count += 1

    if resolved_count > 0:
        print(f"Auto-resolved {resolved_count} outdated review thread(s).")
    else:
        print("No outdated threads to resolve.")

    return resolved_count
