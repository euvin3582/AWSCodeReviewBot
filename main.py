"""CriticAI entrypoint — wires modules together and runs the review.

This is intentionally thin. All logic lives in the criticai/ package.
"""

import sys

from criticai.config import Config
from criticai.diff import filter_diff, build_position_map, find_position
from criticai.github import GitHubClient, extract_previous_findings
from criticai.inline import parse_model_output
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
    raw_output = engine.run(diff, previous_findings)
    if raw_output is None:
        print("No review to post (all models failed).")
        sys.exit(1)

    # Parse into summary + structured inline findings
    review_output = parse_model_output(raw_output)

    # Post/update the summary comment (issue comment, update-in-place)
    summary_body = render_comment(review_output.summary, head_sha, config)
    github.post_comment(summary_body, existing_id)

    # Post inline review comments on the diff (if any findings have positions)
    if review_output.findings:
        position_map = build_position_map(diff)
        inline_comments = []

        for finding in review_output.findings:
            position = find_position(position_map, finding.path, finding.line)
            if position is None:
                # Line isn't in the diff — can't post inline, skip
                print(
                    f"  Skipping inline comment for {finding.path}:{finding.line} "
                    f"(not in diff)"
                )
                continue

            comment: dict = {
                "path": finding.path,
                "position": position,
                "body": finding.format_body(),
            }
            inline_comments.append(comment)

        if inline_comments:
            github.post_inline_review(inline_comments, head_sha)
        else:
            print("No findings mapped to diff positions — inline review skipped.")
    else:
        print("No structured findings — inline review skipped.")


if __name__ == "__main__":
    main()
