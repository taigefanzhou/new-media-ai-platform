from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected = password_hash.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(digest.hex(), expected)
    legacy_digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_digest, password_hash)


def password_hash_needs_upgrade(password_hash: str) -> bool:
    return not password_hash.startswith("pbkdf2_sha256$")


def create_token() -> str:
    return secrets.token_urlsafe(32)
