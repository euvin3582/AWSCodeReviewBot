<p align="center">
  <h1 align="center">CriticAI</h1>
  <p align="center">
    <strong>The most complete AI code review platform — at zero per-seat cost.</strong><br>
    Inline fixes · Codebase awareness · Auto-approval · Research agent · Self-hosted
  </p>
</p>

<p align="center">
  <a href="#why-criticai">Why CriticAI</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a> •
  <a href="#commands">Commands</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#how-it-differs">How It Differs</a>
</p>

---

## Why CriticAI?

Every AI code review tool in 2026 — CodeRabbit, GitHub Copilot, Macroscope,
Greptile — charges per seat, per usage, or both. They lock you into their
infrastructure, their model choices, and their pricing tiers.

**CriticAI gives you more features than any of them, and costs nothing per user.**

It runs on YOUR AWS account, using the best available models:
- **GPT-5.6 Sol** — #1 on SWE-bench, best at code generation and bug detection
- **Claude Opus 4.8** — exceptional multi-file reasoning and semantic logic

You control the models, the data stays in your account, and there's no vendor
lock-in. Scale to 1,000 developers without a pricing conversation.

---

## Quick Start

**Time to first review: under 3 minutes.**

### 1. Create the workflow file

Add `.github/workflows/criticai.yml` to any repo:

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

### 2. Set up AWS credentials

Add these as **org-level** GitHub Actions secrets so every repo inherits them:

> Settings → Secrets and variables → Actions → New organization secret

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `AWS_REGION` | AWS region with Bedrock enabled (e.g. `us-east-1`) |

The IAM user needs two permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "bedrock-mantle:CreateInference",
      "Resource": "*"
    }
  ]
}
```

### 3. Open a PR

CriticAI reviews it automatically. No per-developer setup needed — it works
for every contributor on every repo that has the workflow file.

---

## Features

### 🔍 Review Quality

| Feature | What it does |
|---------|-------------|
| **GPT-5.6 Sol + Claude Opus 4.8** | Uses the two highest-scoring models for code review (SWE-bench #1 + best multi-file reasoning) |
| **Inline comments** | Findings posted on the exact diff line with `Apply suggestion` for one-click fixes |
| **Codebase-aware** | Fetches imported/referenced files to catch cross-file bugs (broken contracts, type mismatches, deprecated usage) |
| **Confidence scoring** | Every finding rated high/medium/low — low-confidence findings suppressed automatically |
| **Severity tags** | 🔴 Critical · 🟠 Major · 🟡 Minor · 🔵 Nit — so you know what to fix first |
| **Sequence diagrams** | Mermaid diagrams auto-generated showing the call flow changes |

### ⚡ Speed & Automation

| Feature | What it does |
|---------|-------------|
| **Auto-approval** | Safe PRs (docs, tests, config, small changes) approved instantly — no human wait |
| **Incremental review** | On subsequent pushes, only reviews new commits — not the whole PR again |
| **Auto-fix commits** | Reply `@criticai fix` and the bot pushes the fix directly to your branch |
| **PR descriptions** | Auto-generates title + body when you open a PR without writing one |
| **Fix CI** | Reply `@criticai fix-ci` to diagnose failed checks and get a fix |
| **Automatic fallback** | If GPT-5.6 Sol is unavailable, Claude Opus 4.8 takes over — no review is ever dropped |

### 🧠 Team Intelligence

| Feature | What it does |
|---------|-------------|
| **Custom rules** | Drop a `.criticai.yml` in your repo — plain-English rules your team enforces |
| **Knowledge base** | Dismissed findings are remembered — same pattern won't be re-flagged |
| **Research agent** | Ask `@criticai ask where is X defined?` — it explores your repo and answers |
| **Resolution tracking** | Fixed findings get ✅ ~~strikethrough~~ — even area-based fixes, not just exact-line |

---

## Commands

Reply to any comment on a PR with:

| Command | Description |
|---------|-------------|
| `@criticai explain` | Deeper explanation of a finding |
| `@criticai explain 3` | Explain finding #3 from the summary |
| `@criticai fix` | Push a fix commit for this finding |
| `@criticai fix-ci` | Diagnose CI failures and suggest a fix |
| `@criticai ask <question>` | Research the codebase |
| `@criticai ignore` | Dismiss a finding permanently |
| `@criticai review` | Re-run the full review |
| `@criticai help` | Show all commands |

**Research agent examples:**
```
@criticai ask where is the authentication middleware defined?
@criticai ask what functions call handlePayment?
@criticai ask how are errors handled in the API layer?
@criticai ask show me the database schema for users
```

---

## Configuration

### `.criticai.yml` (optional)

Place in your repo root to customize CriticAI's behavior:

```yaml
# Focus areas (these get priority in the review)
focus:
  - security
  - error handling
  - TypeScript strict mode

# Custom rules (enforced in every review)
rules:
  - "All async functions must have try/catch"
  - "Never use 'any' type — use 'unknown' if unsure"
  - "API responses must be validated with zod schemas"
  - "No console.log in production code"

# Files to skip (glob patterns)
ignore:
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "generated/**"
  - "*.lock"

# Minimum severity to report
# Options: critical | major | minor | nit
min_severity: minor

# Auto-approval settings
auto_approve: true           # Enable/disable auto-approval
auto_approve_max_lines: 50   # Max changed lines for auto-approval
auto_approve_max_files: 8    # Max changed files for auto-approval
```

### Workflow Permissions

```yaml
permissions:
  contents: read       # Fetch PR diff + file contents
  pull-requests: write # Post comments + reviews
```

Both are required. GitHub sets unlisted scopes to `none` when you specify
`permissions:`, so both lines must always be present together.

### Action Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `aws-access-key-id` | *required* | AWS IAM access key |
| `aws-secret-access-key` | *required* | AWS IAM secret key |
| `aws-region` | *required* | e.g. `us-east-1` |
| `github-token` | *required* | `${{ secrets.GITHUB_TOKEN }}` (auto-provided) |
| `model` | `openai.gpt-5.6-sol` | Primary model |
| `fallback-model` | `us.anthropic.claude-opus-4-8-20260501-v1:0` | Fallback model |
| `max-tokens` | `3072` | Max output tokens |
| `mode` | `review` | `review` or `commands` |
| `language` | `English` | Response language |
| `title` | `Code Review` | Review comment header |
| `temperature` | `0.5` | Model temperature |
| `home-directory` | `''` | Only review files under this path (empty = all) |

---

## How It Differs

### vs CodeRabbit ($24/user/month)

| | CriticAI | CodeRabbit |
|---|---|---|
| Cost | **Free** | $24/user/month |
| Auto-approval | ✅ | ❌ |
| Noise control | ✅ Confidence-based | ❌ Reviews everything |
| Research agent | ✅ `@criticai ask` | ❌ |
| Model choice | You choose (GPT-5.6 Sol, Claude Opus 4.8, or any Bedrock model) | Locked to their models |
| Data residency | Your AWS account | Their servers |
| Fallback model | ✅ Automatic | ❌ |
| Self-hosted | ✅ | ❌ |
| Inline suggestions | ✅ | ✅ |
| Custom rules | ✅ `.criticai.yml` | ✅ `.coderabbit.yml` |
| Fix CI | ✅ | ✅ |
| Multi-platform | GitHub only | GitHub, GitLab, Bitbucket |

**Switch when:** You want the same features without per-seat fees, want to own
your data, or want auto-approval to dissolve queue time on safe PRs.

### vs GitHub Copilot Code Review ($19/user/month)

| | CriticAI | Copilot |
|---|---|---|
| Cost | **Free** | $19/user/month (requires Copilot subscription) |
| Auto-approval | ✅ | ❌ |
| Research agent | ✅ | ❌ |
| Codebase context | ✅ | ✅ (indexed) |
| Custom rules | ✅ Plain-English YAML | ✅ `.github/copilot-instructions.md` |
| Knowledge base | ✅ Learns from dismissals | ❌ |
| Fix CI | ✅ | ❌ |
| Sequence diagrams | ✅ | ❌ |
| Incremental review | ✅ | ✅ |
| Fallback model | ✅ | ❌ |
| Self-hosted | ✅ | ❌ |

**Switch when:** You don't want to pay for Copilot seats just for code review,
want more features than Copilot offers, or want control over which models run.

### vs Macroscope (usage-based)

| | CriticAI | Macroscope |
|---|---|---|
| Cost | **Free** | Usage-based (can get expensive at scale) |
| Auto-approval | ✅ | ✅ |
| Noise control | ✅ | ✅ |
| Auto-fix commits | ✅ | ❌ |
| Conversational commands | ✅ 8 commands | ❌ |
| Fix CI | ✅ | ❌ |
| Knowledge base | ✅ | ❌ |
| Sequence diagrams | ✅ | ❌ |
| Research agent | ✅ | ✅ (different approach) |
| Custom rules | ✅ YAML | ✅ Check Run Agents |
| Self-hosted | ✅ | ❌ |

**Switch when:** You want all the same structural analysis capabilities plus
conversational interaction, auto-fix, and predictable costs (free).

---

## How It Works

```
  PR opened / pushed
         │
         ▼
  ┌──────────────┐
  │ Auto-approve?│──yes──▶ ✅ Approve instantly (skip full review)
  └──────┬───────┘
         │ no
         ▼
  ┌──────────────┐
  │ Load config  │  .criticai.yml rules + team learnings
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Fetch diff   │  Incremental if re-review (only new commits)
  │ + context    │  Imports → referenced files fetched for cross-file awareness
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ GPT-5.6 Sol  │  Primary model (SWE-bench #1)
  └──────┬───────┘
         │ fail?
         ▼
  ┌──────────────┐
  │Claude Opus4.8│  Automatic fallback (multi-file reasoning)
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Noise filter │  Suppress low-confidence findings
  └──────┬───────┘
         ▼
  ┌───────────────────────────────────────────────┐
  │ Summary comment │ Inline comments  │ Mermaid  │
  │ (1 per PR,     │ (per-line with   │ sequence │
  │  updates in    │  suggestion      │ diagram  │
  │  place)        │  blocks)         │          │
  └───────────────────────────────────────────────┘
```

---

## Architecture

```
criticai/
├── auto_approve.py     Safe PR detection + instant approval
├── ci_fix.py           CI failure diagnosis + fix suggestions
├── commands.py         @criticai command parser (8 commands + aliases)
├── config.py           Typed configuration from environment
├── context.py          Cross-file context (import resolution + fetch)
├── diagrams.py         Mermaid sequence diagram generation
├── diff.py             Unified diff parsing + GitHub position mapping
├── github.py           GitHub REST API client (diff, comments, reviews, files)
├── inline.py           Inline comment formatting + confidence filter
├── learnings.py        Knowledge base (dismissed finding persistence)
├── pr_description.py   PR title/body auto-generation
├── renderer.py         Review comment markdown formatting
├── research.py         Codebase exploration agent (@criticai ask)
├── review.py           Review orchestration (model calls, fallback, context assembly)
├── rules.py            .criticai.yml configuration parser
└── providers/
    ├── base.py         Provider detection factory
    ├── anthropic.py    Claude models (bedrock-runtime)
    ├── openai.py       GPT models (bedrock-mantle, SigV4-signed)
    └── amazon.py       Titan models (bedrock-runtime)
```

---

## FAQ

**Do developers need to install anything?**
No. CriticAI runs as a GitHub Actions workflow. It's org-level infrastructure —
every developer gets reviews automatically just by opening a PR.

**Can I use different models?**
Yes. Set the `model` and `fallback-model` inputs to any model ID available in
your AWS Bedrock region. Anthropic, OpenAI, and Amazon Titan are all supported.

**Does it block merges?**
No. CriticAI posts reviews with `event: COMMENT`, which is informational only.
It never blocks a merge. Auto-approvals use `event: APPROVE` which actively
unblocks.

**Where does my code go?**
Your code goes to AWS Bedrock in your own account. CriticAI doesn't send code
to any third-party service. The diff and referenced files are sent to Bedrock
in your region, processed, and the response comes back. Nothing is stored.

**How do I add it to all repos in my org?**
Add the workflow file to each repo, or use a repo template that includes it.
AWS secrets set at the org level are inherited by all repos automatically.

---

## License

Business Source License 1.1 — see [LICENSE](LICENSE).

Source-available. Free for public repos. Use on private repositories
requires a commercial license — contact **euvin3582@gmail.com** or visit
https://criticai.dev. Converts to Apache 2.0 on 2030-07-26.
