# CriticAI

AI-assisted GitHub PR code review powered by AWS Bedrock, styled after
[Gemini Code Assist](https://developers.google.com/gemini-code-assist/docs/review-github-code)
and [CodeRabbit](https://www.coderabbit.ai/): a Summary / Walkthrough /
severity-tagged Findings comment that gets updated in place on every push
instead of piling up a new comment each time.

This is a maintained fork of
[eple0329/AWSBedrock-CodeReview](https://github.com/eple0329/AWSBedrock-CodeReview),
fixed to work with Bedrock's current model lineup — Anthropic (inference
profile IDs, `temperature`/`top_p` conflicts) and OpenAI (via the separate
`bedrock-mantle` endpoint) — plus an automatic fallback model if the
primary one fails. See [NOTICE.md](NOTICE.md) for the full explanation and
attribution.

## Comment format

The posted PR comment follows a fixed structure, driven by the default
`prompt` (see `action.yml`):

- **Summary** — 1-3 sentences on what the PR does.
- **Walkthrough** — a bullet list of the key changes, grouped by file or
  concern.
- **Findings** — a numbered list of concrete issues, each tagged with a
  severity (🔴 Critical, 🟠 Major, 🟡 Minor, 🔵 Nit) and a category (e.g.
  *Security*, *Performance*), with a fenced-code suggested fix where one
  applies. Omitted entirely if there's nothing to flag.
- **Suggested follow-ups** — optional non-blocking nits, omitted if empty.

The comment itself is wrapped in shared chrome: a bot-branded header
naming the commit SHA reviewed, and a footer crediting AWS Bedrock and
linking back to this repo — matching the header/footer convention both
Gemini Code Assist and CodeRabbit use on GitHub.

**One comment per PR, updated in place.** Every run checks for a comment
this action already posted on the same PR (via a hidden HTML marker) and
edits it instead of posting a new one, the same behavior Gemini Code
Assist and CodeRabbit use. This means pushing new commits refreshes the
existing review rather than creating comment clutter.

Overriding the `prompt` input replaces this structure entirely — the
wrapper (header/footer/update-in-place) still applies, but section
headings and severity tags are only present if your custom prompt asks
for them.

## How to use

```yaml
name: PR Review Bot

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: CriticAI Code Review
        uses: euvin3582/CriticAI@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.CRITIC_AI_TOKEN }} # see "Bot identity" below
          # Optional
          model: 'openai.gpt-5.6-terra' # default (primary model)
          fallback-model: 'us.anthropic.claude-haiku-4-5-20251001-v1:0' # default (used if primary fails)
          max-tokens: 3072 # default
          language: 'English' # default
          prompt: 'your custom prompt'
```

`@v1` (used above) tracks the latest `v1.x.y` release and picks up fixes
automatically. For maximum stability, pin to an exact version tag (e.g.
`@v1.1.0`) or a commit SHA instead.

## Permissions

```yaml
permissions:
  contents: read
  pull-requests: write
```

Both are mandatory:

- `pull-requests: write` — required to post/update the review comment.
  Without it you'll see errors like `"Resource not accessible by
  integration"` or `"HttpError: 403 Forbidden"` when posting.
- `contents: read` — required to fetch the PR diff itself. This action
  requests the diff via `Accept: application/vnd.github.diff`, which reads
  git blob content rather than just PR metadata, so `pull-requests` access
  alone isn't enough. Without it, `get_pr_diff()` gets a 403 and the
  action fails before ever calling Bedrock (see NOTICE.md, "Fail loudly on
  diff-fetch errors instead of silently no-op'ing" — this used to fail
  silently with a false-green check instead).

Remember that listing any permission under `permissions:` sets every
unlisted scope to `none`, so both lines above need to be present together
— just adding `pull-requests: write` on its own (as in some older
examples) leaves `contents` at `none`.

## Bot identity

By default, GitHub attributes every comment posted with `${{
secrets.GITHUB_TOKEN }}` to `github-actions[bot]` — the review text itself
still says "CriticAI", but the comment byline above it reads
`github-actions[bot] commented`, since GitHub controls that identity, not
this action. There's no input or config that changes this while using the
default token.

To have reviews posted under a bot identity, use a dedicated machine
account instead:

1. Create a GitHub account for the bot (e.g. `criticai-bot`). This must be
   a real signup completed by a human — GitHub's Terms of Service prohibit
   accounts created by automated/scripted means. GitHub explicitly permits
   this pattern as a ["machine account"](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#3-account-requirements):
   an account a human sets up and is responsible for, used exclusively for
   automated tasks. Enable 2FA on it.
2. Invite that account as a **Write** collaborator on your repo (`Settings
   → Collaborators and teams`), and accept the invite from the bot
   account.
3. While logged in as the bot account, generate a fine-grained [personal
   access token](https://github.com/settings/tokens?type=beta) scoped to
   that repo with **Pull requests: Read and write** and **Issues: Read and
   write** permissions.
4. Add the token as a repository secret (e.g. `CRITIC_AI_TOKEN`) and pass
   it as `github-token` instead of `${{ secrets.GITHUB_TOKEN }}`, as in the
   example above.

No code changes are needed for this — `criticai/github.py` already
resolves whatever identity the token belongs to (`GET /user`) and uses it
both for posting and for recognizing the bot's own comments on later
runs.

## Inputs

### Required

| Input | Description |
|---|---|
| `aws-access-key-id` | AWS IAM access key ID. |
| `aws-secret-access-key` | AWS IAM secret access key. |
| `aws-region` | AWS region with Bedrock enabled, e.g. `us-east-1`. |
| `github-token` | GitHub API token. `${{ secrets.GITHUB_TOKEN }}` works with no setup (provided automatically), but posts as `github-actions[bot]` — see [Bot identity](#bot-identity) to post as a dedicated bot account instead. |

The IAM principal behind `aws-access-key-id` / `aws-secret-access-key`
needs, at minimum, for the broadest (least-scoped) setup:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeModelAccess",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "*"
    },
    {
      "Sid": "InvokeMantleAccess",
      "Effect": "Allow",
      "Action": "bedrock-mantle:CreateInference",
      "Resource": "*"
    }
  ]
}
```

Note the **two separate actions**: OpenAI models (used via the default
`model` of `openai.gpt-5.6-terra`) go through `bedrock-mantle`, which is a
different IAM namespace and resource type (`project/<id>`) than
Anthropic/Amazon models on `bedrock-runtime`
(`foundation-model/<id>`/`inference-profile/<id>`). If you're only using
one provider (e.g. `fallback-model` set to empty and a non-OpenAI
`model`), you can drop the statement you don't need.

If you scope `Resource` down instead of using `*`, remember that current
Anthropic models require calling through an inference profile — you need
`bedrock:InvokeModel` on both the inference-profile ARN and the underlying
foundation-model ARN (regional and, for cross-region profiles, the
account-less global ARN). See
[Amazon Bedrock cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-use.html)
for details. For `bedrock-mantle`, scope to your project ARN, e.g.
`arn:aws:bedrock-mantle:<region>:<account-id>:project/default`. See
[NOTICE.md](NOTICE.md) for how this was confirmed.

### Optional

| Input | Default | Description |
|---|---|---|
| `model` | `openai.gpt-5.6-terra` | Primary Bedrock model ID or inference profile ID. Anthropic, Amazon Titan, or OpenAI. |
| `fallback-model` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Retried automatically if `model` fails for any reason. Set to `''` to disable. |
| `max-tokens` | `3072` | Max output tokens. For OpenAI models this also covers internal reasoning tokens — see [NOTICE.md](NOTICE.md) for a truncation pitfall if set too low. |
| `prompt` | see `action.yml` | Review instructions. The default asks for the Gemini/CodeRabbit-style Summary/Walkthrough/Findings structure described above — see [Comment format](#comment-format). |
| `language` | `English` | Response language. |
| `title` | `Code Review` | Header line used on the posted PR comment (a 🤖 emoji, commit SHA, and attribution footer are added automatically). |
| `temperature` | `0.5` | Model temperature. Ignored for OpenAI models — see [NOTICE.md](NOTICE.md). |
| `top-p` | `0.9` | Model top-p. Ignored for Anthropic and OpenAI models — see [NOTICE.md](NOTICE.md). |
| `home-directory` | `''` | Restrict review to files under this path. |

## Supported models

Anthropic Claude and Amazon Titan Text (via `bedrock-runtime`), and OpenAI
GPT-5.x (via the separate `bedrock-mantle` endpoint — handled
automatically based on the model ID's provider prefix). Reference
Anthropic/Amazon models by bare model ID or by inference profile ID (`us.`,
`eu.`, `global.`, etc). Bedrock's model catalog changes over time — see
[Model lifecycle](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html)
and re-verify `bedrock-runtime` models with:

```bash
aws bedrock list-foundation-models --region <region> \
  --query "modelSummaries[?providerName=='Anthropic'].[modelId,modelLifecycle.status]"
aws bedrock list-inference-profiles --region <region>
```

`bedrock-mantle` (OpenAI) models have no CLI/API listing equivalent as of
this writing — check the AWS Bedrock OpenAI model-card docs directly.

## License

MIT — see [LICENSE](LICENSE). Includes code originally from
eple0329/AWSBedrock-CodeReview, also MIT licensed — see
[NOTICE.md](NOTICE.md).
