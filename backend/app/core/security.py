"""Authentication and password hashing security utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional

from app.core.config import settings


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256 with a cryptographically secure salt.
    Format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = secrets.token_bytes(16)
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_b64}${hash_b64}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored PBKDF2 hash using constant-time comparison.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        stored_hash = base64.b64decode(parts[3].encode("ascii"))
        derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived, stored_hash)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    """Base64url encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data_str: str) -> bytes:
    """Base64url decode with padding compensation."""
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str.encode("ascii"))


def create_access_token(payload: Dict[str, Any], expires_delta_seconds: Optional[int] = None) -> str:
    """
    Generate an HMAC-SHA256 JWT access token.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    exp = now + (expires_delta_seconds if expires_delta_seconds is not None else settings.access_token_expire_minutes * 60)
    
    token_payload = {**payload, "iat": now, "exp": exp}
    
    header_json = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_json = json.dumps(token_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    
    header_b64 = _b64url_encode(header_json)
    payload_b64 = _b64url_encode(payload_json)
    
    message = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode an HMAC-SHA256 JWT token.
    Returns payload dict if valid, or None if invalid/expired.
    """
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        
        # Verify signature
        message = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
            
        # Parse payload
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        
        # Check expiration
        exp = payload.get("exp")
        if exp is not None and int(exp) < int(time.time()):
            return None
            
        return payload
    except Exception:
        return None
