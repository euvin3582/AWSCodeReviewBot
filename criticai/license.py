"""License validation for CriticAI.

Enforces the business model:
  - Public repos: free, no key needed
  - Exempt orgs (dogvatar-dog): free, no key needed
  - Private repos: require a valid CRITICAI_LICENSE_KEY

License keys are HMAC-signed JSON payloads (no external server needed).
The signing secret is embedded at build time — this is deliberate.
The BSL license makes circumvention illegal regardless; this check is a
convenience gate, not a DRM system.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

from criticai.config import Config

# Exempt GitHub organizations — always allowed, no key needed
EXEMPT_ORGS = frozenset([
    "dogvatar-dog",
])

# HMAC signing key (used to verify license keys)
# This is NOT a secret that protects against piracy — the BSL license does that.
# It prevents casual tampering / typos in license keys from being accepted.
_SIGNING_KEY = b"criticai-license-v1-hmac-key-2026"


@dataclass
class LicenseInfo:
    """Decoded license key contents."""
    org: str           # GitHub org this key is valid for (or "*" for any)
    plan: str          # "pro" | "enterprise"
    expires: int       # Unix timestamp
    issued_to: str     # Customer name/email


class LicenseError(Exception):
    """Raised when a license check fails."""
    pass


def check_license(config: Config) -> None:
    """Verify the current run is licensed.

    Raises LicenseError if the run is not permitted.
    Does nothing (returns silently) if the run is allowed.

    Logic:
      1. Check if the repo is public → allowed
      2. Check if the org is exempt → allowed
      3. Check for CRITICAI_LICENSE_KEY env var → validate it
      4. Otherwise → raise with instructions
    """
    repo = config.repository  # "owner/repo"
    org = repo.split("/")[0] if "/" in repo else ""

    # Check exempt orgs
    if org.lower() in {o.lower() for o in EXEMPT_ORGS}:
        return  # Always allowed

    # Check if repo is public (set by the action via GitHub context)
    repo_visibility = os.environ.get("INPUT_REPO_VISIBILITY", "").lower()
    if repo_visibility == "public":
        return  # Public repos are always free

    # For private repos, check for a license key
    license_key = os.environ.get("CRITICAI_LICENSE_KEY", "").strip()
    if not license_key:
        raise LicenseError(
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  CriticAI — License Required for Private Repos\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  CriticAI is free for public repositories.\n"
            "\n"
            "  To use on private repos, you need a license key.\n"
            "  Add it as a secret: CRITICAI_LICENSE_KEY\n"
            "\n"
            "  Get a license: https://criticai.dev\n"
            "  Contact: euvin3582@gmail.com\n"
            "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

    # Validate the license key
    info = _validate_key(license_key)

    # Check expiration
    if info.expires < int(time.time()):
        raise LicenseError(
            f"License key expired on {time.strftime('%Y-%m-%d', time.gmtime(info.expires))}. "
            f"Renew at https://criticai.dev or contact euvin3582@gmail.com"
        )

    # Check org match
    if info.org != "*" and info.org.lower() != org.lower():
        raise LicenseError(
            f"License key is for org '{info.org}', but this repo belongs to '{org}'. "
            f"Contact euvin3582@gmail.com for a key matching your org."
        )

    print(f"License valid: {info.plan} plan for {info.org} (issued to: {info.issued_to})")


def _validate_key(key: str) -> LicenseInfo:
    """Decode and verify a license key.

    Key format: base64(json_payload) + "." + base64(hmac_signature)
    """
    try:
        parts = key.split(".")
        if len(parts) != 2:
            raise LicenseError("Invalid license key format.")

        payload_b64, sig_b64 = parts
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "==")

        # Verify HMAC
        expected_sig = hmac.new(_SIGNING_KEY, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(sig_bytes, expected_sig):
            raise LicenseError("Invalid license key (signature mismatch).")

        # Decode payload
        data = json.loads(payload_bytes)
        return LicenseInfo(
            org=data.get("org", ""),
            plan=data.get("plan", "pro"),
            expires=data.get("expires", 0),
            issued_to=data.get("issued_to", ""),
        )
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        raise LicenseError(f"Invalid license key: {e}")
