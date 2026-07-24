# Attribution and upstream fixes

This project started as a fork of
[eple0329/AWSBedrock-CodeReview](https://github.com/eple0329/AWSBedrock-CodeReview)
v1.1.3 (commit `8be98f7`), MIT licensed, Copyright (c) 2024 Ga Dong Sik.
Per the MIT License, the original copyright notice and permission text are
reproduced here since the license this repo ships under has since been
updated to reflect its own copyright:

> MIT License
>
> Copyright (c) 2024 Ga Dong Sik
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to
> deal in the Software without restriction, including without limitation the
> rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
> sell copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
> FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
> DEALINGS IN THE SOFTWARE.

## Why this fork exists

As of July 2026, `eple0329/AWSBedrock-CodeReview@latest` does not work
against a current AWS Bedrock account. This was confirmed by directly
invoking the Bedrock API (not just reading docs):

- Its default model, `anthropic.claude-3-haiku-20240307-v1:0`, is in
  Bedrock's "Legacy" lifecycle state. Accounts inactive on it for 30+ days
  lose access outright — a live `invoke-model` call against it returned
  `ResourceNotFoundException: ... marked by provider as Legacy` — and it
  hits Bedrock's hard end-of-life on 2026-09-10 regardless.
- Its only other supported model family, Amazon Titan Text, is no longer
  offered in Bedrock's model catalog in the account used for testing.
- Every current Anthropic model on Bedrock (Claude Haiku 4.5, Sonnet 4.5+,
  Opus, etc.) can only be invoked through a region-prefixed **inference
  profile ID**, e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`. A bare
  model ID fails with `ValidationException: ... on-demand throughput isn't
  supported. Retry your request with the ID or ARN of an inference profile
  that contains this model.`
- Upstream's `main.py` picks the Bedrock request shape with
  `model.split('.')[0]`. For a profile ID, that evaluates to `"us"` or
  `"global"` — matching neither the `anthropic` nor `amazon` branch — so
  `request_body` stays `""` and the call fails. This is a functional bug,
  not a configuration issue: as shipped, upstream cannot target any
  generally-available Anthropic model on Bedrock.
- Separately, Claude Sonnet 4.5 / Haiku 4.5 and later reject requests that
  set both `temperature` and `top_p`:
  `ValidationException: temperature and top_p cannot both be specified for
  this model. Please use only one.` (Also documented by AWS:
  https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html)
  Upstream always sent both (hardcoded defaults 0.5 / 0.9), which breaks on
  every current-generation Claude model.

## What was changed relative to upstream v1.1.3

1. `main.py`: added `detect_provider()`, which scans all dot-separated
   segments of the model ID for a known provider name instead of only
   checking the first segment. This makes both bare model IDs and
   profile-prefixed IDs resolve correctly.
2. `main.py`: the Anthropic request body no longer sends `top_p`, only
   `temperature`, avoiding the conflict above. The `top-p` action input is
   still accepted (for anyone copying config from the upstream README) but
   is now ignored on the Anthropic path.
3. `action.yml`: default `model` changed to
   `us.anthropic.claude-haiku-4-5-20251001-v1:0`, a currently Active
   Bedrock model, verified via a live end-to-end `invoke-model` call that
   returned an actual code review of a test diff.
4. **(2026-07-24)** Added OpenAI model support via `bedrock-mantle`, plus
   an automatic fallback model, and switched the default primary model to
   `openai.gpt-5.6-terra`. See the dedicated section below.

Everything else (PR-diff fetching/filtering, comment posting, action
inputs/outputs, `requirements.txt`) is unmodified from upstream.

## OpenAI models via bedrock-mantle (added 2026-07-24)

OpenAI models on Bedrock (GPT-5.4, GPT-5.5, GPT-5.6 Sol/Terra/Luna) are
**not reachable through `bedrock-runtime`'s `InvokeModel` at all** —
their model cards list "Invoke: Not supported". They're only available
through a separate endpoint, `bedrock-mantle`, which speaks the OpenAI
Responses API (`POST /openai/v1/responses`) instead of Bedrock's native
request/response shape. This is a genuinely different API surface, not
just a different model string:

- **Different IAM action/resource shape.** `bedrock-runtime` uses
  `bedrock:InvokeModel` on a `foundation-model/<id>` or
  `inference-profile/<id>` ARN. `bedrock-mantle` uses
  `bedrock-mantle:CreateInference` on a `project/<id>` ARN (confirmed via a
  live 403: `... not authorized to perform: bedrock-mantle:CreateInference
  on resource: arn:aws:bedrock-mantle:<region>:<account>:project/default`).
  See `AWSCloudFormation/github-actions-bedrock-review/` in the
  `dogvatar-dog` org for the IAM policy this needs, alongside the existing
  Claude Haiku 4.5 statements.
- **No boto3/AWS CLI service model** as of this writing — `bedrock-mantle`
  isn't a recognized `aws` CLI service (`Found invalid choice
  'bedrock-mantle'`). This fork hand-signs the HTTPS request with SigV4
  using `botocore.auth.SigV4Auth` instead of going through a generated
  client. AWS's documented default auth for this endpoint is a bearer
  token (Bedrock API key), but SigV4 with a regular IAM access key also
  works — confirmed directly, with either `bedrock-mantle` or `bedrock` as
  the SigV4 signing name (a real inconsistency across AWS's own docs and
  some third-party client implementations). This fork keeps SigV4/IAM
  access keys rather than migrating to bearer tokens, so there's still
  only one credential type to manage in GitHub secrets.
- **A different, model-specific parameter restriction.** GPT-5.6 Terra
  rejects a `temperature` field outright:
  `unsupported_parameter: 'temperature' is not supported with this
  model.` — a different failure mode than the Anthropic
  temperature/top_p conflict, but the same root cause (newer models
  tightening which sampling parameters they accept). The
  `bedrock-mantle` request path sends neither `temperature` nor `top_p`.
- **A silent-truncation trap.** If `max_output_tokens` is too small, the
  model can spend its entire token budget on internal reasoning and
  return `status: "incomplete"` with **zero message output and no
  error** — confirmed with `max_output_tokens: 16` returning only a
  `reasoning` output item, no `message` item, HTTP 200. This fork treats
  "no message item in the response" as a failure (raises, which triggers
  fallback) rather than letting `post_review` post an empty comment.
  `max-tokens: 3072` (the new default) was verified sufficient for a
  realistic multi-file diff, using well under half the budget even
  accounting for reasoning-token overhead.

## Automatic fallback model (added 2026-07-24)

`action.yml` gained a `fallback-model` input (default:
`us.anthropic.claude-haiku-4-5-20251001-v1:0`). If the primary `model`
call fails for any reason — network error, auth/permission error,
throttling, invalid model ID, or a response with no usable text (see the
truncation trap above) — `main.py` automatically retries once with
`fallback-model` instead of failing the whole review. There's no retry
loop on the primary model itself: for a PR-review bot, getting *a* review
promptly matters more than insisting on one specific model, so failures
fall over immediately rather than retrying-then-falling-back.

If the fallback model also fails, `analyze_with_bedrock()` returns `None`
(the pre-existing upstream behavior for any unhandled failure — this fork
didn't change what happens after both models are exhausted).

When fallback fires, the posted PR comment is prefixed with a note naming
both the failed primary model and the fallback model that actually
produced the review, so a reviewer seeing an unexpected style or quality
shift knows why instead of silently wondering. Set `fallback-model` to an
empty string to disable fallback entirely (primary-only behavior,
matching pre-fallback versions of this action).

Verified end-to-end with live Bedrock calls under the production-scoped
IAM policy (not an admin/broad-access credential): a successful primary
call, a primary failure that correctly triggered fallback and produced a
real review with the provenance note, both models failing gracefully to
`None`, and fallback correctly staying disabled when `fallback-model` is
empty.

## Maintenance

Bedrock's model lineup changes over time (see
https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html).
To re-check what's current and available in a given account/region for
`bedrock-runtime` models (Anthropic, Amazon):

```
aws bedrock list-foundation-models --region <region> --query "modelSummaries[?providerName=='Anthropic'].[modelId,modelLifecycle.status]"
aws bedrock list-inference-profiles --region <region>
```

`bedrock-mantle` (OpenAI) models aren't listed by `ListFoundationModels`
and have no CLI equivalent as of this writing — check the AWS Bedrock
model-card docs for current OpenAI model IDs and lifecycle status
instead, e.g. `docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-terra.html`.

Update the `model` / `fallback-model` defaults in `action.yml` (or
override them per-caller via the corresponding inputs) accordingly. If
the IAM policy needs updating too (e.g. a new `bedrock-mantle` project ID,
or new inference-profile ARNs), see
`AWSCloudFormation/github-actions-bedrock-review/` in the `dogvatar-dog`
org.
