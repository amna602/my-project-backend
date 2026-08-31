"""Record practice outcomes: skill mastery + gamification progress (no history table)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.progress import Progress
from app.services.skill_profile import record_practice_from_solve

MATH_SIGNAL = re.compile(
    r"(\d\s*[+\-*/^=]|[+\-*/^=]\s*\d|=\s*\d|\d+\s*[xX]\s*\d|sqrt|sin|cos|tan|\^)",
    re.I,
)
CHAT_ONLY = re.compile(
    r"^(hi+|hello|hey|ok+|thanks|thank you|yo|salam|assalam|kia hal)\b",
    re.I,
)
WORKSHEET_BATCH_MIN = 3
POINTS_SINGLE = 10
POINTS_PER_WORKSHEET_PROBLEM = 5
POINTS_WORKSHEET_CAP = 40


def is_recordable_math(question: str, answer: str | None) -> bool:
    q = (question or "").strip()
    a = (answer or "").strip()
    if not q or not a or len(q) < 3:
        return False
    if a.lower().startswith("could not") or "error" in a.lower()[:40]:
        return False
    if CHAT_ONLY.match(q) and len(q) < 40:
        return False
    if not re.search(r"\d", q):
        return False
    if not MATH_SIGNAL.search(q) and not MATH_SIGNAL.search(a):
        return False
    return True


def _get_or_create_progress(db: Session, user_id: int) -> Progress:
    prog = db.query(Progress).filter(Progress.user_id == user_id).first()
    if not prog:
        prog = Progress(user_id=user_id)
        db.add(prog)
        db.flush()
    return prog


def _apply_progress(prog: Progress, problems_count: int, points: int) -> None:
    today = date.today()
    last = prog.last_solve_date
    if last is None:
        prog.streak = 1
    elif last == today:
        pass
    elif last == today - timedelta(days=1):
        prog.streak = (prog.streak or 0) + 1
    else:
        prog.streak = 1
    prog.last_solve_date = today
    prog.solved_questions = (prog.solved_questions or 0) + problems_count
    prog.total_points = (prog.total_points or 0) + points
    if prog.total_points >= 200:
        prog.level = 3
    elif prog.total_points >= 100:
        prog.level = 2
    else:
        prog.level = 1


def _record_one(db: Session, user_id: int, question: str, answer: str) -> None:
    if not is_recordable_math(question, answer):
        return
    record_practice_from_solve(db, user_id, question, success=True)
    prog = _get_or_create_progress(db, user_id)
    _apply_progress(prog, 1, POINTS_SINGLE)


def record_solve_result(
    db: Session,
    user_id: int,
    result: dict,
    fallback_question: str = "",
) -> None:
    if not user_id:
        return

    rows = result.get("results") or []
    solved_rows = [r for r in rows if r.get("answer") and not r.get("error")]

    if len(solved_rows) >= WORKSHEET_BATCH_MIN:
        n = 0
        for row in solved_rows:
            q, a = row.get("question", ""), row.get("answer", "")
            if is_recordable_math(q, a):
                record_practice_from_solve(db, user_id, q, success=True)
                n += 1
        if n:
            points = min(POINTS_WORKSHEET_CAP, n * POINTS_PER_WORKSHEET_PROBLEM)
            prog = _get_or_create_progress(db, user_id)
            _apply_progress(prog, n, points)
        return

    if solved_rows:
        for row in solved_rows:
            _record_one(db, user_id, row["question"], row["answer"])
        return

    if result.get("answer"):
        q = (result.get("question") or fallback_question or "").strip()
        _record_one(db, user_id, q, result["answer"])
