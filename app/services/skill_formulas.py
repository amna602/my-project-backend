"""
Skill assessment formulas (documented for students & devs).

TOPIC LEVEL (from mastery %):
  0–24   → Beginner
  25–49  → Developing
  50–74  → Proficient
  75–100 → Advanced

MASTERY updates (per answer):
  Chat solve correct:     mastery += 8
  Chat solve wrong:       mastery -= 12  (when we track wrong)
  Quiz correct:           mastery += 15
  Quiz wrong:             mastery -= 10

POINTS (after completing a 5-question test):
  base = 25 + (score / total) * 40
  level_bonus = {Beginner: 5, Developing: 10, Proficient: 20, Advanced: 30}
  speed_bonus = 15 if avg_time <= 50% of time allowed else 5 if <= 75% else 0
  points_earned = round(base + level_bonus + speed_bonus)

TIMER per question (seconds) by difficulty 1–5:
  {1: 90, 2: 75, 3: 60, 4: 45, 5: 30}

DAILY STREAK (Snapchat-style):
  Complete at least one full test (5/5 submitted) per calendar day.
  last_test_date == yesterday → streak += 1
  last_test_date == today   → streak unchanged
  else                      → streak = 1 (broken)
"""

from __future__ import annotations

LEVEL_BANDS = (
    (75, "Advanced"),
    (50, "Proficient"),
    (25, "Developing"),
    (0, "Beginner"),
)

LEVEL_POINTS_BONUS = {
    "Beginner": 5,
    "Developing": 10,
    "Proficient": 20,
    "Advanced": 30,
}

TIMER_BY_DIFFICULTY = {1: 90, 2: 75, 3: 60, 4: 45, 5: 30}


def mastery_to_level_band(mastery: int) -> str:
    m = max(0, min(100, int(mastery or 0)))
    for threshold, name in LEVEL_BANDS:
        if m >= threshold:
            return name
    return "Beginner"


def time_limit_for_difficulty(difficulty: int) -> int:
    d = max(1, min(5, int(difficulty or 2)))
    return TIMER_BY_DIFFICULTY[d]


def compute_test_points(
    score: int,
    total: int,
    topic_band: str,
    avg_time_seconds: float,
    avg_time_limit_seconds: float | None = None,
) -> int:
    total = max(1, total)
    ratio = score / total
    base = 25 + ratio * 40
    bonus = LEVEL_POINTS_BONUS.get(topic_band, 5)
    speed_bonus = 0
    if avg_time_seconds <= 20:
        speed_bonus = 15
    elif avg_time_seconds <= 45:
        speed_bonus = 5
    return int(round(base + bonus + speed_bonus))
