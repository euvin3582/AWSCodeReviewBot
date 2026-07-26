"""Comment rendering — formats the model's review into the final PR comment.

Handles the branded header/footer chrome, commit SHA label, and the
hidden marker for update-in-place identification.
"""

from __future__ import annotations

from criticai.config import Config
from criticai.github import COMMENT_MARKER


def render_comment(review_text: str, head_sha: str | None, config: Config) -> str:
    """Wrap the model's raw review in branded comment chrome.

    Structure:
        <!-- criticai:review -->
        ## 🤖 {title}
        <sub>CriticAI reviewed at commit `abc1234`</sub>
        ---
        {review_text}
        ---
        <sub>footer with attribution</sub>
    """
    reviewed_at = f" reviewed at commit `{head_sha[:7]}`" if head_sha else ""

    return (
        f"{COMMENT_MARKER}\n"
        f"## 🤖 {config.title}\n"
        f"<sub>CriticAI{reviewed_at}</sub>\n\n"
        f"---\n\n"
        f"{review_text}\n\n"
        f"---\n"
        f"<sub>🔎 Powered by AWS Bedrock · "
        f"[dogvatar-dog/CriticAI](https://github.com/dogvatar-dog/CriticAI) · "
        f"Reply in this thread or push a new commit to request another look.</sub>"
    )
