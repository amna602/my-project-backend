from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.vision_ocr import ocr_image

router = APIRouter()


@router.post("/ocr")
async def ocr_math_image(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload a valid image file.")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file.")

    try:
        result = ocr_image(image_bytes, file.content_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc

    text = (result.get("text") or "").strip()
    expressions = result.get("expressions") or []
    raw_text = (result.get("raw_text") or "").strip()

    if not text and not expressions and not raw_text:
        raise HTTPException(
            status_code=422,
            detail="Could not read any text from this image.",
        )

    return {
        "text": text or "\n".join(expressions),
        "expressions": expressions,
        "raw_text": raw_text,
        "problem_count": len(expressions),
        "source": result.get("source") or "vision",
    }
