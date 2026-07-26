<p align="center">
  <h1 align="center">CriticAI</h1>
  <p align="center">
    <strong>AI-powered code review that catches what humans miss.</strong><br>
    Inline fixes. Codebase awareness. Auto-approval. Zero per-seat cost.
  </p>
</p>

<p align="center">
  <a href="#setup">Setup</a> •
  <a href="#features">Features</a> •
  <a href="#commands">Commands</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#architecture">Architecture</a>
</p>

---

## What is CriticAI?

CriticAI is a self-hosted AI code review bot for GitHub. It reviews every PR
automatically, posts inline comments with one-click fix suggestions, auto-approves
safe changes, and responds to conversational commands — all powered by the
top-performing AI models available on AWS Bedrock.

**Models used:**
- **Primary:** GPT-5.6 Sol (leading SWE-bench scores, best at code generation)
- **Fallback:** Claude Opus 4.8 (exceptional multi-file reasoning and semantic logic)

Both are accessed through AWS Bedrock. If the primary model fails for any reason,
the fallback fires automatically — no review is ever silently dropped.

---

## Setup

### Step 1: Add the workflow

Create `.github/workflows/criticai.yml` in your repo:

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
      - uses: dogvatar-dog/CriticAI@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.GITHUB_TOKEN }}

  commands:
    name: CriticAI Commands
    if: >-
      github.event_name == 'issue_comment' &&
      github.event.issue.pull_request &&
      contains(github.event.comment.body, '@criticai')
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: dogvatar-dog/CriticAI@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
          mode: commands
```

### Step 2: Add AWS secrets

Set these as **org-level** GitHub Actions secrets (Settings → Secrets → Actions):

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM access key with Bedrock permissions |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret key |
| `AWS_REGION` | e.g. `us-east-1` |

**Required IAM permissions:**
```json
{
  "Statement": [
    { "Effect": "Allow", "Action": "bedrock:InvokeModel", "Resource": "*" },
    { "Effect": "Allow", "Action": "bedrock-mantle:CreateInference", "Resource": "*" }
  ]
}
```

### Step 3: Open a PR

That's it. CriticAI reviews automatically on every PR.

---

## Features

### 🔍 Intelligent Review

| Feature | Description |
|---------|-------------|
| **Inline comments** | Findings posted directly on diff lines with `Apply suggestion` buttons |
| **Codebase context** | Fetches imported/referenced files — catches cross-file bugs |
| **Sequence diagrams** | Auto-generated Mermaid diagrams showing call flow changes |
| **Severity tags** | 🔴 Critical · 🟠 Major · 🟡 Minor · 🔵 Nit |
| **Confidence scoring** | Each finding rated high/medium/low — low-confidence findings suppressed |
| **Incremental review** | On re-push, only reviews new commits (not the full PR again) |
| **Resolution tracking** | Fixed findings marked ✅ ~~strikethrough~~ — even area-based fixes |

### ⚡ Automation

| Feature | Description |
|---------|-------------|
| **Auto-approval** | Safe PRs (small, docs/tests/config only) get approved instantly |
| **Auto-fix commits** | `@criticai fix` pushes a commit with the suggested fix |
| **PR descriptions** | Auto-generates title + body when PR has no description |
| **Fix CI** | `@criticai fix-ci` analyzes failed checks and suggests fixes |
| **Fallback model** | If GPT-5.6 Sol fails, Claude Opus 4.8 takes over seamlessly |

### 🧠 Intelligence

| Feature | Description |
|---------|-------------|
| **Custom rules** | `.criticai.yml` per repo — focus areas, team standards, ignore patterns |
| **Knowledge base** | Dismissed findings tracked; won't re-flag intentional patterns |
| **Research agent** | `@criticai ask` explores the full repo to answer questions |
| **Noise control** | Only posts findings the model is confident about |

### 💬 Conversational

| Feature | Description |
|---------|-------------|
| **Update-in-place** | One review comment per PR, updated on each push |
| **8 commands** | explain, fix, fix-ci, ask, ignore, review, help + free-form questions |
| **Context-aware replies** | Bot reads the parent comment thread for context |

---

## Commands

Reply to any CriticAI comment (or any PR comment) with:

```
@criticai explain         Deeper explanation of a finding
@criticai explain 3       Explain finding #3 specifically
@criticai fix             Push a fix commit for this finding
@criticai fix-ci          Analyze CI failures and suggest a fix
@criticai ask <question>  Research the codebase
@criticai ignore          Dismiss this finding permanently
@criticai review          Re-run the full review
@criticai help            Show all commands
```

**Examples:**
```
@criticai ask where is the authentication middleware defined?
@criticai ask what functions call handlePayment?
@criticai explain why is this a security issue?
@criticai fix
```

---

## Configuration

### `.criticai.yml`

Drop this file in your repo root to customize behavior:

```yaml
# What to focus on (prioritized in the review)
focus:
  - security
  - error handling
  - TypeScript strict mode compliance

# Team rules the reviewer must enforce
rules:
  - "All async functions must have try/catch error handling"
  - "Never use 'any' type in TypeScript"
  - "API responses must be validated with zod schemas"
  - "No console.log in production code"

# Files to skip entirely (glob patterns)
ignore:
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "generated/**"
  - "*.lock"

# Minimum severity to report (critical | major | minor | nit)
min_severity: minor

# Auto-approve safe PRs
auto_approve: true
auto_approve_max_lines: 50    # Max lines changed for auto-approval
auto_approve_max_files: 8     # Max files changed for auto-approval

# Language for review output (overrides action input)
# language: Spanish
```

### Action Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `model` | `openai.gpt-5.6-sol` | Primary model (SWE-bench leader) |
| `fallback-model` | `us.anthropic.claude-opus-4-8-20260501-v1:0` | Fallback (multi-file reasoning) |
| `max-tokens` | `3072` | Max output tokens |
| `mode` | `review` | `review` or `commands` |
| `language` | `English` | Response language |
| `title` | `Code Review` | Comment header |
| `temperature` | `0.5` | Model temperature |
| `home-directory` | `''` | Path prefix filter (empty = all files) |

---

## How It Works

```
  PR opened / pushed
         │
         ▼
  ┌──────────────┐     ┌───────────────────────────┐
  │ Auto-approve?│─yes─▶│ ✅ Approve + skip review  │
  └──────┬───────┘     └───────────────────────────┘
         │ no
         ▼
  ┌──────────────┐
  │ Load config  │  .criticai.yml rules + learnings
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Fetch diff   │  Incremental if re-review
  │ + context    │  Imports → referenced files fetched
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ GPT-5.6 Sol  │  Primary model
  └──────┬───────┘
         │ fail?
         ▼
  ┌──────────────┐
  │Claude Opus4.8│  Automatic fallback
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Noise filter │  Suppress low-confidence findings
  └──────┬───────┘
         ▼
  ┌──────────────────────────────────────────┐
  │  Summary comment  │  Inline comments    │
  │  (update-in-place)│  (suggestion blocks)│
  │  + diagram        │  + confidence tags  │
  └──────────────────────────────────────────┘
```

---

## Architecture

```
criticai/
├── auto_approve.py     Safe PR detection + auto-approval
├── ci_fix.py           CI failure analysis + fix suggestions
├── commands.py         @criticai command parser (8 commands)
├── config.py           Typed configuration from env vars
├── context.py          Referenced file fetching (cross-file)
├── diagrams.py         Mermaid sequence diagram generation
├── diff.py             Diff parsing + GitHub position mapping
├── github.py           GitHub REST API client
├── inline.py           Inline comment formatting + noise filter
├── learnings.py        Dismissed finding persistence
├── pr_description.py   PR title/body generation
├── renderer.py         Comment markdown formatting
├── research.py         Codebase exploration agent
├── review.py           Review orchestration + fallback
├── rules.py            .criticai.yml config parsing
└── providers/
    ├── base.py         Provider detection + factory
    ├── anthropic.py    Claude (bedrock-runtime)
    ├── openai.py       GPT-5.x (bedrock-mantle, SigV4)
    └── amazon.py       Titan (bedrock-runtime)
```

---

## Comparison

| | CriticAI | CodeRabbit | GitHub Copilot | Macroscope |
|---|:---:|:---:|:---:|:---:|
| **Cost** | **$0/user** | $24/user/mo | $19/user/mo | Usage-based |
| Inline suggestions | ✅ | ✅ | ✅ | ✅ |
| Cross-file context | ✅ | ✅ | ✅ | ✅ |
| Auto-approval | ✅ | ❌ | ❌ | ✅ |
| Noise control | ✅ | ❌ | ❌ | ✅ |
| Research agent | ✅ | ❌ | ❌ | ✅ |
| Auto-fix commits | ✅ | ✅ | ✅ | ❌ |
| Fix CI failures | ✅ | ✅ | ❌ | ❌ |
| Custom rules | ✅ | ✅ | ✅ | ✅ |
| Knowledge base | ✅ | ✅ | ❌ | ❌ |
| Sequence diagrams | ✅ | ✅ | ❌ | ❌ |
| Incremental review | ✅ | ✅ | ✅ | ❌ |
| Fallback model | ✅ | ❌ | ❌ | ❌ |
| Self-hosted | ✅ | ❌ | ❌ | ❌ |

---

## License

MIT — see [LICENSE](LICENSE).
