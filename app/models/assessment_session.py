from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    topic = Column(String(40), nullable=False)
    status = Column(String(20), default="active")  # active | completed
    difficulty = Column(Integer, default=2)
    score = Column(Integer, default=0)
    total_questions = Column(Integer, default=5)
    current_index = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    test_date = Column(Date, default=date.today, index=True)
    points_earned = Column(Integer, default=0)
    total_time_seconds = Column(Integer, default=0)
    daily_seed = Column(String(32), nullable=True)

    items = relationship(
        "AssessmentItem",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AssessmentItem.order_index",
    )


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("assessment_sessions.id"), index=True, nullable=False
    )
    order_index = Column(Integer, nullable=False)
    question = Column(String(500), nullable=False)
    expected_answer = Column(String(200), nullable=False)
    user_answer = Column(String(200), nullable=True)
    is_correct = Column(Integer, nullable=True)  # 1/0/None
    difficulty = Column(Integer, default=2)
    time_limit_seconds = Column(Integer, default=60)
    time_taken_seconds = Column(Integer, nullable=True)
    question_started_at = Column(DateTime, nullable=True)

    session = relationship("AssessmentSession", back_populates="items")
