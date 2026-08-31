"""Reply language: Roman Urdu (default) or English."""

import re

VALID_STYLES = ("en", "ur_roman")

ENGLISH_EXPLICIT = re.compile(
    r"\b("
    r"in english|english please|answer in english|explain in english|"
    r"speak english|use english|reply in english|write in english|"
    r"english mein nahi|only english"
    r")\b",
    re.IGNORECASE,
)

URDU_EXPLICIT = re.compile(
    r"\b(roman urdu|urdu mein|roman urdu mein|urdu me|hindi urdu)\b",
    re.IGNORECASE,
)


def normalize_style(style: str | None) -> str:
    s = (style or "ur_roman").strip().lower()
    return s if s in VALID_STYLES else "ur_roman"


def resolve_reply_style(
    message: str, preference: str = "ur_roman"
) -> tuple[str, str | None]:
    """
    Pick reply language for this turn.
    Returns (style, new_preference) — new_preference set when user explicitly switches.
    """
    pref = normalize_style(preference)
    msg = message or ""

    if ENGLISH_EXPLICIT.search(msg):
        return "en", "en"
    if URDU_EXPLICIT.search(msg):
        return "ur_roman", "ur_roman"
    return pref, None


def language_instruction(style: str) -> str:
    if normalize_style(style) == "ur_roman":
        return (
            "Reply in Roman Urdu only (Urdu written in Latin letters, e.g. 'Pehle hum ... phir ...'). "
            "Keep a warm, teacher-like tone. Math symbols and numbers stay as-is."
        )
    return "Reply in clear English."


def off_topic_message(style: str) -> str:
    if normalize_style(style) == "ur_roman":
        return (
            "Main MathVox hoon — sirf math mein madad karta hoon. "
            "Koi sawal poochho, worksheet upload karo, ya jo masla pehle solve kiya uske baare mein poochho."
        )
    return (
        "I'm MathVox — I only help with math. "
        "Ask a math question, upload a worksheet, or refer to a problem we discussed."
    )


def no_problem_message(style: str) -> str:
    if normalize_style(style) == "ur_roman":
        return (
            "Kaun sa math masla solve karna hai? "
            "Equation likho ya is chat mein jo pehle solve hua uski taraf ishara karo."
        )
    return (
        "Which math problem should I work on? "
        "Type an equation or point to something from this chat."
    )


def format_solve_reply(result: dict, style: str) -> str:
    """Format SymPy solve output in the chosen language."""
    if normalize_style(style) == "en":
        if result.get("error"):
            return f"Could not solve: {result['error']}"
        if result.get("results"):
            lines = []
            for i, row in enumerate(result["results"], start=1):
                if row.get("error"):
                    lines.append(f"{i}. {row['question']} → {row['error']}")
                else:
                    lines.append(f"{i}. {row['question']} = {row['answer']}")
            return "\n".join(lines)
        if result.get("answer"):
            q = result.get("question", "")
            return f"{q} = {result['answer']}" if q else str(result["answer"])
        return "No solution returned."

    if result.get("error"):
        return f"Hal nahi mil saka: {result['error']}"
    if result.get("results"):
        lines = []
        for i, row in enumerate(result["results"], start=1):
            if row.get("error"):
                lines.append(f"{i}. {row['question']} → masla: {row['error']}")
            else:
                lines.append(f"{i}. {row['question']} ka jawab = {row['answer']}")
        return "\n".join(lines)
    if result.get("answer"):
        q = result.get("question", "")
        ans = result["answer"]
        return f"{q} ka jawab = {ans}" if q else f"Jawab: {ans}"
    return "Koi jawab nahi mila."


def explain_footer(style: str, answer: str) -> str:
    if normalize_style(style) == "ur_roman":
        return f"Aakhri jawab: {answer}"
    return f"Final answer: {answer}"
