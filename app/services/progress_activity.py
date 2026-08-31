"""Daily progress log from completed skill checks."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.services.assessment_engine import get_test_history
from app.services.test_streak import streak_status


def build_progress_activity(db: Session, user_id: int, *, limit: int = 100) -> dict:
    streak = streak_status(db, user_id)
    rows = get_test_history(db, user_id, limit=limit)

    by_date: dict[str, dict] = defaultdict(
        lambda: {
            "date": "",
            "total_points": 0,
            "total_time_seconds": 0,
            "exercise_count": 0,
            "exercises": [],
        }
    )

    for row in rows:
        day = row.get("test_date") or ""
        if not day and row.get("finished_at"):
            day = str(row["finished_at"])[:10]
        if not day:
            continue
        bucket = by_date[day]
        bucket["date"] = day
        bucket["total_points"] += row.get("points_earned") or 0
        bucket["total_time_seconds"] += row.get("total_time_seconds") or 0
        bucket["exercise_count"] += 1
        bucket["exercises"].append(
            {
                "session_id": row["session_id"],
                "topic": row["topic"],
                "topic_label": row["topic_label"],
                "score": row["score"],
                "total": row["total"],
                "points_earned": row.get("points_earned") or 0,
                "total_time_seconds": row.get("total_time_seconds") or 0,
            }
        )

    daily_log = sorted(by_date.values(), key=lambda d: d["date"], reverse=True)
    grand_total = sum(d["total_points"] for d in daily_log)

    return {
        **streak,
        "grand_total_points": grand_total,
        "daily_log": daily_log,
    }
