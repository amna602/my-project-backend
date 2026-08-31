from sqlalchemy import Column, Date, ForeignKey, Integer

from app.database import Base


class Progress(Base):
    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"))

    total_points = Column(Integer, default=0)

    level = Column(Integer, default=1)

    streak = Column(Integer, default=0)

    solved_questions = Column(Integer, default=0)

    last_solve_date = Column(Date, nullable=True)

    # Daily skill-check streak (Snapchat-style)
    test_streak = Column(Integer, default=0)
    last_test_date = Column(Date, nullable=True)