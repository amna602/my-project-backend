from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread

router = APIRouter(prefix="/threads", tags=["threads"])

MAX_PINNED = 3


class ThreadCreate(BaseModel):
    user_id: int
    title: str | None = "New chat"


class ThreadPatch(BaseModel):
    user_id: int
    title: str | None = None
    pinned: bool | None = None


def _thread_summary(t: ChatThread, db: Session) -> dict:
    last_user = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == t.id, ChatMessage.role == "user")
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    preview = (last_user.content[:60] + "…") if last_user and len(last_user.content) > 60 else (
        (last_user.content if last_user else "") or ""
    )
    return {
        "id": t.id,
        "title": t.title or "New chat",
        "pinned": bool(t.pinned),
        "updatedAt": int(t.updated_at.timestamp() * 1000) if t.updated_at else 0,
        "preview": preview,
    }


@router.get("")
def list_threads(user_id: int = Query(...), db: Session = Depends(get_db)):
    threads = (
        db.query(ChatThread)
        .filter(ChatThread.user_id == user_id)
        .order_by(ChatThread.pinned.desc(), ChatThread.updated_at.desc())
        .all()
    )
    pinned = sum(1 for t in threads if t.pinned)
    return {
        "threads": [_thread_summary(t, db) for t in threads],
        "pinned_count": pinned,
        "max_pinned": MAX_PINNED,
    }


@router.post("")
def create_thread(body: ThreadCreate, db: Session = Depends(get_db)):
    thread = ChatThread(user_id=body.user_id, title=body.title or "New chat")
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return {"id": thread.id, "title": thread.title}


@router.get("/{thread_id}")
def get_thread(
    thread_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
):
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    last_solved = None
    if thread.last_solved_question:
        last_solved = {
            "question": thread.last_solved_question,
            "answer": thread.last_solved_answer,
        }

    return {
        "id": thread.id,
        "title": thread.title,
        "pinned": bool(thread.pinned),
        "messages": [
            {
                "type": "user" if m.role == "user" else "bot",
                "text": m.content,
            }
            for m in messages
        ],
        "lastSolved": last_solved,
    }


@router.patch("/{thread_id}")
def patch_thread(
    thread_id: int,
    body: ThreadPatch,
    db: Session = Depends(get_db),
):
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == body.user_id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if body.title is not None:
        title = body.title.strip()[:120]
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        thread.title = title
        thread.custom_title = True

    if body.pinned is not None:
        if body.pinned:
            count = (
                db.query(ChatThread)
                .filter(
                    ChatThread.user_id == body.user_id,
                    ChatThread.pinned.is_(True),
                    ChatThread.id != thread_id,
                )
                .count()
            )
            if count >= MAX_PINNED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum {MAX_PINNED} pinned chats",
                )
            thread.pinned = True
            thread.pinned_at = datetime.utcnow()
        else:
            thread.pinned = False
            thread.pinned_at = None

    db.commit()
    db.refresh(thread)
    return _thread_summary(thread, db)


@router.delete("/{thread_id}")
def delete_thread(
    thread_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db),
):
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"ok": True}
