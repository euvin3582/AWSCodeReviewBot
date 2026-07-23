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

Everything else (PR-diff fetching/filtering, comment posting, action
inputs/outputs, `requirements.txt`) is unmodified from upstream.

## Maintenance

Bedrock's model lineup changes over time (see
https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html).
To re-check what's current and available in a given account/region:

```
aws bedrock list-foundation-models --region <region> --query "modelSummaries[?providerName=='Anthropic'].[modelId,modelLifecycle.status]"
aws bedrock list-inference-profiles --region <region>
```

and update the `model` default in `action.yml` (or override it per-caller
via the `model` input) accordingly.
