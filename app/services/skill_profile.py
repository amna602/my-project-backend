"""Update and read per-user skill mastery."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from sqlalchemy import func

from app.models.assessment_session import AssessmentSession
from app.models.user_skill import UserSkill
from app.services.skill_classifier import classify_topic
from app.services.skill_formulas import mastery_to_level_band
from app.services.skill_topics import SKILL_TOPICS
from app.services.test_streak import streak_status

MASTERY_GAIN_CORRECT = 8
MASTERY_LOSS_WRONG = 12
QUIZ_GAIN_CORRECT = 15
QUIZ_LOSS_WRONG = 10


def _get_or_create_skill(db: Session, user_id: int, topic: str) -> UserSkill:
    row = (
        db.query(UserSkill)
        .filter(UserSkill.user_id == user_id, UserSkill.topic == topic)
        .first()
    )
    if not row:
        row = UserSkill(user_id=user_id, topic=topic, mastery=0)
        db.add(row)
        db.flush()
    return row


def update_mastery(
    db: Session,
    user_id: int,
    topic: str,
    *,
    correct: bool,
    from_quiz: bool = False,
) -> UserSkill:
    topic = topic if topic in SKILL_TOPICS else "other"
    row = _get_or_create_skill(db, user_id, topic)
    row.attempts = (row.attempts or 0) + 1
    if correct:
        row.correct_count = (row.correct_count or 0) + 1
        delta = QUIZ_GAIN_CORRECT if from_quiz else MASTERY_GAIN_CORRECT
        row.mastery = min(100, (row.mastery or 0) + delta)
    else:
        row.wrong_count = (row.wrong_count or 0) + 1
        delta = QUIZ_LOSS_WRONG if from_quiz else MASTERY_LOSS_WRONG
        row.mastery = max(0, (row.mastery or 0) - delta)
    row.updated_at = datetime.utcnow()
    return row


def record_practice_from_solve(
    db: Session, user_id: int, question: str, *, success: bool
) -> str | None:
    if not user_id or not question:
        return None
    topic = classify_topic(question)
    update_mastery(db, user_id, topic, correct=success, from_quiz=False)
    return topic


def overall_band(avg_mastery: float) -> str:
    if avg_mastery >= 75:
        return "Advanced"
    if avg_mastery >= 50:
        return "Proficient"
    if avg_mastery >= 25:
        return "Developing"
    return "Starter"


def _topic_points_map(db: Session, user_id: int) -> dict[str, int]:
    rows = (
        db.query(AssessmentSession.topic, func.sum(AssessmentSession.points_earned))
        .filter(
            AssessmentSession.user_id == user_id,
            AssessmentSession.status == "completed",
        )
        .group_by(AssessmentSession.topic)
        .all()
    )
    return {t: int(p or 0) for t, p in rows}


def build_skill_profile(db: Session, user_id: int) -> dict:
    rows = db.query(UserSkill).filter(UserSkill.user_id == user_id).all()
    points_map = _topic_points_map(db, user_id)
    by_topic = {t: 0 for t in SKILL_TOPICS}
    for r in rows:
        by_topic[r.topic] = r.mastery or 0

    skills = []
    for key, label in SKILL_TOPICS.items():
        if key == "other":
            continue
        r = next((x for x in rows if x.topic == key), None)
        mastery = by_topic[key]
        skills.append(
            {
                "topic": key,
                "label": label,
                "mastery": mastery,
                "level_band": mastery_to_level_band(mastery),
                "topic_points": points_map.get(key, 0),
                "attempts": (r.attempts or 0) if r else 0,
                "correct_count": (r.correct_count or 0) if r else 0,
                "wrong_count": (r.wrong_count or 0) if r else 0,
            }
        )

    practiced = [s for s in skills if s["attempts"] > 0]
    if practiced:
        avg = sum(s["mastery"] for s in practiced) / len(practiced)
    else:
        avg = 0.0

    weakest = min(skills, key=lambda s: s["mastery"])
    strongest = max(skills, key=lambda s: s["mastery"])

    weak_list = sorted(
        [s for s in skills if s["mastery"] < 50],
        key=lambda s: s["mastery"],
    )[:3]

    tips = _recommendation(weakest["topic"], weakest["mastery"], weak_list)
    streak = streak_status(db, user_id)

    from app.models.progress import Progress

    prog = db.query(Progress).filter(Progress.user_id == user_id).first()
    total_points = prog.total_points if prog else 0

    return {
        "skills": skills,
        "total_points": total_points,
        **streak,
        "overall_mastery": round(avg, 1),
        "overall_band": overall_band(avg),
        "weakest_topic": weakest["topic"],
        "weakest_label": weakest["label"],
        "weakest_mastery": weakest["mastery"],
        "strongest_topic": strongest["topic"],
        "strongest_label": strongest["label"],
        "strongest_mastery": strongest["mastery"],
        "weak_topics": [
            {"topic": s["topic"], "label": s["label"], "mastery": s["mastery"]}
            for s in weak_list
        ],
        "recommendation": tips,
    }


def _recommendation(weakest_topic: str, mastery: int, weak_list: list) -> str:
    label = SKILL_TOPICS.get(weakest_topic, weakest_topic)
    if mastery == 0 and not weak_list:
        return (
            "You have not tested yet — do a 5-question skill check today or your streak will stay at zero."
        )
    parts = [
        f"⚠️ {label} is still weak ({mastery}% mastery). Do a skill check on it today — do not skip it."
    ]
    if len(weak_list) > 1:
        others = ", ".join(w["label"] for w in weak_list[1:])
        parts.append(f"Also dragging you down: {others}. Fix these before moving on.")
    parts.append("Tap the red topic card below and start a skill check now.")
    return " ".join(parts)


def pick_weakest_topic(db: Session, user_id: int) -> str:
    profile = build_skill_profile(db, user_id)
    return profile["weakest_topic"]
