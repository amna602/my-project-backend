from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SolveRequest
from app.services.activity_record import record_solve_result
from app.services.solver import solve_math_many

router = APIRouter()


@router.post("/solve")
def solve_question(request: SolveRequest, db: Session = Depends(get_db)):
    result = solve_math_many(request.question)

    if "error" in result:
        return result

    if request.user_id:
        record_solve_result(db, request.user_id, result, request.question)
        db.commit()

    return {
        "question": result.get("question"),
        "answer": result.get("answer"),
        "results": result.get("results"),
        "count": result.get("count", 1),
        "user_id": request.user_id,
    }
