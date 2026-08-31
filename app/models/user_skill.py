from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class UserSkill(Base):
    """Per-user mastery for one math topic (0–100)."""

    __tablename__ = "user_skills"
    __table_args__ = (UniqueConstraint("user_id", "topic", name="uq_user_topic"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    topic = Column(String(40), nullable=False, index=True)
    mastery = Column(Integer, default=0)
    attempts = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
