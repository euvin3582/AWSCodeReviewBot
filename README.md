# AWS Bedrock Code Review Action

AI-assisted GitHub PR code review powered by AWS Bedrock.

This is a maintained fork of
[eple0329/AWSBedrock-CodeReview](https://github.com/eple0329/AWSBedrock-CodeReview),
fixed to work with Bedrock's current model lineup — Anthropic (inference
profile IDs, `temperature`/`top_p` conflicts) and OpenAI (via the separate
`bedrock-mantle` endpoint) — plus an automatic fallback model if the
primary one fails. See [NOTICE.md](NOTICE.md) for the full explanation and
attribution.

## How to use

```yaml
name: PR Review Bot

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: AWS Bedrock Code Review Action
        uses: euvin3582/AWSCodeReviewBot@main
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}
          github-token: ${{ secrets.GITHUB_TOKEN }} # provided by GitHub automatically
          # Optional
          model: 'openai.gpt-5.6-terra' # default (primary model)
          fallback-model: 'us.anthropic.claude-haiku-4-5-20251001-v1:0' # default (used if primary fails)
          max-tokens: 3072 # default
          language: 'English' # default
          prompt: 'your custom prompt'
```

Pin to a commit SHA or release tag instead of `@main` for production use,
since `main` can change.

## Permissions

```yaml
permissions:
  pull-requests: write
```

Write permission for pull requests is mandatory. Without it you'll see
errors like `"Resource not accessible by integration"` or
`"HttpError: 403 Forbidden"`.

## Inputs

### Required

| Input | Description |
|---|---|
| `aws-access-key-id` | AWS IAM access key ID. |
| `aws-secret-access-key` | AWS IAM secret access key. |
| `aws-region` | AWS region with Bedrock enabled, e.g. `us-east-1`. |
| `github-token` | GitHub API token. Use `${{ secrets.GITHUB_TOKEN }}` — no need to add it to secrets yourself. |

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
| `prompt` | see `action.yml` | Custom instructions for the reviewer persona/focus. |
| `language` | `English` | Response language. |
| `title` | `[Code Review]` | Header used on the posted PR comment. |
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
