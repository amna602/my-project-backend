from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP
from app.database import Base
import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    username = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    google_id = Column(String, unique=True, nullable=True, index=True)
    auth_provider = Column(String, default="email")
    email_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True, index=True)
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.datetime.utcnow)
