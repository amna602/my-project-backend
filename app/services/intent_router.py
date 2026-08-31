import json
import os
import re

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower().strip()


def _parse_json(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group(0))
    return {}


def _history_block(history: list[dict]) -> str:
    lines = []
    for turn in history[-14:]:
        role = turn.get("role", "user")
        label = "Student" if role == "user" else "MathVox"
        text = (turn.get("text") or "").strip()[:800]
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines) if lines else "(no prior messages)"


def classify_message(message: str, history: list[dict]) -> dict:
    """
    LLM decides how to handle the message (math-only app).
    Returns dict with intent, expression, use_thread_problem.
    """
    prompt = f"""You are the router for MathVox, a math-only tutoring app.

Conversation so far:
{_history_block(history)}

New student message:
{message.strip()}

Classify and extract math. Respond with ONLY JSON:
{{
  "intent": "solve" | "explain" | "discuss" | "off_topic",
  "expression": "SymPy-ready math ONLY if this message contains a new problem to compute; else null",
  "use_thread_problem": true if they refer to a prior problem (it, that, last one, explain, why, clarify) without giving a full new equation
}}

Rules:
- intent "solve": they want an answer (new equation, worksheet, calculate, what is 2+2, etc.)
- intent "explain": they want steps or understanding (explain, how, why, show work, break it down)
- intent "discuss": follow-up about math already in the thread (compare problems, is my answer right, what about x)
- intent "off_topic": not math (weather, jokes unrelated to math, coding homework with no math)
- expression: use * for multiply, ** for powers, 2*x+1=5 for algebra; digits only for worksheets like 1+4
- use_thread_problem: true for vague references when history has a problem
- If message has BOTH explain and a full equation, intent "explain" and fill expression
- If unsure but message mentions numbers/operators, prefer solve or explain over off_topic"""

    if PROVIDER == "groq":
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        client = Groq(api_key=api_key)
        model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        raw = completion.choices[0].message.content or ""
    else:
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
        raw = model.generate_content(prompt).text or ""

    data = _parse_json(raw)
    intent = (data.get("intent") or "discuss").lower().strip()
    if intent not in ("solve", "explain", "discuss", "off_topic"):
        intent = "discuss"

    expr = data.get("expression")
    if expr in (None, "null", ""):
        expr = None
    else:
        expr = str(expr).strip()

    return {
        "intent": intent,
        "expression": expr,
        "use_thread_problem": bool(data.get("use_thread_problem")),
    }
