import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


def verify_google_token(credential: str) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is not set in backend .env")

    info = id_token.verify_oauth2_token(
        credential,
        google_requests.Request(),
        client_id,
    )

    if not info.get("email"):
        raise ValueError("Google account has no email")

    return {
        "google_id": info["sub"],
        "email": info["email"].lower().strip(),
        "name": info.get("name") or info.get("email", "").split("@")[0],
        "email_verified": bool(info.get("email_verified", False)),
    }
