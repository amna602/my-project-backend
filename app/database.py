from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./mathvox.db"

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