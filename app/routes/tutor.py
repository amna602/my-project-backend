from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ReplyStyle
from app.services.reply_language import normalize_style
from app.services.tutor import process_tutor_message

router = APIRouter(prefix="/tutor", tags=["tutor"])


class TutorAskRequest(BaseModel):
    user_id: int
    thread_id: int
    message: str
    reply_style: ReplyStyle = ReplyStyle.ur_roman


@router.post("/ask")
def tutor_ask(body: TutorAskRequest, db: Session = Depends(get_db)):
    try:
        return process_tutor_message(
            db,
            body.user_id,
            body.thread_id,
            body.message,
            normalize_style(body.reply_style.value),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
