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

## Gemini/CodeRabbit-style comment format and update-in-place (added 2026-07-24)

Requested explicitly: make the posted review "look and feel similar to
Gemini [Code Assist] and a little like CodeRabbit." Two independent
changes, both in `main.py`/`action.yml`, neither touching the Bedrock
invocation logic above:

1. **Structured comment content.** The default `prompt` in `action.yml`
   now asks the model for a fixed markdown structure — `## Summary`, `##
   Walkthrough`, `## Findings` (numbered, severity-tagged: 🔴
   Critical/🟠 Major/🟡 Minor/🔵 Nit, with a category and an optional
   fenced-code fix per finding), and an optional `## Suggested
   follow-ups`. This mirrors Gemini Code Assist's PR summary +
   per-file walkthrough and CodeRabbit's severity-tagged, collapsible
   findings list. This is a prompt change, not a parsing change —
   `main.py` does not parse or validate the model's markdown structure,
   so a custom `prompt` input can still produce free-form output; only
   the default prompt requests this shape.
2. **Comment chrome + update-in-place.** New `render_comment()` wraps
   whatever text the model returns in a shared header (🤖 title + commit
   SHA reviewed) and footer (Bedrock attribution + link to this repo).
   New `find_existing_comment()` scans the PR's existing comments for a
   hidden `<!-- awscodereviewbot:review -->` marker from a prior run and,
   if found, `post_review()` `PATCH`es that comment instead of `POST`ing
   a new one. Previously every push posted an additional comment,
   unlike Gemini Code Assist and CodeRabbit, which both edit one review
   comment per PR across pushes. The fallback-model notice (previously
   a plain italic line) is now a blockquote admonition (`> ⚠️ **Fallback
   model used**...`) to read consistently with the rest of the format.

Verified against a live PR: this repo now runs its own action against its
own PRs (see `.github/workflows/self-review.yml`), and its first live run
(against dogvatar-dog/AWSCodeReviewBot#4, the PR carrying this exact
change) produced correctly-structured Summary/Walkthrough/Findings output
from the primary model (GPT-5.6 Terra) with real severity tags and
per-finding suggested fixes — confirming the structured prompt works in
practice, not just in the abstract.

That same live run also **found three real bugs in this change**, which
were fixed in response before this landed (all in `find_existing_comment()`
unless noted):

1. 🔴 *Security* — the dogfooding workflow initially pointed
   `uses: dogvatar-dog/AWSCodeReviewBot@feat/gemini-coderabbit-style-fork`
   at a mutable branch while passing real AWS credentials, instead of a
   pinned tag — needed at the time because `v1` didn't yet include the
   code being tested. The bot's *second* live self-review run (after the
   pagination/ownership fixes below, still on the branch ref) caught that
   this was still unresolved and flagged it again as a Major finding, and
   noted this document had prematurely described it as already fixed.
   Resolved in the same PR, immediately before merge: switched
   `self-review.yml` to `@v1` and moved the `v1` tag itself to this
   commit as part of merging (see "Retagging v1" below) — so by the time
   `@v1` was live, it was never pointing at a branch that could still be
   pushed to.
2. 🟠 *Reliability* — the existing-comment lookup only fetched the first
   100 issue comments. GitHub returns issue comments oldest-first, so on
   a PR with 100+ prior comments this action's own (newer) marker comment
   would never be found, silently breaking the one-comment-per-PR
   guarantee and posting a duplicate on every run instead. Fixed by
   following the `Link: rel="next"` pagination header until either the
   marker is found or there are no more pages.
3. 🟠 *Reliability* — the marker match trusted the comment body alone.
   Any PR participant could post a comment containing
   `<!-- awscodereviewbot:review -->` and this action would try to `PATCH`
   a comment it doesn't own, which fails outright and drops the review
   instead of publishing it. Fixed with a new `bot_identity_login()`
   helper that also matches the comment author against this action's own
   identity — `github-actions[bot]` for the default `GITHUB_TOKEN`
   (`GET /user` 404s for installation tokens, so that 404 is treated as
   the signal to use the deterministic bot login rather than a generic
   failure), or the token owner's actual login for a custom
   `github-token` input.

Findings 2 and 3 were unit-tested locally with mocked HTTP responses
(pagination across two pages, a spoofed marker from a mismatched author
correctly ignored, and the 404-to-`github-actions[bot]` fallback) before
being pushed back into the same PR that had already been live-reviewed.
Pushing that fix triggered a second live self-review run, which confirmed
in the rendered comment (same comment ID, `updated_at` advanced instead
of a second comment appearing — the update-in-place behavior working
correctly end-to-end) that findings 2 and 3 no longer reproduced, correctly
re-flagged finding 1 as still open (see above), and raised one additional
🟡 Minor finding: if a duplicate marker comment ever existed,
`find_existing_comment()` would keep updating the oldest one under the
GitHub API's default oldest-first ordering rather than the most recent.
Fixed by requesting `sort=created&direction=desc` explicitly.

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
