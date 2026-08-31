"""Apply schema updates for existing SQLite databases.

`Base.metadata.create_all()` only creates missing tables — it does not add new
columns to tables that already exist. This module keeps old databases in sync
with the SQLAlchemy models without wiping data.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import engine

# (column_name, ALTER TABLE fragment after ADD COLUMN)
TABLE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [
        ("name", "name VARCHAR"),
        ("username", "username VARCHAR"),
        ("email", "email VARCHAR"),
        ("password", "password VARCHAR"),
        ("password_hash", "password_hash VARCHAR"),
        ("google_id", "google_id VARCHAR"),
        ("auth_provider", "auth_provider VARCHAR DEFAULT 'email'"),
        ("email_verified", "email_verified BOOLEAN DEFAULT 0"),
        ("verification_token", "verification_token VARCHAR"),
        ("reset_token", "reset_token VARCHAR"),
        ("reset_token_expires", "reset_token_expires TIMESTAMP"),
        ("created_at", "created_at TIMESTAMP"),
    ],
    "history": [
        ("question", "question VARCHAR"),
        ("answer", "answer VARCHAR"),
        ("created_at", "created_at TIMESTAMP"),
        ("user_id", "user_id INTEGER"),
        ("entry_type", "entry_type VARCHAR(20) DEFAULT 'single'"),
        ("problem_count", "problem_count INTEGER DEFAULT 1"),
    ],
    "progress": [
        ("user_id", "user_id INTEGER"),
        ("total_points", "total_points INTEGER DEFAULT 0"),
        ("level", "level INTEGER DEFAULT 1"),
        ("streak", "streak INTEGER DEFAULT 0"),
        ("solved_questions", "solved_questions INTEGER DEFAULT 0"),
        ("last_solve_date", "last_solve_date DATE"),
        ("test_streak", "test_streak INTEGER DEFAULT 0"),
        ("last_test_date", "last_test_date DATE"),
    ],
    "chat_threads": [
        ("user_id", "user_id INTEGER NOT NULL DEFAULT 0"),
        ("title", "title VARCHAR(120) DEFAULT 'New chat'"),
        ("custom_title", "custom_title BOOLEAN DEFAULT 0"),
        ("pinned", "pinned BOOLEAN DEFAULT 0"),
        ("pinned_at", "pinned_at TIMESTAMP"),
        ("last_solved_question", "last_solved_question TEXT"),
        ("last_solved_answer", "last_solved_answer TEXT"),
        ("created_at", "created_at TIMESTAMP"),
        ("updated_at", "updated_at TIMESTAMP"),
    ],
    "assessment_sessions": [
        ("test_date", "test_date DATE"),
        ("points_earned", "points_earned INTEGER DEFAULT 0"),
        ("total_time_seconds", "total_time_seconds INTEGER DEFAULT 0"),
        ("daily_seed", "daily_seed VARCHAR(32)"),
    ],
    "assessment_items": [
        ("time_limit_seconds", "time_limit_seconds INTEGER DEFAULT 60"),
        ("time_taken_seconds", "time_taken_seconds INTEGER"),
        ("question_started_at", "question_started_at TIMESTAMP"),
    ],
    "chat_messages": [
        ("thread_id", "thread_id INTEGER NOT NULL DEFAULT 0"),
        ("role", "role VARCHAR(20) NOT NULL DEFAULT 'user'"),
        ("content", "content TEXT NOT NULL DEFAULT ''"),
        ("created_at", "created_at TIMESTAMP"),
    ],
}


def _add_missing_columns(table_name: str) -> list[str]:
    """Add any columns defined in TABLE_COLUMNS that are missing from table_name."""
    column_defs = TABLE_COLUMNS.get(table_name)
    if not column_defs:
        return []

    insp = inspect(engine)
    if table_name not in insp.get_table_names():
        return []

    existing = {c["name"] for c in insp.get_columns(table_name)}
    added: list[str] = []

    with engine.begin() as conn:
        for col_name, sql_fragment in column_defs:
            if col_name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {sql_fragment}"))
            added.append(f"{table_name}.{col_name}")

    return added


def run_all_migrations() -> list[str]:
    """Run migrations for every app table. Returns list of columns that were added."""
    changes: list[str] = []
    for table_name in TABLE_COLUMNS:
        changes.extend(_add_missing_columns(table_name))
    return changes


# Backwards-compatible names used elsewhere
def migrate_users_table() -> None:
    _add_missing_columns("users")


def migrate_progress_table() -> None:
    _add_missing_columns("progress")
