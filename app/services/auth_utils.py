import hashlib
import re
import secrets
import string

PBKDF2_ITERATIONS = 120_000

PASSWORD_RULES = (
    (r".{8,}", "At least 8 characters"),
    (r"[A-Za-z]", "At least one letter"),
    (r"\d", "At least one number"),
)


def validate_password_strength(password: str) -> list[str]:
    errors = []
    for pattern, msg in PASSWORD_RULES:
        if not re.search(pattern, password):
            errors.append(msg)
    return errors


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not password:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iters, salt, expected = stored.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                int(iters),
            ).hex()
            return secrets.compare_digest(digest, expected)
        except (ValueError, TypeError):
            return False
    return secrets.compare_digest(password, stored)


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd
