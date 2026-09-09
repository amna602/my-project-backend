from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base


class AdminSettings(Base):
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)

    app_name = Column(String, nullable=False, default="MathVox")
    description = Column(
        String,
        nullable=False,
        default="AI-powered mathematics learning platform."
    )

    ai_enabled = Column(Boolean, nullable=False, default=True)
    show_steps = Column(Boolean, nullable=False, default=True)
    allow_voice = Column(Boolean, nullable=False, default=True)

    email_notifications = Column(Boolean, nullable=False, default=True)
    new_user_notifications = Column(Boolean, nullable=False, default=True)

    session_timeout = Column(Integer, nullable=False, default=30)
    maintenance_mode = Column(Boolean, nullable=False, default=False)
