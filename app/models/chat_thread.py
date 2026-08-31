from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ChatThread(Base):
    """One conversation (like a ChatGPT chat)."""

    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(120), default="New chat")
    custom_title = Column(Boolean, default=False)
    pinned = Column(Boolean, default=False)
    pinned_at = Column(DateTime, nullable=True)
    last_solved_question = Column(Text, nullable=True)
    last_solved_answer = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )
