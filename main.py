"""CriticAI entrypoint — wires modules together and runs the review.

This is intentionally thin. All logic lives in the criticai/ package.
"""

import sys

from criticai.config import Config
from criticai.diff import filter_diff
from criticai.github import GitHubClient, extract_previous_findings
from criticai.renderer import render_comment
from criticai.review import ReviewEngine


def main() -> None:
    # Load configuration from environment
    config = Config.from_env()

    # Initialize clients
    github = GitHubClient(config)
    engine = ReviewEngine(config)

    # Fetch PR diff
    raw_diff = github.get_pr_diff()
    diff = filter_diff(raw_diff, config.home_directory)

    # Fetch head SHA for labeling the comment
    head_sha = github.get_pr_head_sha()

    # Check for existing review comment (update-in-place)
    existing_id, existing_body = github.find_existing_comment()

    # Extract prior findings for resolution tracking
    previous_findings = extract_previous_findings(existing_body)
    if previous_findings:
        print("Found previous findings — will track resolution across pushes.")

    # Run the AI review
    review_text = engine.run(diff, previous_findings)

    # Post or update the comment
    if review_text is None:
        print("No review to post (all models failed).")
        sys.exit(1)

    body = render_comment(review_text, head_sha, config)
    github.post_comment(body, existing_id)


if __name__ == "__main__":
    main()
