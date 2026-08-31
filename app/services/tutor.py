import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.services.activity_record import record_solve_result
from app.services.intent_router import classify_message
from app.services.llm_client import chat_with_history, generate_explanation
from app.services.math_extract import split_questions
from app.services.reply_language import (
    explain_footer,
    format_solve_reply,
    no_problem_message,
    off_topic_message,
    resolve_reply_style,
)
from app.services.solver import solve_math, solve_math_many


def _history_from_db(messages: list[ChatMessage]) -> list[dict]:
    return [
        {"role": m.role, "text": m.content}
        for m in messages
        if m.content and m.content.strip()
    ]


def _find_problem_in_history(history: list[dict]) -> dict | None:
    for i in range(len(history) - 1, 0, -1):
        if history[i].get("role") != "assistant":
            continue
        user = history[i - 1]
        if user.get("role") != "user":
            continue
        text = (user.get("text") or "").strip()
        text = re.sub(r"^Solve all \(\d+ problems\):\s*", "", text, flags=re.I)
        first = text.split("\n")[0].strip() if text else ""
        if first and re.search(r"\d", first):
            answer = None
            bot = (history[i].get("text") or "").strip()
            for line in bot.split("\n"):
                if "=" in line:
                    answer = line.split("=")[-1].strip()
                    break
            return {"question": first, "answer": answer}
    return None


def _resolve_problem(
    message: str,
    thread: ChatThread,
    history: list[dict],
    routing: dict,
) -> tuple[str | None, str | None]:
    expr = routing.get("expression")
    if expr:
        return expr, None

    if routing.get("use_thread_problem") or routing.get("intent") in (
        "explain",
        "discuss",
    ):
        if thread.last_solved_question:
            return thread.last_solved_question, thread.last_solved_answer
        found = _find_problem_in_history(history)
        if found:
            return found["question"], found.get("answer")

    if re.search(r"\d", message) and routing.get("intent") == "solve":
        return message.strip(), None

    return None, None


def _run_explain(
    problem: str, known_answer: str | None, reply_style: str
) -> tuple[str, dict | None]:
    answer = known_answer
    if not answer:
        solved = solve_math(problem)
        if solved.get("error"):
            return solved["error"], None
        answer = solved["answer"]

    expl = generate_explanation(problem, answer, reply_style)
    steps = expl.get("steps", [])
    body = "\n\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    reply = f"{body}\n\n{explain_footer(reply_style, answer)}"
    return reply, {"question": problem, "answer": answer}


def _run_solve(
    db: Session, user_id: int, problem: str, reply_style: str
) -> tuple[str, dict | None]:
    parts = split_questions(problem)
    if len(parts) > 1:
        result = solve_math_many(problem)
    else:
        result = solve_math(problem)

    reply = format_solve_reply(result, reply_style)
    last_solved = None

    if result.get("results"):
        solved_rows = [r for r in result["results"] if r.get("answer")]
        if solved_rows:
            last = solved_rows[-1]
            last_solved = {"question": last["question"], "answer": last["answer"]}
            record_solve_result(db, user_id, result, problem)
    elif result.get("answer"):
        last_solved = {
            "question": result.get("question") or problem,
            "answer": result["answer"],
        }
        record_solve_result(db, user_id, result, problem)

    return reply, last_solved


def process_tutor_message(
    db: Session,
    user_id: int,
    thread_id: int,
    message: str,
    reply_style_pref: str = "ur_roman",
) -> dict[str, Any]:
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        .first()
    )
    if not thread:
        raise ValueError("Thread not found")

    text = (message or "").strip()
    if not text:
        raise ValueError("Message is required")

    db.add(ChatMessage(thread_id=thread_id, role="user", content=text))
    db.flush()

    prior = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = _history_from_db(prior[:-1])

    reply_style, pref_update = resolve_reply_style(text, reply_style_pref)
    routing = classify_message(text, history)
    intent = routing["intent"]
    last_solved: dict | None = None
    reply = ""

    if intent == "off_topic":
        reply = off_topic_message(reply_style)
    elif intent == "discuss":
        reply = chat_with_history(text, history, reply_style)
    else:
        problem, known_answer = _resolve_problem(text, thread, history, routing)

        if not problem:
            reply = chat_with_history(text, history, reply_style) or no_problem_message(
                reply_style
            )
        elif intent == "explain":
            reply, last_solved = _run_explain(problem, known_answer, reply_style)
        else:
            reply, last_solved = _run_solve(db, user_id, problem, reply_style)

    if last_solved:
        thread.last_solved_question = last_solved["question"]
        thread.last_solved_answer = last_solved["answer"]

    if not thread.custom_title and len(prior) <= 2:
        thread.title = (text[:52] + "…") if len(text) > 52 else text

    db.add(ChatMessage(thread_id=thread_id, role="assistant", content=reply))
    db.commit()
    db.refresh(thread)

    return {
        "reply": reply,
        "intent": intent,
        "thread_id": thread_id,
        "last_solved": last_solved,
        "title": thread.title,
        "reply_style": reply_style,
        "preference_update": pref_update,
    }
