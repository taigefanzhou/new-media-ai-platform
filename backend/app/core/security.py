from __future__ import annotations

import hashlib
import secrets


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_token() -> str:
    return secrets.token_urlsafe(32)
