import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))


def _send_email(to_email: str, subject: str, body: str, html: str) -> bool:
    if not _smtp_configured():
        print(f"[MathVox DEV] Email to {to_email}")
        print(f"  Subject: {subject}")
        print(f"  {body}")
        return False

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password_smtp = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            if user and password_smtp:
                server.login(user, password_smtp)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True
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
      <p><a href="{link}" style="background:#5d44f8;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;">Confirm email</a></p>
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
      <p><a href="{link}" style="background:#5d44f8;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">Set new password</a></p>
      <p style="font-size:13px;color:#64748b;">Link expires in 1 hour.</p>
    </div>
    """
    return _send_email(to_email, subject, body, html)
