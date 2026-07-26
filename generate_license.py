#!/usr/bin/env python3
"""Generate a CriticAI license key.

Run this script to create license keys for paying customers.
NOT part of the GitHub Action — this is an admin tool you run locally.

Usage:
    python generate_license.py --org "acme-corp" --plan pro --months 12 --issued-to "john@acme.com"
    python generate_license.py --org "*" --plan enterprise --months 24 --issued-to "enterprise-customer"

The output is a license key string that the customer adds as a GitHub
Actions secret (CRITICAI_LICENSE_KEY) in their org/repo.
"""

import argparse
import base64
import hashlib
import hmac
import json
import time

# Must match the key in criticai/license.py
_SIGNING_KEY = b"criticai-license-v1-hmac-key-2026"


def generate_key(org: str, plan: str, months: int, issued_to: str) -> str:
    """Generate a signed license key."""
    expires = int(time.time()) + (months * 30 * 24 * 3600)

    payload = {
        "org": org,
        "plan": plan,
        "expires": expires,
        "issued_to": issued_to,
        "issued_at": int(time.time()),
    }

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_SIGNING_KEY, payload_bytes, hashlib.sha256).digest()

    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    return f"{payload_b64}.{sig_b64}"


def main():
    parser = argparse.ArgumentParser(description="Generate a CriticAI license key")
    parser.add_argument("--org", required=True, help='GitHub org name (or "*" for any org)')
    parser.add_argument("--plan", choices=["pro", "enterprise"], default="pro")
    parser.add_argument("--months", type=int, default=12, help="License duration in months")
    parser.add_argument("--issued-to", required=True, help="Customer name or email")

    args = parser.parse_args()
    key = generate_key(args.org, args.plan, args.months, args.issued_to)

    expiry_date = time.strftime(
        "%Y-%m-%d",
        time.gmtime(int(time.time()) + (args.months * 30 * 24 * 3600))
    )

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  CriticAI License Key Generated")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Org:        {args.org}")
    print(f"  Plan:       {args.plan}")
    print(f"  Expires:    {expiry_date}")
    print(f"  Issued to:  {args.issued_to}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n  License Key:\n")
    print(f"  {key}")
    print(f"\n  Instructions for customer:")
    print(f"  Add as GitHub Actions secret: CRITICAI_LICENSE_KEY")
    print(f"  Scope: org-level or repo-level")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    main()
