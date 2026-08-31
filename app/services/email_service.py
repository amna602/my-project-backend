import os
import requests


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _resend_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY"))


def _send_email(to_email: str, subject: str, body: str, html: str) -> bool:
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        print(f"[MathVox DEV] Email to {to_email}")
        print(f"  Subject: {subject}")
        print(f"  {body}")
        return False

    from_addr = os.getenv("SMTP_FROM") or "MathVox <onboarding@resend.dev>"

    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body,
        "html": html,
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )

        if response.ok:
            print(f"[MathVox] Email sent successfully to {to_email}")
            return True

        print(
            f"[MathVox] Resend email failed: "
            f"{response.status_code} {response.text}"
        )
        return False

    except Exception as exc:
        print(f"[MathVox] Email send failed: {exc}")
        return False


def send_verification_email(to_email: str, name: str, token: str) -> bool:
    link = f"{_frontend_url()}/verify-email?token={token}"
    subject = "Confirm your MathVox email"

    body = f"""Hi {name or "there"},

Thanks for signing up for MathVox!

Please confirm your email by opening this link:
{link}

If you did not create an account, ignore this email.

— MathVox
"""

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;">
      <h2 style="color:#5d44f8;">Confirm your email</h2>
      <p>Hi {name or "there"},</p>
      <p>Click below to verify your MathVox account:</p>
      <p>
        <a href="{link}"
           style="background:#5d44f8;color:white;padding:12px 24px;
                  border-radius:8px;text-decoration:none;display:inline-block;">
          Confirm email
        </a>
      </p>
      <p style="font-size:13px;color:#64748b;">Or copy: {link}</p>
    </div>
    """

    return _send_email(to_email, subject, body, html)


def send_reset_password_email(to_email: str, name: str, token: str) -> bool:
    link = f"{_frontend_url()}/reset-password?token={token}"
    subject = "Reset your MathVox password"

    body = f"""Hi {name or "there"},

We received a request to reset your password.

Open this link (valid for 1 hour):
{link}

If you did not request this, ignore this email.

— MathVox
"""

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;">
      <h2 style="color:#5d44f8;">Reset password</h2>
      <p>
        <a href="{link}"
           style="background:#5d44f8;color:white;padding:12px 24px;
                  border-radius:8px;text-decoration:none;">
          Set new password
        </a>
      </p>
      <p style="font-size:13px;color:#64748b;">
        Link expires in 1 hour.
      </p>
    </div>
    """

    return _send_email(to_email, subject, body, html)
