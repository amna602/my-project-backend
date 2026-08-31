from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ✅ routers
from app.routes.solve import router as solve_router
from app.routes.explain import router as explain_router
from app.routes.skills import router as skills_router
from app.routes.assessment import router as assessment_router
from app.routes.auth import router as auth_router
from app.routes.ocr import router as ocr_router
from app.routes.chat import router as chat_router
from app.routes.threads import router as threads_router
from app.routes.tutor import router as tutor_router
from app.routes.progress_route import router as progress_router

# ✅ database
from app.database import Base, engine

# ✅ IMPORT ALL MODELS
from app.models.users import User
from app.models.progress import Progress
from app.models.chat_thread import ChatThread
from app.models.chat_message import ChatMessage
from app.models.user_skill import UserSkill
from app.models.assessment_session import AssessmentSession, AssessmentItem

# ✅ create tables + migrate missing columns on existing tables
Base.metadata.create_all(bind=engine)
from app.db_migrate import run_all_migrations

_db_changes = run_all_migrations()
if _db_changes:
    print(f"[MathVox] DB migrated: added {', '.join(_db_changes)}")
else:
    print("[MathVox] DB schema up to date")


def _log_email_mode():
    import os

    if os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"):
        print("[MathVox] Email: SMTP enabled (confirmation & reset emails sent)")
    else:
        print(
            "[MathVox] Email: dev mode — links print in this terminal "
            "(set SMTP_HOST + SMTP_USER in .env for real email)"
        )


_log_email_mode()

app = FastAPI()

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "MathVox API running 🚀"}

# ✅ routers
app.include_router(solve_router)
app.include_router(explain_router)
app.include_router(skills_router)
app.include_router(assessment_router)
app.include_router(auth_router)
app.include_router(ocr_router)
app.include_router(chat_router)
app.include_router(threads_router)
app.include_router(tutor_router)
app.include_router(progress_router)