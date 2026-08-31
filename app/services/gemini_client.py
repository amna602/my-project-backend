import json
import os
import re

import google.generativeai as genai

# API name: models/gemini-2.0-flash (use short id in code)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _get_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
    return api_key


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    return json.loads(cleaned)


def generate_explanation(question: str, answer: str, reply_style: str) -> dict:
    """Text-only Gemini helper for step-by-step math explanations."""
    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(MODEL_NAME)

    if reply_style == "ur_roman":
        language_instruction = (
            "Write the ENTIRE explanation in Roman Urdu (Urdu in Latin script only). "
            "Start with a short, student-friendly preamble (e.g. 'Pehle ... phir ...'). "
            "Keep steps simple and conversational."
        )
    else:
        language_instruction = "Write the explanation in clear English."

    prompt = f"""You are a math tutor. Explain how to solve this problem step by step.

Problem: {question}
The correct final answer (verified by SymPy) is: {answer}
Your explanation MUST agree with this final answer. Use numbered steps in the step text (1., 2., 3., ...).

{language_instruction}

Respond with ONLY valid JSON in this exact shape:
{{"steps": ["step 1 text", "step 2 text", ...]}}

Do not include markdown code fences or any text outside the JSON object."""

    response = model.generate_content(prompt)
    data = _parse_json_response(response.text)
    steps = data.get("steps", [])

    if isinstance(steps, str):
        steps = [steps]
    elif not isinstance(steps, list):
        steps = [str(steps)]

    return {"steps": steps}
