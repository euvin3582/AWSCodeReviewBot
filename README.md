# AWS Bedrock Code Review Action

AI-assisted GitHub PR code review powered by AWS Bedrock.

This is a maintained fork of
[eple0329/AWSBedrock-CodeReview](https://github.com/eple0329/AWSBedrock-CodeReview),
fixed to work with Bedrock's current Anthropic model lineup (inference
profile IDs, `temperature`/`top_p` conflicts). See [NOTICE.md](NOTICE.md)
for the full explanation and attribution.

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
          model: 'us.anthropic.claude-haiku-4-5-20251001-v1:0' # default
          max-tokens: 1000 # default
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
needs at minimum:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeModelAccess",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "*"
    }
  ]
}
```

If you scope `Resource` down instead of using `*`, remember that current
Anthropic models require calling through an inference profile — you need
`bedrock:InvokeModel` on both the inference-profile ARN and the underlying
foundation-model ARN (regional and, for cross-region profiles, the
account-less global ARN). See
[Amazon Bedrock cross-Region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-use.html)
for details.

### Optional

| Input | Default | Description |
|---|---|---|
| `model` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model ID or inference profile ID. |
| `max-tokens` | `1000` | Max response tokens (3072 is Bedrock's ceiling for this action's request shape). |
| `prompt` | see `action.yml` | Custom instructions for the reviewer persona/focus. |
| `language` | `English` | Response language. |
| `title` | `[Code Review]` | Header used on the posted PR comment. |
| `temperature` | `0.5` | Model temperature. |
| `top-p` | `0.9` | Model top-p. Currently ignored for Anthropic models — see [NOTICE.md](NOTICE.md). |
| `home-directory` | `''` | Restrict review to files under this path. |

## Supported models

Anthropic Claude and Amazon Titan Text model families, referenced either by
bare model ID or by inference profile ID (`us.`, `eu.`, `global.`, etc).
Bedrock's model catalog changes over time — see
[Model lifecycle](https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html)
and re-verify with:

```bash
aws bedrock list-foundation-models --region <region> \
  --query "modelSummaries[?providerName=='Anthropic'].[modelId,modelLifecycle.status]"
aws bedrock list-inference-profiles --region <region>
```

## License

MIT — see [LICENSE](LICENSE). Includes code originally from
eple0329/AWSBedrock-CodeReview, also MIT licensed — see
[NOTICE.md](NOTICE.md).
