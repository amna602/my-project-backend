"""Classify a math question into a skill topic (heuristics + optional Groq)."""

from __future__ import annotations

import json
import os
import re

from app.services.skill_topics import DEFAULT_TOPIC, SKILL_TOPICS

_FRACTION = re.compile(r"\d+\s*/\s*\d+")
_DECIMAL = re.compile(r"\d+\.\d+")
_QUADRATIC = re.compile(r"x\s*\*\*\s*2|x\s*\^\s*2|x²", re.I)
_LINEAR = re.compile(r"\bx\b|solve\s+for", re.I)
_WORD = re.compile(
    r"\b(if|when|total|cost|speed|distance|apples|students|per|each|sum|difference)\b",
    re.I,
)


def classify_topic(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return DEFAULT_TOPIC

    lower = t.lower()
    if _WORD.search(lower) and len(t.split()) > 8:
        return "word_problems"
    if _QUADRATIC.search(t):
        return "quadratics"
    if _LINEAR.search(lower) and ("=" in t or "equation" in lower):
        return "linear_equations"
    if _FRACTION.search(t):
        return "fractions"
    if _DECIMAL.search(t):
        return "decimals"
    if re.search(r"[+\-*/]", t) and not _LINEAR.search(lower):
        return "arithmetic"

    # Optional Groq for ambiguous text
    if len(t) > 15 and os.getenv("GROQ_API_KEY"):
        try:
            return _classify_with_groq(t)
        except Exception:
            pass

    return DEFAULT_TOPIC


def _classify_with_groq(text: str) -> str:
    from groq import Groq

    topics = ", ".join(SKILL_TOPICS.keys())
    prompt = f"""Classify this student math content into exactly ONE topic key.
Keys: {topics}
Content: {text[:400]}
Reply JSON only: {{"topic": "arithmetic"}}"""

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = completion.choices[0].message.content or "{}"
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    topic = (data.get("topic") or DEFAULT_TOPIC).strip().lower()
    return topic if topic in SKILL_TOPICS else DEFAULT_TOPIC
