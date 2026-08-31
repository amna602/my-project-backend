from fastapi import APIRouter, HTTPException

from app.schemas import ExplainRequest
from app.services.llm_client import generate_explanation
from app.services.solver import solve_math

router = APIRouter()


def _looks_like_follow_up_only(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    if any(
        k in t
        for k in (
            "explain",
            "how did you",
            "why is that",
            "show steps",
            "step by step",
        )
    ) and not any(c.isdigit() for c in t) and "=" not in t:
        return True
    return False


@router.post("/explain")
def explain_question(request: ExplainRequest):
    answer = request.answer
    question = (request.question or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="No problem to explain.")

    if not answer:
        if _looks_like_follow_up_only(question):
            raise HTTPException(
                status_code=400,
                detail="Tell me which problem to explain, or solve one in chat first.",
            )
        result = solve_math(question)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        answer = result["answer"]

    try:
        explanation = generate_explanation(
            question=request.question,
            answer=answer,
            reply_style=request.reply_style.value,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "steps": explanation["steps"],
        "final_answer": answer,
        "reply_style": request.reply_style.value,
    }
