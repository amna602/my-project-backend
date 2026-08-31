import base64
import json
import os
import re

from app.services.image_preprocess import preprocess_for_ocr
from app.services.math_extract import extract_expressions_from_text
from app.services.ocr_validate import (
    dedupe_expressions,
    filter_single_digit_addition,
    filter_valid_expressions,
)


OCR_PROMPT = r"""
You are a precision OCR engine for printed mathematics.

YOUR ONLY JOB IS TO READ THE IMAGE AND TRANSCRIBE THE MATHEMATICS.

DO NOT solve the problem.
DO NOT calculate the answer.
DO NOT explain the image.
DO NOT describe what you see.
DO NOT provide reasoning.
DO NOT output <think>.
DO NOT output analysis.

Read the mathematical expression EXACTLY as it appears.

IMPORTANT:
Preserve the COMPLETE mathematical expression.

Supported operations:

+   addition
-   subtraction
×   multiplication
x   multiplication
*   multiplication
÷   division
/   division

Also preserve:

- fractions such as 1/3, 2/5, 3/4
- parentheses ( )
- brackets [ ]
- exponents such as x^2 or 2^3
- decimal numbers such as 2.5
- negative numbers such as -3
- equations containing =
- question marks such as ?
- expressions containing multiple operations

Examples:

Image:
44 ÷ 8 = ?

Return:
{"problem_count":1,"raw_text":"44 ÷ 8 = ?","expressions":["44/8=?"]}

Image:
9 - 3 ÷ 1/3 + 1 = ?

Return:
{"problem_count":1,"raw_text":"9 - 3 ÷ 1/3 + 1 = ?","expressions":["9-3/(1/3)+1=?"]}

Image:
2 × (5 + 3) = ?

Return:
{"problem_count":1,"raw_text":"2 × (5 + 3) = ?","expressions":["2*(5+3)=?"]}

Image:
1/2 + 3/4 = ?

Return:
{"problem_count":1,"raw_text":"1/2 + 3/4 = ?","expressions":["1/2+3/4=?"]}

Image:
2^2 + 5 = ?

Return:
{"problem_count":1,"raw_text":"2^2 + 5 = ?","expressions":["2^2+5=?"]}

IMPORTANT OPERATOR RULES:

÷ must become /
× must become *
x used as multiplication must become *
− must become -
+ stays +

NEVER replace an operator with another operator.

For example:

44 ÷ 8

MUST become:

44/8

NOT:

44+8

NOT:

44-8

NOT:

44*8

COMPLETE EXPRESSION RULE:

If the image contains:

9 - 3 ÷ 1/3 + 1 = ?

DO NOT return:

9-3

DO NOT return:

9-3/1

DO NOT return:

9-3+1

Return the COMPLETE expression:

9-3/(1/3)+1=?

If the image contains:

2 × (5 + 3) = ?

Return:

2*(5+3)=?

Do NOT return only:

2*5

FRACTIONS:

Read fractions carefully.

For example:

1
—
3

means:

1/3

If the fraction is part of a larger expression, keep it as part of that expression.

For example:

9 - 3 ÷ 1/3 + 1

must remain ONE complete problem.

WORKSHEET:

If there are multiple separate problems:

Scan LEFT-TO-RIGHT and TOP-TO-BOTTOM.

Include EVERY visible mathematical problem.

Do NOT merge separate problems.

Do NOT stop after the first problem.

VERTICAL PROBLEMS:

For:

  8
 +5
 ----

return:

8+5

For:

  12
 - 7
 ----

return:

12-7

IGNORE:

- Name
- Date
- website URLs
- page numbers
- decorative text
- unrelated instructions
- multiple-choice answers unless they are themselves mathematical problems

OUTPUT:

Return ONLY valid JSON.

No markdown.
No code fences.
No explanation.
No reasoning.
No <think>.

Use exactly this structure:

{
  "problem_count": 1,
  "raw_text": "44 ÷ 8 = ?",
  "expressions": ["44/8=?"]
}

problem_count MUST equal the number of expressions.

expressions MUST contain complete mathematical problems.
"""


def _parse_llm_json(text: str) -> dict:
    """
    Safely parse the vision model response.

    Removes <think>...</think>, markdown fences,
    and tries to recover JSON if the model adds extra text.
    """

    cleaned = (text or "").strip()

    # Remove model reasoning if present
    cleaned = re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Remove possible markdown JSON fences
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    ).strip()

    # Normal JSON response
    try:
        data = json.loads(cleaned)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    # Try to find JSON object inside extra text
    match = re.search(r"\{[\s\S]*\}", cleaned)

    if match:
        try:
            data = json.loads(match.group(0))

            if isinstance(data, dict):
                return data

        except json.JSONDecodeError:
            pass
 # Last fallback:
    # Try to find simple mathematical expressions
    expressions = re.findall(
        r"\d+(?:\.\d+)?\s*[+\-*/]\s*\d+(?:\.\d+)?",
        cleaned,
    )

    return {
        "raw_text": "",
        "expressions": expressions,
    }
def _normalize_expression(expression: str) -> str:
    """
    Normalize mathematical operators while preserving
    the complete expression.
    """

    s = str(expression or "").strip()

    # Remove whitespace
    s = re.sub(r"\s+", "", s)

    # Normalize multiplication
    s = s.replace("×", "*")
    s = s.replace("x", "*")

    # Normalize division
    s = s.replace("÷", "/")

    # Normalize minus
    s = s.replace("−", "-")

    return s


def _normalize_expr_list(exprs: list) -> list[str]:
    """
    Normalize all expressions.

    IMPORTANT:
    We intentionally do NOT restrict expressions to:

        number operator number

    because MathVox supports longer expressions such as:

        9-3/(1/3)+1=?
        2*(5+3)=?
        1/2+3/4=?
    """

    out: list[str] = []

    for e in exprs:

        s = _normalize_expression(str(e))

        if not s:
            continue

        # Remove surrounding quotes if model accidentally adds them
        s = s.strip("\"'")

        # Ignore obvious reasoning text
        if "<think>" in s.lower():
            continue

        if len(s) > 500:
            continue

        # Must contain at least one digit
        if not re.search(r"\d", s):
            continue

        # Must contain at least one mathematical operator
        if not re.search(r"[+\-*/=]", s):
            continue

        out.append(s)

    return out


def _extract_from_raw_text(raw: str) -> list[str]:
    """
    Fallback extraction from raw OCR text.

    This is intentionally conservative.
    """

    if not raw:
        return []

    # Remove reasoning blocks
    cleaned = re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    results: list[str] = []

    # First try the project's existing math parser
    try:
        parsed = extract_expressions_from_text(cleaned)

        if parsed:
            results.extend(parsed)

    except Exception:
        pass

    # Also detect common complete arithmetic expressions
    lines = cleaned.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        # Remove obvious explanatory prefixes
        if re.search(
            r"^(the image|the user|analysis|reasoning|example|return|output)",
            line,
            re.IGNORECASE,
        ):
            continue

        normalized = _normalize_expression(line)

        # Must contain a digit and math operator
        if (
            re.search(r"\d", normalized)
            and re.search(r"[+\-*/=]", normalized)
        ):
            if len(normalized) <= 500:
                results.append(normalized)

    return results

def _merge_vision_expressions(
    exprs: list[str],
    raw: str,
) -> list[str]:
    """
    Merge vision expressions with raw OCR text.

    Prefer complete expressions. If the vision model returns
    suspicious fragments while raw_text contains more complete
    mathematical lines, use the raw-text extraction.
    """

    # Normalize model expressions
    model_exprs = _normalize_expr_list(exprs)
    model_exprs = dedupe_expressions(model_exprs)

    # Extract complete expressions from raw OCR text
    parsed = _extract_from_raw_text(raw)
    parsed = _normalize_expr_list(parsed)
    parsed = dedupe_expressions(parsed)

    # If raw OCR found more complete mathematical problems,
    # prefer those over suspicious/incomplete model expressions.
    if parsed:
        if not model_exprs:
            return parsed

        if len(parsed) > len(model_exprs):
            return parsed

        # If raw contains a longer mathematical expression,
        # prefer it over a shorter model fragment.
        longest_raw = max(parsed, key=len)
        longest_model = max(model_exprs, key=len)

        if len(longest_raw) > len(longest_model) + 2:
            return parsed

    # Otherwise keep the vision model result exactly as before.
    if model_exprs:
        return model_exprs

    return parsed


def _result_from_llm(llm_text: str) -> dict:
    """
    Convert vision model output into the clean OCR result
    expected by the frontend.
    """

    data = _parse_llm_json(llm_text)

    raw = (
        data.get("raw_text")
        or data.get("text")
        or ""
    ).strip()

    expressions = data.get("expressions") or []

    exprs = _merge_vision_expressions(
        expressions,
        raw,
    )

    # Special handling for single digit addition sheets
    is_single_digit_sheet = bool(
        re.search(
            r"single\s*digit|digit\s*addition",
            raw or "",
            re.IGNORECASE,
        )
    )

    if is_single_digit_sheet and exprs:

        try:
            filtered = filter_single_digit_addition(exprs)

            if len(filtered) >= len(exprs):
                exprs = filtered

        except Exception:
            pass

    # IMPORTANT:
    #
    # Do NOT use format_for_client(raw, exprs)
    # because raw_text may contain model reasoning.
    #
    # OCR display should contain ONLY mathematical expressions.
    display = "\n".join(exprs)

    return {
        "text": display,
        "expressions": exprs,
        "raw_text": raw,
        "problem_count": len(exprs),
        "source": "vision",
    }


def _vision_provider_order() -> list[str]:
    """
    Determine which vision provider should be used.
    """

    explicit = (
        os.getenv("VISION_PROVIDER")
        or ""
    ).strip().lower()

    if explicit in ("groq", "gemini"):
        return [explicit]

    if (
        os.getenv("GROQ_API_KEY")
        and not os.getenv("GEMINI_API_KEY")
    ):
        return ["groq"]

    if (
        os.getenv("GEMINI_API_KEY")
        and not os.getenv("GROQ_API_KEY")
    ):
        return ["gemini"]

    if (
        os.getenv("LLM_PROVIDER")
        or ""
    ).strip().lower() == "groq":
        return ["groq", "gemini"]

    return ["gemini", "groq"]


def _ocr_with_gemini(
    image_bytes: bytes,
    mime_type: str,
) -> dict:

    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set"
        )

    genai.configure(api_key=api_key)

    model_name = os.getenv(
        "GEMINI_VISION_MODEL",
        os.getenv(
            "GEMINI_MODEL",
            "gemini-2.0-flash",
        ),
    )

    model = genai.GenerativeModel(model_name)

    response = model.generate_content(
        [
            OCR_PROMPT,
            {
                "mime_type": mime_type or "image/png",
                "data": image_bytes,
            },
        ],
        generation_config={
            "temperature": 0,
        },
    )

    response_text = getattr(
        response,
        "text",
        "",
    ) or ""

    out = _result_from_llm(response_text)

    out["provider"] = "gemini"

    return out


def _ocr_with_groq(
    image_bytes: bytes,
    mime_type: str,
) -> dict:

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set"
        )

    from groq import Groq

    client = Groq(api_key=api_key)

    # Current vision model from .env
    model = os.getenv(
        "GROQ_VISION_MODEL",
        "qwen/qwen3.6-27b",
    )

    b64 = base64.standard_b64encode(
        image_bytes
    ).decode("ascii")

    data_url = (
        f"data:{mime_type or 'image/png'};"
        f"base64,{b64}"
    )

    strict_prompt = OCR_PROMPT + r"""

FINAL WARNING:

You are an OCR engine.

The image is NOT asking you to solve the problem.

If the image says:

44 ÷ 8 = ?

Your COMPLETE response must be exactly:

{
  "problem_count": 1,
  "raw_text": "44 ÷ 8 = ?",
  "expressions": ["44/8=?"]
}

Do not write:

<think>

Do not write:

The image shows...

Do not write:

The answer is...

Do not explain anything.

Return JSON ONLY.
"""

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": strict_prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                        },
                    },
                ],
            }
        ],
        temperature=0,

        # Force JSON output
        response_format={
            "type": "json_object"
        },
    )

    text = (
        completion
        .choices[0]
        .message
        .content
        or ""
    )

    out = _result_from_llm(text)

    out["provider"] = "groq"

    return out


def _pick_best_result(
    results: list[dict],
) -> dict | None:

    if not results:
        return None

    prefer = _vision_provider_order()[0]

    def score(r: dict) -> int:

        n = len(
            r.get("expressions") or []
        )

        raw_len = len(
            r.get("raw_text") or ""
        )

        bonus = 50

        if r.get("provider") == prefer:
            bonus += 30

        return (
            n * 200
            + raw_len
            + bonus
        )

    return max(
        results,
        key=score,
    )


def _run_vision(
    img_bytes: bytes,
    mime_type: str,
    provider: str,
) -> dict:

    if provider == "groq":
        return _ocr_with_groq(
            img_bytes,
            mime_type,
        )

    return _ocr_with_gemini(
        img_bytes,
        mime_type,
    )


def ocr_image(
    image_bytes: bytes,
    mime_type: str = "image/png",
) -> dict:

    errors: list[str] = []

    candidates: list[dict] = []

    # Preprocess image
    try:
        enhanced = preprocess_for_ocr(
            image_bytes
        )

    except Exception:
        enhanced = image_bytes

    # Try enhanced image first, then original
    image_variants = [
        enhanced,
        image_bytes,
    ]

    providers = _vision_provider_order()

    for img_bytes in image_variants:

        for provider in providers:

            if (
                provider == "groq"
                and not os.getenv("GROQ_API_KEY")
            ):
                continue

            if (
                provider == "gemini"
                and not os.getenv("GEMINI_API_KEY")
            ):
                continue

            try:

                result = _run_vision(
                    img_bytes,
                    mime_type,
                    provider,
                )

                if (
                    result.get("expressions")
                    or result.get("text")
                ):
                    candidates.append(result)

            except Exception as exc:

                label = (
                    f"{provider}: {exc}"
                )

                print(
                    f"[OCR ERROR] {label}"
                )

                if label not in errors:
                    errors.append(label)

    best = _pick_best_result(
        candidates
    )

    if best and (
        best.get("expressions")
        or best.get("text", "").strip()
    ):
        return best

    if errors:
        raise RuntimeError(
            "; ".join(errors)
        )

    raise RuntimeError(
        "Set GROQ_API_KEY (or GEMINI_API_KEY) "
        "in mathvox-backend/.env for vision OCR"
    )