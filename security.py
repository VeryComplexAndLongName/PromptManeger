import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

_PASSWORD_ITERATIONS = 390000
_TOKEN_TTL_SECONDS = 60 * 60 * 8


def _machine_secret() -> str:
    return os.getenv("PROMPTMAN_KEY", os.uname().nodename if hasattr(os, "uname") else "default")


def _derive_key(label: str) -> bytes:
    material = hashlib.sha256(f"{label}:{_machine_secret()}".encode()).digest()
    return base64.urlsafe_b64encode(material)


_CIPHER = Fernet(_derive_key("fernet"))
_TOKEN_SECRET = hashlib.sha256(_derive_key("token")).digest()


def encrypt_secret(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    try:
        return _CIPHER.encrypt(value.strip().encode()).decode("utf-8")
    except Exception as exc:
        logger.warning("security.encrypt.failed error={}", exc)
        return None


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _CIPHER.decrypt(value.encode()).decode("utf-8")
    except InvalidToken:
        logger.warning("security.decrypt.invalid_token")
        return None
    except Exception as exc:
        logger.warning("security.decrypt.failed error={}", exc)
        return None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PASSWORD_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(_PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded_hash: str | None) -> bool:
    if not encoded_hash:
        return False
    try:
        algorithm, raw_iterations, salt_b64, digest_b64 = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def create_access_token(*, user_id: int, username: str, role: str, ttl_seconds: int = _TOKEN_TTL_SECONDS) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": int(time.time()) + max(60, ttl_seconds),
    }
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(_TOKEN_SECRET, f"{header_part}.{payload_part}".encode(), hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url_encode(signature)}"


def verify_access_token(token: str) -> dict[str, Any] | None:
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
    except ValueError:
        return None

    expected = hmac.new(_TOKEN_SECRET, f"{header_part}.{payload_part}".encode(), hashlib.sha256).digest()
    actual = _b64url_decode(signature_part)
    if not hmac.compare_digest(expected, actual):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_part))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    return payload
