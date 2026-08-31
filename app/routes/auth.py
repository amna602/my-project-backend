import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.users import User
from app.schemas import (
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from app.services.auth_utils import hash_password, validate_password_strength, verify_password
from app.services.email_service import send_reset_password_email, send_verification_email
from app.services.google_auth import verify_google_token

router = APIRouter()

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")


def _normalize_username(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _validate_username(username: str) -> None:
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3–30 characters: letters, numbers, underscore only.",
        )


def _auth_response(user: User, message: str = "Login successful"):
    return {
        "message": message,
        "user_id": user.id,
        "email": user.email,
        "name": user.name or "",
        "username": user.username or "",
        "email_verified": bool(user.email_verified),
    }


def _check_password(user: User, password: str) -> bool:
    if user.password_hash and verify_password(password, user.password_hash):
        return True
    if user.password and user.password == password:
        user.password_hash = hash_password(password)
        user.password = None
        return True
    return False


def _profile_payload(user: User) -> dict:
    username = (user.username or "").strip()
    if not username and user.email:
        username = _normalize_username(user.email.split("@")[0]) or ""
    name = (user.name or "").strip()
    if not name:
        name = username
    return {
        "user_id": user.id,
        "name": name,
        "username": username,
        "email": user.email or "",
    }


@router.get("/auth/me")
def get_current_user(user_id: int = Query(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _profile_payload(user)


@router.patch("/auth/profile")
def update_profile(body: UpdateProfileRequest, db: Session = Depends(get_db)):
    if body.name is None and body.username is None:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if body.name is not None:
        name = body.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
        if len(name) > 80:
            raise HTTPException(status_code=400, detail="Name is too long.")
        user.name = name

    if body.username is not None:
        username = _normalize_username(body.username)
        if username:
            _validate_username(username)
            taken = (
                db.query(User)
                .filter(User.username == username, User.id != user.id)
                .first()
            )
            if taken:
                raise HTTPException(status_code=400, detail="Username is already taken.")
            user.username = username
        else:
            user.username = None

    db.commit()
    db.refresh(user)
    return _profile_payload(user)


@router.get("/auth/config")
def auth_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    return {
        "google_client_id": client_id,
        "google_enabled": bool(client_id),
    }


@router.post("/signup")
def signup(user: SignupRequest, db: Session = Depends(get_db)):
    email = user.email.lower().strip()
    username = _normalize_username(user.username)
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    _validate_username(username)

    display = (user.name or "").strip() or username

    if user.password != user.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    errors = validate_password_strength(user.password)
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Password: " + ", ".join(errors),
        )

    taken_username = db.query(User).filter(User.username == username).first()
    if taken_username:
        raise HTTPException(status_code=400, detail="Username is already taken.")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.email_verified:
            raise HTTPException(
                status_code=400,
                detail="This email is already registered. Log in or use Forgot password.",
            )
        raise HTTPException(
            status_code=400,
            detail="This email is not verified yet. Log in and resend confirmation, or check your inbox.",
        )

    token = secrets.token_urlsafe(32)
    new_user = User(
        name=display,
        email=email,
        password_hash=hash_password(user.password),
        auth_provider="email",
        email_verified=False,
        verification_token=token,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    emailed = send_verification_email(email, display, token)

    return {
        "message": "Account created. Please confirm your email, then log in.",
        "user_id": new_user.id,
        "email_sent": emailed,
        "email_verified": False,
    }


@router.post("/auth/resend-verification")
def resend_verification(body: ResendVerificationRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account with this email. Sign up first.",
        )

    if user.email_verified:
        raise HTTPException(
            status_code=400,
            detail="This email is already confirmed. You can log in.",
        )

    if user.auth_provider != "email":
        raise HTTPException(
            status_code=400,
            detail="This account cannot be confirmed by email. Use Forgot password on the login page.",
        )

    token = secrets.token_urlsafe(32)
    user.verification_token = token
    db.commit()

    emailed = send_verification_email(email, user.name or "", token)
    return {
        "message": "Confirmation email sent. Check your inbox.",
        "email_sent": emailed,
    }


@router.post("/auth/verify-email")
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.verification_token == body.token.strip())
        .first()
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation link.")

    user.email_verified = True
    user.verification_token = None
    db.commit()
    return {
        "message": "Email confirmed. You can log in now.",
        "email": user.email,
    }


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account with this email. Sign up first.",
        )

    if not user.email_verified and user.auth_provider == "email":
        raise HTTPException(
            status_code=400,
            detail="Confirm your email first. Log in and use Resend confirmation.",
        )

    if user.auth_provider == "google" and not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="This account has no password yet. Use Forgot password to set one.",
        )

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
    db.commit()

    emailed = send_reset_password_email(email, user.name or "", token)
    return {
        "message": "Reset email sent. Check your inbox.",
        "email_sent": emailed,
    }


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    errors = validate_password_strength(body.password)
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Password: " + ", ".join(errors),
        )

    user = db.query(User).filter(User.reset_token == body.token.strip()).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Reset link expired. Request a new one.")

    user.password_hash = hash_password(body.password)
    user.password = None
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    return {"message": "Password updated. You can log in now."}


@router.post("/auth/google")
def auth_google(body: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        info = verify_google_token(body.credential)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google sign-in: {exc}") from exc

    user = db.query(User).filter(User.google_id == info["google_id"]).first()
    if not user:
        user = db.query(User).filter(User.email == info["email"]).first()

    if user:
        if not user.google_id:
            user.google_id = info["google_id"]
        user.email_verified = True
        if not user.name and info["name"]:
            user.name = info["name"]
        db.commit()
        db.refresh(user)
        return _auth_response(user, "Signed in with Google")

    user = User(
        name=info["name"],
        email=info["email"],
        google_id=info["google_id"],
        auth_provider="google",
        email_verified=True,
        password_hash=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_response(user, "Account created with Google")


@router.post("/login")
def login(user: LoginRequest, db: Session = Depends(get_db)):
    email = user.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()

    if not existing:
        return {"error": "No account with this email. Sign up first."}

    if existing.auth_provider == "google" and not existing.password_hash:
        return {
            "error": "This account has no password. Use Forgot password to set one, or sign up with a new email.",
        }

    if not _check_password(existing, user.password):
        return {"error": "Invalid password."}

    if not existing.email_verified and existing.auth_provider == "email":
        return {
            "error": "Please confirm your email first. Check your inbox for the confirmation link.",
        }

    db.commit()
    return _auth_response(existing)
