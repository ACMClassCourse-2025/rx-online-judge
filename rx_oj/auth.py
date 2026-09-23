"""Password hashing and opaque, server-side sessions; no public registration."""

import hashlib
import hmac
import re
import secrets

COOKIE_NAME = "rx_oj_session"


def username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", value):
        raise ValueError("Username must be 3–40 letters, digits, dots, underscores, or hyphens")
    return value


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("Password must contain between 12 and 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=67108864)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    # Missing users still incur the same password hashing cost.
    salt, expected = bytes(16), bytes(64)
    if encoded:
        scheme, raw_salt, raw_digest = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = bytes.fromhex(raw_salt), bytes.fromhex(raw_digest)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=67108864)
    return hmac.compare_digest(digest, expected) and encoded is not None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user):
    return {key: user[key] for key in ("id", "username", "is_admin")}
