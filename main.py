import re

import botocore.session, botocore.exceptions
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
import requests
import json
import os

# Github 환경 변수
github_token = os.environ['INPUT_GITHUB_TOKEN']
repo = os.environ['INPUT_GITHUB_REPOSITORY']
pr_number = os.environ['INPUT_PR_NUMBER']

# AWS 환경 변수
access_key = os.environ['INPUT_AWS_ACCESS_KEY_ID']
secret_key = os.environ['INPUT_AWS_SECRET_ACCESS_KEY']
aws_region = os.environ['INPUT_AWS_REGION']

# Bedrock 환경 변수
model = os.environ['INPUT_MODEL']
fallback_model = os.environ.get('INPUT_FALLBACK_MODEL', '').strip()
max_tokens = int(os.environ['INPUT_MAX_TOKENS'])

# 추가 환경 변수
input_prompt = os.environ['INPUT_PROMPT']
language = os.environ['INPUT_LANGUAGE']
title = os.environ['INPUT_TITLE']
temperature = float(os.environ['INPUT_TEMPERATURE'])
top_p = float(os.environ['INPUT_TOP_P'])
home_dir = os.environ['INPUT_HOME_DIRECTORY']

# Hidden marker embedded in every posted comment. GitHub renders HTML
# comments as invisible, so this doesn't affect the rendered output, but
# lets find_existing_comment() recognize a comment this action already
# posted on a prior run of the same PR and edit it in place — matching how
# Gemini Code Assist and CodeRabbit keep one updating review comment per
# PR instead of posting a new one on every push.
COMMENT_MARKER = "<!-- awscodereviewbot:review -->"


def get_pr_diff():
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.diff"
    }

    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        print(f"Status Code: {response.status_code}")

        return filtering_diff(response.text)

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None


def get_pr_head_sha():
    """Fetch the PR's current head commit SHA via the normal JSON API
    (get_pr_diff() requests the diff media type instead, which doesn't
    include this). Used only to label the posted comment with the commit
    it reviewed — Gemini Code Assist and CodeRabbit both do this so a
    reviewer can tell whether a comment reflects the latest push. Best
    effort: returns None on any failure rather than blocking the review.
    """
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        return response.json().get("head", {}).get("sha")
    except requests.exceptions.RequestException as e:
        print(f"Warning: could not fetch PR head SHA: {e}")
        return None


def filtering_diff(diff):
    changed_files = set(re.findall(r'diff --git a/(.*?) b/', diff))
    print("changed_files:")
    for file in changed_files:
        print(f"- {file}")

    # 홈 디렉토리 내의 파일만 필터링하고 제외 파일 리스트에 없는 파일만 선택
    filtered_files = [
        file for file in changed_files if file.startswith(home_dir)
    ]

    print("Filtered changed files:")
    for file in filtered_files:
        print(f"- {file}")

    # 필터링된 파일만 포함하는 새로운 diff 생성
    filtered_diff = []
    current_file = None
    for line in diff.splitlines():
        if line.startswith('diff --git'):
            file_match = re.search(r'diff --git a/(.*?) b/', line)
            if file_match:
                current_file = file_match.group(1)

        if current_file in filtered_files:
            filtered_diff.append(line)
    return '\n'.join(filtered_diff)


def detect_provider(model_id):
    """Derive the Bedrock model provider from a model ID.

    Upstream (eple0329/AWSBedrock-CodeReview) used `model.split('.')[0]`,
    which only works for bare model IDs like "anthropic.claude-3-haiku-...".
    Every current Anthropic model on Bedrock requires a region-prefixed
    inference profile ID instead, e.g. "us.anthropic.claude-haiku-4-5-..."
    or "global.anthropic.claude-haiku-4-5-...", where split('.')[0] would
    return "us"/"global" instead of "anthropic" and silently produce an
    empty request body. Scanning all dot-separated segments for a known
    provider name handles both bare model IDs and profile-prefixed ones.
    See NOTICE.md for details and how this was verified.
    """
    segments = model_id.split('.')
    if 'anthropic' in segments:
        return 'anthropic'
    if 'amazon' in segments:
        return 'amazon'
    if 'openai' in segments:
        return 'openai'
    return segments[0]


def invoke_bedrock_runtime(model_id, diff):
    """Call a model through the bedrock-runtime InvokeModel API.

    Covers Anthropic (via inference profile or bare model ID) and Amazon
    Titan models. Raises on any failure instead of swallowing it, so
    callers can decide whether to fall back to another model.
    """
    session = botocore.session.get_session()
    session.set_credentials(access_key=access_key, secret_key=secret_key)
    client = session.create_client('bedrock-runtime', region_name=aws_region)

    system_prompt = input_prompt + f" Please answer to {language}. "
    provider = detect_provider(model_id)

    if provider == 'anthropic':
        # Claude Sonnet 4.5 / Haiku 4.5 and later reject requests that set
        # both `temperature` and `top_p` with a ValidationException ("...
        # cannot both be specified for this model."). See NOTICE.md. Send
        # `temperature` only — it's accepted alone on both old and new
        # Claude models — and drop `top_p` from the request.
        request_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": diff
                }
            ]
        })
    elif provider == 'amazon':
        request_body = json.dumps({
            "inputText": system_prompt + diff,
            "textGenerationConfig": {
                "temperature": temperature,
                "topP": top_p,
                "maxTokenCount": max_tokens
            }
        })
    else:
        raise ValueError(f"invoke_bedrock_runtime does not support provider {provider!r} for model {model_id!r}")

    response = client.invoke_model(
        modelId=model_id,
        contentType='application/json',
        accept='application/json',
        body=request_body
    )

    response_body = b''
    for event in response['body']:
        response_body += event

    # 바이트 문자열을 일반 문자열로 디코딩
    response_json = json.loads(response_body.decode('utf-8', errors='ignore'))

    if provider == 'anthropic':
        return response_json['content'][0]['text']

    # provider == 'amazon'
    error = response_json.get("error")
    if error is not None:
        raise RuntimeError(f"Text generation error. Error is {error}")

    print(f"Input token count: {response_json['inputTextTokenCount']}")
    for result in response_json['results']:
        print(f"Token count: {result['tokenCount']}")
        return result['outputText']

    raise RuntimeError("Amazon Titan response contained no results")


def invoke_bedrock_mantle(model_id, diff):
    """Call an OpenAI model through the bedrock-mantle Responses API.

    OpenAI models on Bedrock (GPT-5.4/5.5/5.6 and later) are NOT reachable
    through bedrock-runtime's InvokeModel at all — they're only available
    on the separate bedrock-mantle endpoint, which speaks the OpenAI
    Responses API (POST /openai/v1/responses) rather than Bedrock's native
    request/response shape. See NOTICE.md for how this was confirmed.

    bedrock-mantle has no boto3/botocore service model as of this writing,
    so requests are hand-signed with SigV4 and sent over plain HTTPS
    instead of going through a generated client. IAM requires
    bedrock-mantle:CreateInference on the project ARN (not
    bedrock:InvokeModel on a model/inference-profile ARN) — see
    AWSCloudFormation/github-actions-bedrock-review/ in the dogvatar-dog
    org for the policy this needs.

    Note: GPT-5.6 Terra rejects a `temperature` parameter outright
    (`unsupported_parameter`), unlike the Anthropic temperature/top_p
    conflict — so this path sends neither `temperature` nor `top_p`, only
    `max_output_tokens`. If `max_output_tokens` is too small, the model can
    spend its entire budget on internal reasoning and return zero message
    text with `status: "incomplete"` and no error — that's treated as a
    failure below so it triggers fallback instead of posting an empty
    review.
    """
    session = botocore.session.get_session()
    session.set_credentials(access_key=access_key, secret_key=secret_key)
    credentials = session.get_credentials().get_frozen_credentials()

    system_prompt = input_prompt + f" Please answer to {language}. "
    url = f"https://bedrock-mantle.{aws_region}.api.aws/openai/v1/responses"
    body = json.dumps({
        "model": model_id,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": diff},
        ],
        "max_output_tokens": max_tokens,
        "store": False,
    })

    request = AWSRequest(method="POST", url=url, data=body, headers={"Content-Type": "application/json"})
    SigV4Auth(credentials, "bedrock-mantle", aws_region).add_auth(request)
    prepared = request.prepare()

    response = requests.post(url, data=body, headers=dict(prepared.headers))
    response_json = response.json()

    if response.status_code >= 400 or response_json.get("error"):
        raise RuntimeError(f"bedrock-mantle error ({response.status_code}): {response_json.get('error') or response.text}")

    message_items = [item for item in response_json.get("output", []) if item.get("type") == "message"]
    if not message_items:
        raise RuntimeError(
            f"bedrock-mantle returned no message output "
            f"(status={response_json.get('status')!r}, "
            f"incomplete_details={response_json.get('incomplete_details')!r}); "
            f"increase max-tokens if this is due to reasoning-token overhead"
        )

    content = message_items[0].get("content", [])
    text_parts = [part.get("text", "") for part in content if part.get("type") == "output_text"]
    result_text = "".join(text_parts).strip()
    if not result_text:
        raise RuntimeError("bedrock-mantle message item contained no output_text content")

    return result_text


def invoke_model(model_id, diff):
    """Dispatch to the right Bedrock endpoint based on the model's provider."""
    provider = detect_provider(model_id)
    if provider == 'openai':
        return invoke_bedrock_mantle(model_id, diff)
    return invoke_bedrock_runtime(model_id, diff)


def analyze_with_bedrock(diff):
    """Run the code review, trying `model` first and falling back to
    `fallback_model` (if configured) on any failure — network errors,
    auth/permission errors, throttling, or a response with no usable text.

    Returns the review text, or None if every configured model failed.
    """
    try:
        return invoke_model(model, diff)
    except Exception as error:
        print(f"Primary model {model!r} failed: {error}")

        if not fallback_model:
            print("No fallback-model configured; giving up.")
            return None

        print(f"Falling back to {fallback_model!r}...")
        try:
            review = invoke_model(fallback_model, diff)
            # Flag in the comment itself that the primary model failed, so a
            # maintainer seeing an unexpected style/quality shift knows why
            # rather than silently wondering. Styled as a blockquote
            # admonition to match the rest of the branded comment format
            # (see render_comment below).
            return (
                f"> ⚠️ **Fallback model used** — the primary model (`{model}`) "
                f"failed, so this review was generated by `{fallback_model}` "
                f"instead.\n\n"
                + review
            )
        except Exception as fallback_error:
            print(f"Fallback model {fallback_model!r} also failed: {fallback_error}")
            return None


def render_comment(review_text, head_sha):
    """Wrap the model's raw review text in the shared comment chrome.

    Modeled on how Gemini Code Assist and CodeRabbit format their GitHub
    PR comments: a bot-branded header line naming the commit reviewed, and
    a small footer identifying the bot and linking back to this repo,
    matching both tools' convention of a one-line attribution/help footer.
    The model is instructed (via the default `prompt` in action.yml) to
    produce a "## Summary" section followed by numbered findings — this
    function only adds the wrapper, not the inner structure, so a custom
    `prompt` input still renders reasonably.
    """
    reviewed_at = f" reviewed at commit `{head_sha[:7]}`" if head_sha else ""

    return (
        f"{COMMENT_MARKER}\n"
        f"## 🤖 {title}\n"
        f"<sub>CriticAI{reviewed_at}</sub>\n\n"
        f"---\n\n"
        f"{review_text}\n\n"
        f"---\n"
        f"<sub>🔎 Powered by AWS Bedrock · "
        f"[dogvatar-dog/CriticAI](https://github.com/dogvatar-dog/CriticAI) · "
        f"Reply in this thread or push a new commit to request another look.</sub>"
    )


def find_existing_comment():
    """Look for a comment this action already posted on this PR, so a new
    push updates it in place instead of piling up a fresh comment per push
    — the same behavior Gemini Code Assist and CodeRabbit use on GitHub.
    Returns the comment ID, or None if there isn't one yet (or the lookup
    fails, in which case we fall back to posting a new comment).

    Two things beyond just matching COMMENT_MARKER, found by this action's
    own bot dogfooding itself on dogvatar-dog/AWSCodeReviewBot#4:

    1. Paginates through *all* issue comments, not just the first page.
       GitHub returns issue comments oldest-first by default, so on a PR
       with 100+ prior comments, a naive single-page fetch would never see
       this action's own (more recent) marker comment and would post a
       duplicate on every run instead of updating it.
    2. Only matches a comment actually authored by this action's own
       identity (github-actions[bot] for the default GITHUB_TOKEN; the PAT
       owner's login for a custom github-token). Otherwise any PR
       participant could post a comment containing COMMENT_MARKER and
       this action would try to PATCH a comment it doesn't own — which
       fails outright and drops the review instead of publishing it.
    """
    api_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    # Newest-first: if a duplicate marker comment ever exists (e.g. from a
    # past run where the ownership/pagination lookup itself failed) we
    # want to keep updating the most recent one rather than an old,
    # possibly-stale one that happens to sort first under the API's
    # oldest-first default.
    params = {"per_page": 100, "sort": "created", "direction": "desc"}

    try:
        while api_url:
            response = requests.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            for existing_comment in response.json():
                body = existing_comment.get("body") or ""
                author = (existing_comment.get("user") or {}).get("login") or ""
                if COMMENT_MARKER in body and author == bot_identity_login():
                    return existing_comment["id"]
            # Only the first request needs `params`; subsequent pages come
            # from the fully-qualified `next` link already containing them.
            params = None
            api_url = response.links.get("next", {}).get("url")
    except requests.exceptions.RequestException as e:
        print(f"Warning: could not list existing comments, will post a new one: {e}")
    return None


_bot_identity_login_cache = None


def bot_identity_login():
    """Resolve the GitHub login this action is posting as, so
    find_existing_comment() can require ownership instead of trusting a
    spoofable body marker alone.

    `GET /user` (what a personal-access-token setup would use) returns 404
    for the default `${{ secrets.GITHUB_TOKEN }}` — Actions installation
    tokens aren't tied to a user account. Detect that case up front rather
    than treating the 404 as a generic failure: the default token's
    identity is always the deterministic `github-actions[bot]` login, the
    same identity GitHub itself displays for comments made with it.
    """
    global _bot_identity_login_cache
    if _bot_identity_login_cache is not None:
        return _bot_identity_login_cache

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    try:
        response = requests.get("https://api.github.com/user", headers=headers)
        if response.status_code == 404:
            # Installation token (the default GITHUB_TOKEN case).
            _bot_identity_login_cache = "github-actions[bot]"
        else:
            response.raise_for_status()
            _bot_identity_login_cache = response.json()["login"]
    except requests.exceptions.RequestException as e:
        print(f"Warning: could not resolve bot identity, assuming github-actions[bot]: {e}")
        _bot_identity_login_cache = "github-actions[bot]"

    return _bot_identity_login_cache


def post_review(comment, head_sha):
    if comment is None:
        print("No review to post (both primary and fallback model failed).")
        return

    body = render_comment(str(comment), head_sha)
    existing_comment_id = find_existing_comment()

    if existing_comment_id:
        api_url = f"https://api.github.com/repos/{repo}/issues/comments/{existing_comment_id}"
        method = requests.patch
        success_action = "updated"
    else:
        api_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
        method = requests.post
        success_action = "posted"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    }

    try:
        response = method(api_url, json={"body": body}, headers=headers)
        response.raise_for_status()
        print(f"Comment {success_action} successfully!")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    diff = get_pr_diff()
    head_sha = get_pr_head_sha()
    review_comments = analyze_with_bedrock(diff)
    post_review(review_comments, head_sha)
