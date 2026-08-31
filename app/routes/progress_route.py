from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.progress import Progress
from app.services.progress_activity import build_progress_activity

router = APIRouter(tags=["progress"])


@router.get("/progress")
def get_progress(user_id: int = Query(...), db: Session = Depends(get_db)):
    prog = db.query(Progress).filter(Progress.user_id == user_id).first()
    if not prog:
        return {
            "total_points": 0,
            "level": 1,
            "level_name": "Beginner",
            "streak": 0,
            "solved_questions": 0,
            "points_to_next_level": 100,
            "next_level_name": "Intermediate",
        }
    level_name = (
        "Pro" if prog.level >= 3 else "Intermediate" if prog.level >= 2 else "Beginner"
    )
    pts = prog.total_points or 0
    if prog.level >= 3:
        points_to_next = 0
        next_name = None
    elif prog.level >= 2:
        points_to_next = max(0, 200 - pts)
        next_name = "Pro"
    else:
        points_to_next = max(0, 100 - pts)
        next_name = "Intermediate"

    return {
        "total_points": pts,
        "level": prog.level or 1,
        "level_name": level_name,
        "streak": prog.streak or 0,
        "solved_questions": prog.solved_questions or 0,
        "points_to_next_level": points_to_next,
        "next_level_name": next_name,
    }


@router.get("/progress/activity")
def progress_activity(user_id: int = Query(...), db: Session = Depends(get_db)):
    if not user_id:
        return {"test_streak": 0, "daily_log": [], "grand_total_points": 0}
    return build_progress_activity(db, user_id)
