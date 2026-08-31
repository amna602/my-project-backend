"""Daily test streak — like Snapchat: complete one full skill check per day."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.progress import Progress


def _get_progress(db: Session, user_id: int, *, create: bool = False) -> Progress | None:
    prog = db.query(Progress).filter(Progress.user_id == user_id).first()
    if not prog and create:
        prog = Progress(user_id=user_id, test_streak=0)
        db.add(prog)
        db.flush()
    return prog


def streak_status(db: Session, user_id: int) -> dict:
    prog = _get_progress(db, user_id, create=False)
    if not prog:
        return {
            "test_streak": 0,
            "last_test_date": None,
            "completed_test_today": False,
            "streak_at_risk": False,
            "streak_broken": False,
        }
    today = date.today()
    last = prog.last_test_date
    streak = prog.test_streak or 0

    completed_today = last == today
    at_risk = (
        streak > 0
        and last is not None
        and last < today
        and last == today - timedelta(days=1)
    )
    broken = streak > 0 and last is not None and last < today - timedelta(days=1)

    return {
        "test_streak": streak,
        "last_test_date": last.isoformat() if last else None,
        "completed_test_today": completed_today,
        "streak_at_risk": at_risk and not completed_today,
        "streak_broken": broken,
    }


def record_daily_test_completed(db: Session, user_id: int) -> dict:
    """Call when user finishes a full 5-question skill check."""
    prog = _get_progress(db, user_id, create=True)
    today = date.today()
    last = prog.last_test_date

    if last == today:
        new_streak = prog.test_streak or 1
    elif last == today - timedelta(days=1):
        new_streak = (prog.test_streak or 0) + 1
    else:
        new_streak = 1

    prog.test_streak = new_streak
    prog.last_test_date = today
    # Legacy streak field mirrors test streak for UI
    prog.streak = new_streak
    prog.last_solve_date = today

    return {
        "test_streak": new_streak,
        "last_test_date": today.isoformat(),
        "completed_test_today": True,
        "streak_increased": last != today,
    }
