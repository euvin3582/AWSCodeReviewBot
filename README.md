# CriticAI

AI-powered code review for GitHub PRs — inline comments with one-click fixes,
codebase-aware analysis, auto-approval for safe PRs, and conversational
interaction. Powered by AWS Bedrock (GPT-5.6 Terra + Claude Haiku 4.5 fallback).

Zero per-seat cost. Runs on your own AWS account.

## Features

### Core Review
- **Inline comments with suggestion blocks** — findings posted directly on
  diff lines with `Apply suggestion` for one-click commits
- **Codebase-aware** — fetches imported/referenced files for cross-file analysis
  (catches broken contracts, deprecated usage, type mismatches)
- **Structured output** — Summary, Walkthrough, severity-tagged Findings
  (🔴 Critical, 🟠 Major, 🟡 Minor, 🔵 Nit)
- **Sequence diagrams** — auto-generated Mermaid diagrams showing call flow
- **Incremental review** — on subsequent pushes, only reviews new commits
- **Resolved finding tracking** — marks fixed findings with ✅ strikethrough,
  even when the fix is in a related area (not just the exact line)

### Automation
- **Auto-approval** — trivial/safe PRs (docs, tests, config, small changes)
  get auto-approved to dissolve queue time
- **Auto-fix commits** — `@criticai fix` pushes a commit with the suggested fix
- **PR description generation** — auto-generates title + body when PR is opened
  without a description
- **Fix CI failures** — `@criticai fix-ci` analyzes failed checks and suggests fixes

### Intelligence
- **Custom rules** — `.criticai.yml` per repo for team standards, focus areas,
  ignore patterns, severity thresholds
- **Knowledge base** — dismissed findings are tracked; the same pattern won't
  be re-flagged at high severity
- **Noise control** — confidence-based filtering; only posts findings the model
  is confident about (Critical/Major always pass through)
- **Automatic fallback model** — if the primary model fails, retries with a
  fallback (GPT-5.6 → Claude Haiku 4.5)

### Conversational
- `@criticai explain` — deeper explanation of a finding
- `@criticai fix` — push a fix commit for this finding
- `@criticai fix-ci` — diagnose and fix CI failures
- `@criticai ask <question>` — research the codebase ("where is auth defined?")
- `@criticai ignore` — dismiss a finding permanently
- `@criticai review` — re-run the full review
- `@criticai help` — show all commands

---

## Setup

### 1. Add the workflow to your repo

Create `.github/workflows/criticai-code-review.yml`:

```yaml
name: CriticAI
on:
  pull_request:
    types: [opened, reopened, synchronize]
  issue_comment:
    types: [created]
permissions:
  contents: read
  pull-requests: write
jobs:
  review:
    name: CriticAI Code Review
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Run Review
        uses: dogvatar-dog/CriticAI@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          max-tokens: 3072
          mode: review
  commands:
    name: CriticAI Commands
    if: >-
      github.event_name == 'issue_comment' &&
      github.event.issue.pull_request &&
      contains(github.event.comment.body, '@criticai')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Handle Command
        uses: dogvatar-dog/CriticAI@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          max-tokens: 3072
          mode: commands
```

### 2. Configure AWS secrets

Add these as org-level or repo-level GitHub Actions secrets:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION` (e.g. `us-east-1`)

The IAM user needs:
```json
{
  "Statement": [
    {"Effect": "Allow", "Action": "bedrock:InvokeModel", "Resource": "*"},
    {"Effect": "Allow", "Action": "bedrock-mantle:CreateInference", "Resource": "*"}
  ]
}
```

### 3. (Optional) Add custom rules

Create `.criticai.yml` in your repo root:

```yaml
# Focus the review on these areas
focus:
  - security
  - error handling
  - TypeScript strict mode

# Custom rules to enforce
rules:
  - "All async functions must have try/catch"
  - "Never use 'any' type — use 'unknown' if unsure"
  - "API responses must be validated with zod schemas"

# Files to skip (glob patterns)
ignore:
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "generated/**"
  - "*.lock"

# Only report findings at this level or above
# Options: critical, major, minor, nit
min_severity: minor

# Auto-approve safe PRs (small, docs-only, tests-only)
auto_approve: true
auto_approve_max_lines: 50
auto_approve_max_files: 8
```

---

## Permissions

```yaml
permissions:
  contents: read       # Required to fetch PR diff and file contents
  pull-requests: write # Required to post comments and reviews
```

Both are mandatory. Listing any permission in `permissions:` sets unlisted
scopes to `none`, so both lines must be present.

---

## Inputs

| Input | Default | Description |
|---|---|---|
| `aws-access-key-id` | required | AWS IAM access key |
| `aws-secret-access-key` | required | AWS IAM secret key |
| `aws-region` | required | AWS region with Bedrock enabled |
| `github-token` | required | `${{ secrets.GITHUB_TOKEN }}` |
| `model` | `openai.gpt-5.6-terra` | Primary Bedrock model ID |
| `fallback-model` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Fallback model (empty to disable) |
| `max-tokens` | `3072` | Max output tokens |
| `mode` | `review` | `review` or `commands` |
| `prompt` | (structured review prompt) | Custom prompt (replaces default entirely) |
| `language` | `English` | Response language |
| `title` | `Code Review` | Comment header title |
| `temperature` | `0.5` | Model temperature |
| `top-p` | `0.9` | Top-p (ignored for Anthropic/OpenAI) |
| `home-directory` | `''` | Path prefix filter (empty = all files) |

---

## How It Works

```
PR opened/pushed
       │
       ▼
┌─────────────────┐
│  Auto-approve?  │──yes──▶ ✅ Approve & skip review
└────────┬────────┘
         │ no
         ▼
┌─────────────────┐
│  Load rules +   │
│  learnings      │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Fetch diff     │──incremental if re-review
│  + context files│
└────────┬────────┘
         ▼
┌─────────────────┐
│  Generate PR    │──only on first review if body empty
│  description    │
└────────┬────────┘
         ▼
┌─────────────────┐
│  AI Review      │──with rules, learnings, context
│  (primary model)│
└────────┬────────┘
         │ fail?
         ▼
┌─────────────────┐
│  Fallback model │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Noise filter   │──suppress low-confidence findings
└────────┬────────┘
         ▼
┌────────┴────────┐
│  Post summary   │  Post inline    │  Generate
│  comment        │  review         │  diagram
│  (update in     │  comments       │  (mermaid)
│  place)         │  + suggestions  │
└─────────────────┴─────────────────┘
```

---

## Architecture

```
criticai/
├── __init__.py              # Package (v2.0.0)
├── auto_approve.py          # Safe PR detection + auto-approval
├── ci_fix.py                # CI failure analysis
├── commands.py              # @criticai command parser
├── config.py                # Configuration from env vars
├── context.py               # Referenced file fetching
├── diagrams.py              # Mermaid sequence diagrams
├── diff.py                  # Diff parsing + position mapping
├── github.py                # GitHub API client
├── inline.py                # Inline comment formatting + noise filter
├── learnings.py             # Dismissed finding tracking
├── pr_description.py        # PR description generation
├── renderer.py              # Comment chrome/formatting
├── research.py              # Codebase research agent
├── review.py                # Review engine (orchestration)
├── rules.py                 # .criticai.yml custom rules
└── providers/
    ├── __init__.py
    ├── base.py              # Provider detection + factory
    ├── anthropic.py         # Claude via bedrock-runtime
    ├── openai.py            # GPT-5.x via bedrock-mantle
    └── amazon.py            # Titan via bedrock-runtime

main.py                      # Review entrypoint
comment_handler.py           # @criticai command entrypoint
action.yml                   # GitHub Action definition
```

---

## License

MIT — see [LICENSE](LICENSE).
