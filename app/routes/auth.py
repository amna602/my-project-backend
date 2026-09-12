import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db

from app.models.users import User
from app.models.chat_thread import ChatThread
from app.models.chat_message import ChatMessage
from app.models.progress import Progress
from app.models.assessment_session import (
    AssessmentSession,
    AssessmentItem,
)
from app.models.settings import AdminSettings

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

from app.services.auth_utils import (
    hash_password,
    validate_password_strength,
    verify_password,
)

from app.services.email_service import (
    send_reset_password_email,
    send_verification_email,
)

from app.services.google_auth import verify_google_token


router = APIRouter()

USERNAME_RE = re.compile(
    r"^[a-zA-Z0-9_]{3,30}$"
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _normalize_username(
    value: str | None,
) -> str | None:

    if value is None:
        return None

    cleaned = value.strip().lower()

    return cleaned or None


def _validate_username(
    username: str,
) -> None:

    if not USERNAME_RE.match(username):

        raise HTTPException(
            status_code=400,
            detail=(
                "Username must be 3–30 characters: "
                "letters, numbers, underscore only."
            ),
        )


def _auth_response(
    user: User,
    message: str = "Login successful",
):

    return {
        "message": message,
        "user_id": user.id,
        "email": user.email,
        "name": user.name or "",
        "username": user.username or "",
        "email_verified": bool(
            user.email_verified
        ),
        "role": user.role or "user",
    }


def _check_password(
    user: User,
    password: str,
) -> bool:

    # New hashed password
    if (
        user.password_hash
        and verify_password(
            password,
            user.password_hash,
        )
    ):
        return True

    # Legacy plain password migration
    if (
        user.password
        and user.password == password
    ):

        user.password_hash = hash_password(
            password
        )

        user.password = None

        return True

    return False


def _profile_payload(
    user: User,
) -> dict:

    username = (
        user.username or ""
    ).strip()

    if not username and user.email:

        username = (
            _normalize_username(
                user.email.split("@")[0]
            )
            or ""
        )

    name = (
        user.name or ""
    ).strip()

    if not name:
        name = username

    return {
        "user_id": user.id,
        "name": name,
        "username": username,
        "email": user.email or "",
    }


# ============================================================
# CURRENT USER
# ============================================================

@router.get("/auth/me")
def get_current_user(
    user_id: int = Query(...),
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    return _profile_payload(user)


# ============================================================
# ADMIN - GET ALL USERS
# ============================================================

@router.get("/admin/users")
def get_all_users(
    db: Session = Depends(get_db),
):

    users = (
        db.query(User)
        .order_by(
            User.created_at.desc()
        )
        .all()
    )

    result = []

    for user in users:

        conversations_count = (
            db.query(ChatThread)
            .filter(ChatThread.user_id == user.id)
            .count()
        )

        progress = (
            db.query(Progress)
            .filter(Progress.user_id == user.id)
            .first()
        )

        problems_solved = (
            progress.solved_questions
            if progress and progress.solved_questions
            else 0
        )

        result.append({
            "id": user.id,
            "name": (user.name or "").strip(),
            "username": (user.username or "").strip(),
            "email": (user.email or ""),
            "status": "Active" if user.email_verified else "Inactive",
            "joined": user.created_at.isoformat() if user.created_at else None,
            "role": user.role or "user",
            "conversations": conversations_count,
            "problemsSolved": problems_solved,
        })

    return result


# ============================================================
# ADMIN - GET ALL CONVERSATIONS
# ============================================================

@router.get("/admin/conversations")
def get_all_conversations(
    db: Session = Depends(get_db),
):

    threads = (
        db.query(ChatThread, User)
        .join(
            User,
            ChatThread.user_id == User.id,
        )
        .order_by(
            ChatThread.updated_at.desc()
        )
        .all()
    )

    conversations = []

    for thread, user in threads:

        # ----------------------------------------------------
        # GET ALL MESSAGES FOR THIS CONVERSATION
        # ----------------------------------------------------

        messages = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.thread_id
                == thread.id
            )
            .order_by(
                ChatMessage.created_at.asc()
            )
            .all()
        )

        # ----------------------------------------------------
        # LAST MESSAGE
        # ----------------------------------------------------

        last_message = None

        if messages:
            last_message = messages[-1].content

        # ----------------------------------------------------
        # CONVERSATION STATUS
        #
        # Updated within last 30 minutes = Active
        # Otherwise = Completed
        # ----------------------------------------------------

        now = datetime.utcnow()

        if (
            thread.updated_at
            and (
                now - thread.updated_at
            ).total_seconds()
            <= 30 * 60
        ):
            status = "Active"
        else:
            status = "Completed"

        # ----------------------------------------------------
        # DATE
        #
        # Windows-safe formatting
        # ----------------------------------------------------

        if thread.updated_at:

            conversation_date = (
                thread.updated_at
                .strftime("%b %d, %Y")
                .replace(" 0", " ")
            )

            conversation_time = (
                thread.updated_at
                .strftime("%I:%M %p")
            )

        elif thread.created_at:

            conversation_date = (
                thread.created_at
                .strftime("%b %d, %Y")
                .replace(" 0", " ")
            )

            conversation_time = (
                thread.created_at
                .strftime("%I:%M %p")
            )

        else:

            conversation_date = ""
            conversation_time = ""

        # ----------------------------------------------------
        # ADD CONVERSATION
        # ----------------------------------------------------

        conversations.append(
            {
                "id": thread.id,
"user_id": user.id,
                "user": (
                    user.name or ""
                ).strip(),

                "username": (
                    user.username or ""
                ).strip(),

                "email": (
                    user.email or ""
                ),

                "topic": (
                    thread.title
                    or "New chat"
                ),

                "date": conversation_date,

                "time": conversation_time,

                "messages": len(messages),

                "status": status,

                "lastMessage": (
                    last_message or ""
                ),
            }
        )

    return {
        "total": len(conversations),
        "conversations": conversations,
    }


   
# ============================================================
# ADMIN - ANALYTICS
# ============================================================

@router.get("/admin/analytics")
def get_admin_analytics(
    db: Session = Depends(get_db),
):

    # ========================================================
    # BASIC COUNTS
    # ========================================================

    total_users = (
        db.query(User).count()
    )

    total_conversations = (
        db.query(ChatThread).count()
    )

    total_messages = (
        db.query(ChatMessage).count()
    )

    total_problems_solved = (
        db.query(
            func.coalesce(
                func.sum(
                    Progress.solved_questions
                ),
                0,
            )
        ).scalar()
        or 0
    )


    # ========================================================
    # ACTIVE USERS
    #
    # A user is considered active if they have
    # at least one conversation.
    # ========================================================

    active_users = (
        db.query(
            func.count(
                func.distinct(
                    ChatThread.user_id
                )
            )
        ).scalar()
        or 0
    )


    # ========================================================
    # USER GROWTH - LAST 6 MONTHS
    # ========================================================

    now = datetime.utcnow()

    months = []

    current_year = now.year
    current_month = now.month

    for _ in range(6):

        months.append(
            (
                current_year,
                current_month,
            )
        )

        current_month -= 1

        if current_month == 0:

            current_month = 12
            current_year -= 1


    months.reverse()


    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]


    user_growth = []

    for year, month in months:

        if month == 12:

            next_year = year + 1
            next_month = 1

        else:

            next_year = year
            next_month = month + 1


        start_date = datetime(
            year,
            month,
            1,
        )

        end_date = datetime(
            next_year,
            next_month,
            1,
        )


        count = (
            db.query(User)
            .filter(
                User.created_at >= start_date,
                User.created_at < end_date,
            )
            .count()
        )


        user_growth.append(
            {
                "month": month_names[
                    month - 1
                ],
                "value": count,
            }
        )


    # ========================================================
    # ACTIVITY OVERVIEW
    # ========================================================

    chat_users = (
        db.query(
            func.count(
                func.distinct(
                    ChatThread.user_id
                )
            )
        ).scalar()
        or 0
    )


    problem_users = (
        db.query(Progress)
        .filter(
            Progress.solved_questions > 0
        )
        .count()
    )


    assessment_users = (
        db.query(
            func.count(
                func.distinct(
                    AssessmentSession.user_id
                )
            )
        ).scalar()
        or 0
    )


    verified_users = (
        db.query(User)
        .filter(
            User.email_verified.is_(True)
        )
        .count()
    )


    def percentage(
        value: int,
        total: int,
    ) -> int:

        if not total:
            return 0

        return round(
            (value / total) * 100
        )


    activity_overview = {

        "chat_activity": percentage(
            chat_users,
            total_users,
        ),

        "problem_solving": percentage(
            problem_users,
            total_users,
        ),

        "assessment_activity": percentage(
            assessment_users,
            total_users,
        ),

        "verified_accounts": percentage(
            verified_users,
            total_users,
        ),
    }


    # ========================================================
    # DAILY ACTIVITY
    #
    # Based on actual ChatMessage records.
    # ========================================================

    weekday_counts = {

        "Monday": 0,

        "Tuesday": 0,

        "Wednesday": 0,

        "Thursday": 0,

        "Friday": 0,

        "Saturday": 0,

        "Sunday": 0,
    }


    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.created_at.isnot(None)
        )
        .all()
    )


    for message in messages:

        if not message.created_at:
            continue

        day = (
            message.created_at
            .strftime("%A")
        )

        if day in weekday_counts:

            weekday_counts[day] += 1


    max_messages = (
        max(
            weekday_counts.values()
        )
        if weekday_counts
        else 0
    )


    daily_activity = []


    for day, count in (
        weekday_counts.items()
    ):

        relative_percentage = (

            round(
                (count / max_messages)
                * 100
            )

            if max_messages

            else 0
        )


        daily_activity.append(
            {
                "day": day,
                "messages": count,
                "value": relative_percentage,
            }
        )


    # ========================================================
    # ASSESSMENT SUCCESS RATE
    # ========================================================

    answered_items = (
        db.query(AssessmentItem)
        .filter(
            AssessmentItem.is_correct
            .isnot(None)
        )
        .count()
    )


    correct_items = (
        db.query(AssessmentItem)
        .filter(
            AssessmentItem.is_correct == 1
        )
        .count()
    )


    success_rate = (

        round(
            (
                correct_items
                / answered_items
            )
            * 100,
            1,
        )

        if answered_items

        else 0
    )


    # ========================================================
    # DAILY ACTIVE USERS
    #
    # Users who sent/received a chat message today.
    # ========================================================

    today = datetime.utcnow().date()


    daily_active_users = (
        db.query(
            func.count(
                func.distinct(
                    ChatThread.user_id
                )
            )
        )
        .join(
            ChatMessage,
            ChatMessage.thread_id
            == ChatThread.id,
        )
        .filter(
            func.date(
                ChatMessage.created_at
            )
            == today.isoformat()
        )
        .scalar()
        or 0
    )


    # ========================================================
    # AVERAGE PROBLEMS PER USER
    # ========================================================

    avg_problems_per_user = (

        round(
            total_problems_solved
            / total_users,
            1,
        )

        if total_users

        else 0
    )


    # ========================================================
    # FINAL ANALYTICS RESPONSE
    # ========================================================

    return {

        "total_users": total_users,

        "active_users": active_users,

        "conversations": total_conversations,

        "messages": total_messages,

        "problems_solved": (
            total_problems_solved
        ),

        "user_growth": user_growth,

        "activity_overview": (
            activity_overview
        ),

        "daily_activity": (
            daily_activity
        ),

        "quick_stats": {

            "daily_active_users": (
                daily_active_users
            ),

            "success_rate": (
                success_rate
            ),

            "avg_problems_per_user": (
                avg_problems_per_user
            ),
        },
    }


# ============================================================
# UPDATE PROFILE
# ============================================================

@router.patch("/auth/profile")
def update_profile(
    body: UpdateProfileRequest,
    db: Session = Depends(get_db),
):

    if (
        body.name is None
        and body.username is None
    ):

        raise HTTPException(
            status_code=400,
            detail="Nothing to update.",
        )


    user = (
        db.query(User)
        .filter(
            User.id == body.user_id
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )


    # --------------------------------------------------------
    # UPDATE NAME
    # --------------------------------------------------------

    if body.name is not None:

        name = body.name.strip()


        if len(name) < 2:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Name must be at least "
                    "2 characters."
                ),
            )


        if len(name) > 80:

            raise HTTPException(
                status_code=400,
                detail="Name is too long.",
            )


        user.name = name


    # --------------------------------------------------------
    # UPDATE USERNAME
    # --------------------------------------------------------

    if body.username is not None:

        username = (
            _normalize_username(
                body.username
            )
        )


        if username:

            _validate_username(
                username
            )


            taken = (
                db.query(User)
                .filter(
                    User.username
                    == username,
                    User.id
                    != user.id,
                )
                .first()
            )


            if taken:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Username is already taken."
                    ),
                )


            user.username = username

        else:

            user.username = None


    db.commit()

    db.refresh(user)

    return _profile_payload(user)


# ============================================================
# AUTH CONFIG
# ============================================================

@router.get("/auth/config")
def auth_config():

    client_id = (
        os.getenv(
            "GOOGLE_CLIENT_ID",
            "",
        ).strip()
    )


    return {

        "google_client_id": (
            client_id
        ),

        "google_enabled": bool(
            client_id
        ),
    }


# ============================================================
# SIGNUP
# ============================================================

@router.post("/signup")
def signup(
    user: SignupRequest,
    db: Session = Depends(get_db),
):

    email = (
        user.email
        .lower()
        .strip()
    )


    username = (
        _normalize_username(
            user.username
        )
    )


    if not username:

        raise HTTPException(
            status_code=400,
            detail="Username is required.",
        )


    _validate_username(
        username
    )


    display = (
        user.name or ""
    ).strip() or username


    if (
        user.password
        != user.confirm_password
    ):

        raise HTTPException(
            status_code=400,
            detail="Passwords do not match.",
        )


    errors = (
        validate_password_strength(
            user.password
        )
    )


    if errors:

        raise HTTPException(
            status_code=400,
            detail=(
                "Password: "
                + ", ".join(errors)
            ),
        )


    # --------------------------------------------------------
    # CHECK USERNAME
    # --------------------------------------------------------

    taken_username = (
        db.query(User)
        .filter(
            User.username
            == username
        )
        .first()
    )


    if taken_username:

        raise HTTPException(
            status_code=400,
            detail="Username is already taken.",
        )


    # --------------------------------------------------------
    # CHECK EMAIL
    # --------------------------------------------------------

    existing = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )


    if existing:

        raise HTTPException(
            status_code=400,
            detail=(
                "This email is already registered. "
                "Log in or use Forgot password."
            ),
        )


    # --------------------------------------------------------
    # CREATE USER
    # --------------------------------------------------------

    new_user = User(

        name=display,

        email=email,

        password_hash=hash_password(
            user.password
        ),

        auth_provider="email",

        email_verified=True,

        verification_token=None,

        role="user",
    )


    db.add(new_user)

    db.commit()

    db.refresh(new_user)


    return {

        "message": (
            "Account created successfully. "
            "You can now log in."
        ),

        "user_id": new_user.id,

        "email_sent": False,

        "email_verified": True,
    }


# ============================================================
# RESEND VERIFICATION
# ============================================================

@router.post(
    "/auth/resend-verification"
)
def resend_verification(
    body: ResendVerificationRequest,
    db: Session = Depends(get_db),
):

    email = (
        body.email
        .lower()
        .strip()
    )


    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=404,
            detail=(
                "No account with this email. "
                "Sign up first."
            ),
        )


    if user.email_verified:

        raise HTTPException(
            status_code=400,
            detail=(
                "This email is already confirmed. "
                "You can log in."
            ),
        )


    if user.auth_provider != "email":

        raise HTTPException(
            status_code=400,
            detail=(
                "This account cannot be confirmed by email. "
                "Use Forgot password on the login page."
            ),
        )


    token = secrets.token_urlsafe(32)

    user.verification_token = token

    db.commit()


    emailed = send_verification_email(
        email,
        user.name or "",
        token,
    )


    return {

        "message": (
            "Confirmation email sent. "
            "Check your inbox."
        ),

        "email_sent": emailed,
    }


# ============================================================
# VERIFY EMAIL
# ============================================================

@router.post(
    "/auth/verify-email"
)
def verify_email(
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(
            User.verification_token
            == body.token.strip()
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or expired "
                "confirmation link."
            ),
        )


    user.email_verified = True

    user.verification_token = None

    db.commit()


    return {

        "message": (
            "Email confirmed. "
            "You can log in now."
        ),

        "email": user.email,
    }


# ============================================================
# FORGOT PASSWORD
# ============================================================

@router.post(
    "/auth/forgot-password"
)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):

    email = (
        body.email
        .lower()
        .strip()
    )


    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=404,
            detail=(
                "No account with this email. "
                "Sign up first."
            ),
        )


    if (
        user.auth_provider == "google"
        and not user.password_hash
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "This account has no password yet. "
                "Use Forgot password to set one."
            ),
        )


    token = secrets.token_urlsafe(32)


    user.reset_token = token

    user.reset_token_expires = (
        datetime.utcnow()
        + timedelta(hours=1)
    )


    db.commit()


    emailed = send_reset_password_email(
        email,
        user.name or "",
        token,
    )


    return {

        "message": (
            "Reset email sent. "
            "Check your inbox."
        ),

        "email_sent": emailed,
    }


# ============================================================
# RESET PASSWORD
# ============================================================

@router.post(
    "/auth/reset-password"
)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):

    if (
        body.password
        != body.confirm_password
    ):

        raise HTTPException(
            status_code=400,
            detail="Passwords do not match.",
        )


    errors = (
        validate_password_strength(
            body.password
        )
    )


    if errors:

        raise HTTPException(
            status_code=400,
            detail=(
                "Password: "
                + ", ".join(errors)
            ),
        )


    user = (
        db.query(User)
        .filter(
            User.reset_token
            == body.token.strip()
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or expired "
                "reset link."
            ),
        )


    if (
        user.reset_token_expires
        and user.reset_token_expires
        < datetime.utcnow()
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Reset link expired. "
                "Request a new one."
            ),
        )


    user.password_hash = hash_password(
        body.password
    )

    user.password = None

    user.reset_token = None

    user.reset_token_expires = None


    db.commit()


    return {

        "message": (
            "Password updated. "
            "You can log in now."
        )
    }


# ============================================================
# GOOGLE AUTH
# ============================================================

@router.post(
    "/auth/google"
)
def auth_google(
    body: GoogleAuthRequest,
    db: Session = Depends(get_db),
):

    try:

        info = verify_google_token(
            body.credential
        )

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=401,
            detail=(
                f"Invalid Google sign-in: {exc}"
            ),
        ) from exc


    # --------------------------------------------------------
    # FIND BY GOOGLE ID
    # --------------------------------------------------------

    user = (
        db.query(User)
        .filter(
            User.google_id
            == info["google_id"]
        )
        .first()
    )


    # --------------------------------------------------------
    # FIND BY EMAIL
    # --------------------------------------------------------

    if not user:

        user = (
            db.query(User)
            .filter(
                User.email
                == info["email"]
            )
            .first()
        )


    # --------------------------------------------------------
    # EXISTING USER
    # --------------------------------------------------------

    if user:

        if not user.google_id:

            user.google_id = (
                info["google_id"]
            )


        user.email_verified = True


        if (
            not user.name
            and info["name"]
        ):

            user.name = info["name"]


        # Preserve existing role
        if not user.role:

            user.role = "user"


        db.commit()

        db.refresh(user)


        return _auth_response(
            user,
            "Signed in with Google",
        )


    # --------------------------------------------------------
    # NEW GOOGLE USER
    # --------------------------------------------------------

    user = User(

        name=info["name"],

        email=info["email"],

        google_id=info["google_id"],

        auth_provider="google",

        email_verified=True,

        password_hash=None,

        role="user",
    )


    db.add(user)

    db.commit()

    db.refresh(user)


    return _auth_response(
        user,
        "Account created with Google",
    )


# ============================================================
# LOGIN
# ============================================================

@router.post("/login")
def login(
    user: LoginRequest,
    db: Session = Depends(get_db),
):

    email = (
        user.email
        .lower()
        .strip()
    )


    existing = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )


    if not existing:

        return {

            "error": (
                "No account with this email. "
                "Sign up first."
            )
        }


    if (
        existing.auth_provider
        == "google"
        and not existing.password_hash
    ):

        return {

            "error": (
                "This account has no password. "
                "Use Forgot password to set one, "
                "or sign up with a new email."
            )
        }


    if not _check_password(
        existing,
        user.password,
    ):

        return {
            "error": "Invalid password."
        }


    # Old users without role
    # become normal users.
    if not existing.role:

        existing.role = "user"


    db.commit()


    return _auth_response(
        existing
    )

# ============================================================
# ADMIN - SETTINGS
# ============================================================

@router.get("/admin/settings")
def get_admin_settings(
    db: Session = Depends(get_db),
):

    settings = (
        db.query(AdminSettings)
        .first()
    )

    if not settings:
        settings = AdminSettings()

        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "id": settings.id,
        "appName": settings.app_name,
        "description": settings.description,
        "aiEnabled": settings.ai_enabled,
        "showSteps": settings.show_steps,
        "allowVoice": settings.allow_voice,
        "emailNotifications": settings.email_notifications,
        "newUserNotifications": settings.new_user_notifications,
        "sessionTimeout": settings.session_timeout,
        "maintenanceMode": settings.maintenance_mode,
    }


@router.put("/admin/settings")
def update_admin_settings(
    payload: dict,
    db: Session = Depends(get_db),
):

    settings = (
        db.query(AdminSettings)
        .first()
    )

    if not settings:
        settings = AdminSettings()
        db.add(settings)

    if "appName" in payload:
        settings.app_name = str(payload["appName"])

    if "description" in payload:
        settings.description = str(payload["description"])

    if "aiEnabled" in payload:
        settings.ai_enabled = bool(payload["aiEnabled"])

    if "showSteps" in payload:
        settings.show_steps = bool(payload["showSteps"])

    if "allowVoice" in payload:
        settings.allow_voice = bool(payload["allowVoice"])

    if "emailNotifications" in payload:
        settings.email_notifications = bool(
            payload["emailNotifications"]
        )

    if "newUserNotifications" in payload:
        settings.new_user_notifications = bool(
            payload["newUserNotifications"]
        )

    if "sessionTimeout" in payload:
        settings.session_timeout = int(
            payload["sessionTimeout"]
        )

    if "maintenanceMode" in payload:
        settings.maintenance_mode = bool(
            payload["maintenanceMode"]
        )

    db.commit()
    db.refresh(settings)

    return {
        "id": settings.id,
        "appName": settings.app_name,
        "description": settings.description,
        "aiEnabled": settings.ai_enabled,
        "showSteps": settings.show_steps,
        "allowVoice": settings.allow_voice,
        "emailNotifications": settings.email_notifications,
        "newUserNotifications": settings.new_user_notifications,
        "sessionTimeout": settings.session_timeout,
        "maintenanceMode": settings.maintenance_mode,
    }




 # ============================================================
# TEMPORARY - PROMOTE TO ADMIN (remove after use)
# ============================================================

@router.post("/admin/promote-temp")
def promote_to_admin_temp(
    email: str,
    secret: str,
    db: Session = Depends(get_db),
):
    import os

    if secret != os.getenv("PROMOTE_SECRET", ""):
        raise HTTPException(status_code=403, detail="Forbidden")

    user = db.query(User).filter(User.email == email.lower().strip()).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = "admin"
    db.commit()

    return {"message": f"{email} is now admin"}