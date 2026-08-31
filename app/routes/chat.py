from fastapi import APIRouter, HTTPException

from app.schemas import ChatRequest, ReplyStyle
from app.services.llm_client import chat_with_history
from app.services.reply_language import normalize_style, resolve_reply_style

router = APIRouter()


@router.post("/chat")
def chat_discuss(request: ChatRequest):
    message = (request.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    history = [
        {"role": t.role, "text": t.text}
        for t in request.history
        if t.text and t.text.strip()
    ]

    style, _ = resolve_reply_style(message, normalize_style(request.reply_style.value))

    try:
        reply = chat_with_history(message, history, style)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not reply:
        raise HTTPException(status_code=502, detail="Empty response from tutor.")

    return {"reply": reply}
