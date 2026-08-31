"""Create all tables and apply column migrations. Safe to run anytime."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Base, engine
from app.db_migrate import run_all_migrations
from app.models.assessment_session import AssessmentItem, AssessmentSession  # noqa: F401
from app.models.chat_message import ChatMessage  # noqa: F401
from app.models.chat_thread import ChatThread  # noqa: F401
from app.models.progress import Progress  # noqa: F401
from app.models.user_skill import UserSkill  # noqa: F401
from app.models.users import User  # noqa: F401


def main() -> None:
    print("Creating missing tables...")
    Base.metadata.create_all(bind=engine)

    changes = run_all_migrations()
    if changes:
        print("Added columns:")
        for col in changes:
            print(f"  + {col}")
    else:
        print("All tables and columns already present.")

    print("\nTables in mathvox.db:")
    import sqlite3

    db_path = ROOT / "mathvox.db"
    conn = sqlite3.connect(db_path)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    for table in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
        print(f"  {table}: {', '.join(cols)}")


if __name__ == "__main__":
    main()
