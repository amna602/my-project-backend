"""Timed skill checks, daily streak, points, test history."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.assessment_session import AssessmentItem, AssessmentSession
from app.models.progress import Progress
from app.services.skill_formulas import compute_test_points, mastery_to_level_band
from app.services.skill_profile import pick_weakest_topic, update_mastery, build_skill_profile
from app.services.skill_topics import QUESTIONS_PER_TEST, SKILL_TOPICS
from app.services.solver import solve_math
from app.services.test_streak import record_daily_test_completed, streak_status

_FALLBACK: dict[tuple[str, int], list[tuple[str, str]]] = {
    ("arithmetic", 1): [("7 + 5", "12"), ("9 - 4", "5"), ("3 * 6", "18"), ("8 + 9", "17")],
    ("arithmetic", 2): [("24 / 6", "4"), ("15 + 28", "43"), ("81 - 37", "44")],
    ("fractions", 1): [("1/2 + 1/4", "3/4"), ("3/4 - 1/4", "1/2"), ("2/5 + 1/5", "3/5")],
    ("fractions", 2): [("2/3 + 1/6", "5/6"), ("5/6 - 1/3", "1/2")],
    ("linear_equations", 1): [("x + 3 = 10", "7"), ("2*x = 14", "7"), ("x - 4 = 6", "10")],
    ("linear_equations", 2): [("3*x - 5 = 10", "5"), ("x/4 = 3", "12")],
    ("decimals", 1): [("1.5 + 2.3", "3.8"), ("5.0 - 1.2", "3.8")],
    ("quadratics", 2): [("x**2 = 16", "4"), ("x**2 - 9 = 0", "3")],
    ("word_problems", 1): [("Ali has 5 apples and buys 3 more. How many?", "8")],
    ("other", 1): [("4 + 4", "8"), ("10 - 3", "7")],
}


def _daily_seed(user_id: int, topic: str, day: date | None = None) -> str:
    d = day or date.today()
    raw = f"{user_id}:{d.isoformat()}:{topic}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _normalize_answer(val: str) -> str:
    return re.sub(r"\s+", "", (val or "").strip().lower())


def grade_answer(expected: str, user_answer: str) -> tuple[bool, str]:
    user = (user_answer or "").strip()
    if not user:
        return False, expected
    if _normalize_answer(user) == _normalize_answer(expected):
        return True, expected
    exp_solve = solve_math(expected)
    usr_solve = solve_math(user)
    exp_ans = exp_solve.get("answer")
    usr_ans = usr_solve.get("answer")
    if exp_ans and usr_ans:
        if _normalize_answer(str(exp_ans)) == _normalize_answer(str(usr_ans)):
            return True, str(exp_ans)
        try:
            if abs(float(exp_ans) - float(usr_ans)) < 1e-6:
                return True, str(exp_ans)
        except (TypeError, ValueError):
            pass
    return False, exp_ans or expected


def generate_question(topic: str, difficulty: int, seed: str) -> tuple[str, str]:
    topic = topic if topic in SKILL_TOPICS else "other"
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(seed + f":{difficulty}:{random.randint(0, 9999)}")

    if os.getenv("GROQ_API_KEY"):
        try:
            return _generate_with_groq(topic, difficulty, seed)
        except Exception:
            pass

    pool = _FALLBACK.get((topic, difficulty)) or _FALLBACK.get((topic, 1)) or _FALLBACK[("other", 1)]
    return rng.choice(pool)


def _generate_with_groq(topic: str, difficulty: int, seed: str) -> tuple[str, str]:
    from groq import Groq

    label = SKILL_TOPICS.get(topic, topic)
    prompt = f"""Generate ONE unique math practice problem.
Topic: {label}
Difficulty: {difficulty} (1=easy, 5=hard)
Daily variation id: {seed}
Return JSON only:
{{"question": "...", "answer": "SymPy-ready answer"}}
No steps."""

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
    )
    raw = completion.choices[0].message.content or "{}"
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    q = (data.get("question") or "").strip()
    a = (data.get("answer") or "").strip()
    if not q or not a:
        raise ValueError("invalid_question")
    return q, a


def _active_session(db: Session, user_id: int) -> AssessmentSession | None:
    return (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.user_id == user_id,
            AssessmentSession.status == "active",
        )
        .order_by(AssessmentSession.id.desc())
        .first()
    )


def _question_payload(item: AssessmentItem, session: AssessmentSession) -> dict:
    return {
        "question": item.question,
        "index": item.order_index,
        "total": session.total_questions,
        "difficulty": item.difficulty,
        "topic_label": SKILL_TOPICS.get(session.topic, session.topic),
    }


def start_session(db: Session, user_id: int, topic: str | None = None) -> dict:
    if not topic or topic not in SKILL_TOPICS:
        topic = pick_weakest_topic(db, user_id)
    if topic == "other":
        topic = pick_weakest_topic(db, user_id)

    active = _active_session(db, user_id)
    if active:
        active.status = "abandoned"
        active.finished_at = datetime.utcnow()

    difficulty = 2
    seed = _daily_seed(user_id, topic)
    today = date.today()

    session = AssessmentSession(
        user_id=user_id,
        topic=topic,
        status="active",
        difficulty=difficulty,
        total_questions=QUESTIONS_PER_TEST,
        current_index=0,
        score=0,
        test_date=today,
        daily_seed=seed,
    )
    db.add(session)
    db.flush()

    q, a = generate_question(topic, difficulty, f"{seed}:q1")
    now = datetime.utcnow()
    item = AssessmentItem(
        session_id=session.id,
        order_index=1,
        question=q,
        expected_answer=a,
        difficulty=difficulty,
        time_limit_seconds=None,
        question_started_at=now,
    )
    db.add(item)
    db.commit()
    db.refresh(session)

    streak = streak_status(db, user_id)
    return {
        "session_id": session.id,
        "topic": topic,
        "topic_label": SKILL_TOPICS.get(topic, topic),
        "test_date": today.isoformat(),
        "daily_seed": seed,
        **streak,
        **_question_payload(item, session),
    }


def submit_answer(
    db: Session,
    user_id: int,
    session_id: int,
    user_answer: str,
    time_taken_seconds: int | None = None,
) -> dict:
    session = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.id == session_id,
            AssessmentSession.user_id == user_id,
        )
        .first()
    )
    if not session or session.status != "active":
        raise ValueError("No active assessment session")

    item = (
        db.query(AssessmentItem)
        .filter(
            AssessmentItem.session_id == session.id,
            AssessmentItem.order_index == session.current_index + 1,
        )
        .first()
    )
    if not item:
        raise ValueError("Question not found")

    taken = time_taken_seconds
    if taken is None and item.question_started_at:
        taken = int((datetime.utcnow() - item.question_started_at).total_seconds())
    taken = max(0, int(taken or 0))
    item.time_taken_seconds = taken

    correct, canonical = grade_answer(item.expected_answer, user_answer)
    item.user_answer = user_answer.strip()[:200]
    item.is_correct = 1 if correct else 0
    if correct:
        session.score = (session.score or 0) + 1
    session.total_time_seconds = (session.total_time_seconds or 0) + taken

    update_mastery(db, user_id, session.topic, correct=correct, from_quiz=True)

    if correct and session.difficulty < 5:
        session.difficulty += 1
    elif not correct and session.difficulty > 1:
        session.difficulty -= 1

    session.current_index = (session.current_index or 0) + 1
    finished = session.current_index >= session.total_questions

    result = {
        "correct": correct,
        "expected_answer": canonical,
        "time_taken_seconds": taken,
        "index": session.current_index,
        "total": session.total_questions,
        "score_so_far": session.score,
        "finished": finished,
    }

    if finished:
        session.status = "completed"
        session.finished_at = datetime.utcnow()
        result["summary"] = _finalize_session(db, user_id, session)
        db.commit()
        return result

    seed = session.daily_seed or _daily_seed(user_id, session.topic)
    q, a = generate_question(
        session.topic, session.difficulty, f"{seed}:q{session.current_index + 1}"
    )
    now = datetime.utcnow()
    next_item = AssessmentItem(
        session_id=session.id,
        order_index=session.current_index + 1,
        question=q,
        expected_answer=a,
        difficulty=session.difficulty,
        time_limit_seconds=None,
        question_started_at=now,
    )
    db.add(next_item)
    db.commit()

    payload = _question_payload(next_item, session)
    payload["index"] = next_item.order_index
    result.update(payload)
    return result


def _finalize_session(db: Session, user_id: int, session: AssessmentSession) -> dict:
    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.session_id == session.id)
        .order_by(AssessmentItem.order_index)
        .all()
    )
    times = [i.time_taken_seconds or 0 for i in items]
    avg_time = sum(times) / len(times) if times else 0

    from app.models.user_skill import UserSkill

    us = (
        db.query(UserSkill)
        .filter(UserSkill.user_id == user_id, UserSkill.topic == session.topic)
        .first()
    )
    mastery = us.mastery if us else 0
    band = mastery_to_level_band(mastery)

    total = session.total_questions or QUESTIONS_PER_TEST
    score = session.score or 0
    pct = round(100 * score / total) if total else 0
    points = compute_test_points(score, total, band, avg_time)
    session.points_earned = points

    prog = db.query(Progress).filter(Progress.user_id == user_id).first()
    if not prog:
        prog = Progress(user_id=user_id)
        db.add(prog)
    prog.total_points = (prog.total_points or 0) + points
    if prog.total_points >= 200:
        prog.level = 3
    elif prog.total_points >= 100:
        prog.level = 2
    else:
        prog.level = 1

    streak_info = record_daily_test_completed(db, user_id)
    topic_label = SKILL_TOPICS.get(session.topic, session.topic)

    if pct >= 80:
        msg = f"Strong in {topic_label}! Speed: {round(avg_time)}s per question avg."
    elif pct >= 60:
        msg = f"Good work in {topic_label}. Practice weak areas in chat."
    else:
        msg = f"Keep going on {topic_label} — tap the topic below for tips."

    return {
        "score": score,
        "total": total,
        "percent": pct,
        "topic": session.topic,
        "topic_label": topic_label,
        "topic_level": band,
        "points_earned": points,
        "total_time_seconds": session.total_time_seconds,
        "avg_time_seconds": round(avg_time, 1),
        "message": msg,
        "streak": streak_info,
        "test_date": session.test_date.isoformat() if session.test_date else None,
    }


def get_test_history(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    rows = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.user_id == user_id,
            AssessmentSession.status == "completed",
        )
        .order_by(AssessmentSession.finished_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for s in rows:
        total = s.total_questions or QUESTIONS_PER_TEST
        out.append(
            {
                "session_id": s.id,
                "topic": s.topic,
                "topic_label": SKILL_TOPICS.get(s.topic, s.topic),
                "score": s.score or 0,
                "total": total,
                "percent": round(100 * (s.score or 0) / total) if total else 0,
                "points_earned": s.points_earned or 0,
                "total_time_seconds": s.total_time_seconds or 0,
                "test_date": s.test_date.isoformat() if s.test_date else None,
                "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            }
        )
    return out


def get_recent_sessions(db: Session, user_id: int, limit: int = 5) -> list[dict]:
    return get_test_history(db, user_id, limit)


def topic_detail(db: Session, user_id: int, topic: str) -> dict:
    from app.models.user_skill import UserSkill

    if topic not in SKILL_TOPICS:
        topic = "other"
    us = (
        db.query(UserSkill)
        .filter(UserSkill.user_id == user_id, UserSkill.topic == topic)
        .first()
    )
    mastery = us.mastery if us else 0
    band = mastery_to_level_band(mastery)
    history = [
        h
        for h in get_test_history(db, user_id, 30)
        if h["topic"] == topic
    ][:10]

    tips = {
        "arithmetic": "Practice mental math daily. Start with small numbers, then mix operations.",
        "fractions": "Make denominators the same before adding. Draw pie charts to visualize.",
        "decimals": "Line up decimal points when adding. Multiply as whole numbers, then place the dot.",
        "linear_equations": "Do the same operation on both sides. Isolate x step by step.",
        "quadratics": "Factor when possible, or use the quadratic formula. Check solutions by substituting back.",
        "word_problems": "Underline numbers and what is asked. Write an equation before solving.",
        "other": "Solve in chat and ask for step-by-step explanations.",
    }

    return {
        "topic": topic,
        "label": SKILL_TOPICS.get(topic, topic),
        "mastery": mastery,
        "level_band": band,
        "attempts": us.attempts if us else 0,
        "correct_count": us.correct_count if us else 0,
        "wrong_count": us.wrong_count if us else 0,
        "improvement_tip": tips.get(topic, tips["other"]),
        "test_history": history,
        "is_weakest": topic == build_skill_profile(db, user_id).get("weakest_topic"),
    }
