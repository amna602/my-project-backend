import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from openai import OpenAI

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


def is_addressed_to_tutor(message: str) -> bool:
    """Pass 1 Intent Filter: Uses gpt-4o-mini to check if the message is 

    directed at the tutor or is background cross-talk.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent filter for an AI tutor. Analyze the incoming text transcribed from audio.\n"
                        "Determine if the user is addressing the AI tutor (asking a question, seeking help, explaining, replying to tutor) "
                        "or if it is background noise, cross-talk, or spoken to another person in the physical room.\n\n"
                        "Rules:\n"
                        "- Respond strictly with '[ANSWER]' if the text is directed to the tutor.\n"
                        "- Respond strictly with '[IGNORE]' if it is side conversation or directed to someone else in the room."
                    ),
                },
                {"role": "user", "content": message},
            ],
        )

        result = response.choices[0].message.content.strip()
        return result == "[ANSWER]"
    except Exception as exc:
        # Fallback: Default to True on failure so valid questions are never blocked
        print(f"Intent filter error: {exc}")
        return True


@router.post("/ask")
def tutor_ask(body: TutorAskRequest, db: Session = Depends(get_db)):
    try:
        # 1. Filter out background talk before running main logic
        if not is_addressed_to_tutor(body.message):
            return {
                "status": "ignored",
                "message": "Background audio ignored.",
                "reply": None,
            }

        # 2. Run your existing tutor logic if the intent is valid
        reply = process_tutor_message(
            db,
            body.user_id,
            body.thread_id,
            body.message,
            normalize_style(body.reply_style.value),
        )
        return {"status": "success", "reply": reply}

    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc