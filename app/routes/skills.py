from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.assessment_engine import get_recent_sessions, get_test_history, topic_detail
from app.services.skill_profile import build_skill_profile

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/profile")
def skills_profile(user_id: int = Query(...), db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        profile = build_skill_profile(db, user_id)
        profile["recent_assessments"] = get_recent_sessions(db, user_id)
        profile["test_history"] = get_test_history(db, user_id, limit=30)
        return profile
    except Exception:
        db.rollback()
        profile = build_skill_profile(db, user_id)
        profile["recent_assessments"] = []
        profile["test_history"] = []
        return profile


@router.get("/topic/{topic}")
def skills_topic_detail(
    topic: str, user_id: int = Query(...), db: Session = Depends(get_db)
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Login required")
    return topic_detail(db, user_id, topic)
