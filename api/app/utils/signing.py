"""
HMAC-SHA256 webhook payload signing and verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json


def sign_payload(payload: dict, secret: str) -> str:
    """
    Sign a webhook payload with HMAC-SHA256.
    
    Returns:
        Hex-encoded signature string.
    """
    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    signature = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


def verify_signature(payload: dict, signature: str, secret: str) -> bool:
    """
    Verify a webhook signature.
    
    Args:
        payload: The webhook payload dict
        signature: The signature from X-Webhook-Signature header
        secret: The signing secret
    
    Returns:
        True if the signature is valid.
    """
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature)
