from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ChatMessage(Base):
    """One turn in a thread (user or assistant)."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id"), index=True, nullable=False)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    thread = relationship("ChatThread", back_populates="messages")
