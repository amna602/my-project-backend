import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.getenv("DATABASE_PATH", "./mathvox.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ✅ ADD THIS
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# volume test
# path fix verified
