from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import assessment_engine
from app.services.skill_topics import SKILL_TOPICS

router = APIRouter(prefix="/assessment", tags=["assessment"])


class AssessmentStartRequest(BaseModel):
    user_id: int
    topic: str | None = None


class AssessmentAnswerRequest(BaseModel):
    user_id: int
    session_id: int
    answer: str
    time_taken_seconds: int | None = None


@router.get("/topics")
def list_topics():
    return {
        "topics": [
            {"id": k, "label": v} for k, v in SKILL_TOPICS.items() if k != "other"
        ]
    }


@router.post("/start")
def start_assessment(body: AssessmentStartRequest, db: Session = Depends(get_db)):
    if not body.user_id:
        raise HTTPException(status_code=401, detail="Login required")
    if body.topic and body.topic not in SKILL_TOPICS:
        raise HTTPException(status_code=400, detail="Invalid topic")
    try:
        return assessment_engine.start_session(db, body.user_id, body.topic)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/answer")
def answer_assessment(body: AssessmentAnswerRequest, db: Session = Depends(get_db)):
    if not body.user_id:
        raise HTTPException(status_code=401, detail="Login required")
    try:
        return assessment_engine.submit_answer(
            db,
            body.user_id,
            body.session_id,
            body.answer,
            body.time_taken_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
