import json
import os
import re

PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower().strip()

def _build_prompt(question: str, answer: str, reply_style: str) -> str:
    if reply_style == "ur_roman":
        language_instruction = (
            "Write the ENTIRE explanation in simple Roman Urdu. "
            "Use short, natural student-friendly sentences."
        )
    else:
        language_instruction = (
            "Write the explanation in clear, simple English."
        )

    return f"""You are MathVox, a math tutor.

The student has already been shown the problem and the final answer.
Your ONLY job is to explain HOW THE FINAL ANSWER was calculated.

Problem: {question}
Verified final answer: {answer}

STRICT RULES:

1. DO NOT explain or describe the question.
2. DO NOT describe the image or OCR.
3. DO NOT repeat the full question.
4. DO NOT spend any step identifying what the question says.
5. Start DIRECTLY with the first mathematical calculation.
6. Explain ONLY the operations needed to reach the verified answer.
7. Give a detailed step-by-step explanation. Use as many steps as needed to clearly show every important calculation.
8. Do not skip intermediate calculations.
9. For multi-operation problems, explain the order of operations clearly.
10. Each step should contain a real calculation.
11. Use the actual numbers from the problem.
12. Follow normal mathematical order of operations.
13. The final step must clearly state the verified answer.
14. NEVER invent numbers or operations.
15. NEVER contradict the verified answer.
16. NEVER output <think>, analysis, reasoning, or hidden thoughts.
17. Do not explain the question itself; explain only how to calculate the answer.

Example:

For problem:
9 - 3 ÷ (1/3) + 1

Do NOT write:
"The question asks us to solve..."

Instead write calculation steps such as:
"3 ÷ (1/3) = 9."
"Ab expression 9 - 9 + 1 ban jati hai."
"9 - 9 + 1 = 1."
"Final answer = 1."

{language_instruction}

Return ONLY valid JSON:

{{"steps":["step 1","step 2","step 3"]}}

No markdown.
No code fences.
No text before or after the JSON."""

def _remove_thinking(text: str) -> str:
    """Remove model reasoning/thinking blocks from generated output."""
    if not text:
        return ""

    # Remove complete <think>...</think> blocks.
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove unmatched think tags too.
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)

    # Remove common reasoning labels if the model adds them.
    text = re.sub(
        r"^\s*(analysis|reasoning|chain of thought)\s*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def _parse_json_response(text: str) -> dict:
    cleaned = _remove_thinking(text)

    # Remove markdown fences if model adds them.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try to extract the JSON object if extra text exists.
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)

    return json.loads(cleaned)


def _clean_step(step: str) -> str:
    """Clean an individual generated step."""
    step = _remove_thinking(str(step))

    # Remove accidental markdown headings/fences.
    step = re.sub(r"```+", "", step)

    # Remove repeated numbering such as:
    # 1. 1. Pehle...
    # 2. 2. Ab...
    step = re.sub(
        r"^\s*\d+\s*[\.\)]\s*(?:\d+\s*[\.\)]\s*)?",
        "",
        step,
    )

    return step.strip()


def _normalize_steps(data: dict) -> dict:
    steps = data.get("steps", [])

    if isinstance(steps, str):
        steps = [steps]
    elif not isinstance(steps, list):
        steps = [str(steps)]

    cleaned_steps = []

    for step in steps:
        step = _clean_step(step)

        if not step:
            continue

        # Prevent extremely long individual steps.
        if len(step) > 300:
            step = step[:300].rstrip() + "..."

        cleaned_steps.append(step)

    # Keep explanation short.
    cleaned_steps = cleaned_steps[:4]

    return {"steps": cleaned_steps}


def _generate_groq(prompt: str) -> dict:
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")

    from groq import Groq

    client = Groq(api_key=api_key)

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b",
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a concise math tutor. "
                    "Never reveal internal reasoning or thinking. "
                    "Never output <think> tags. "
                    "Return only the requested JSON."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
    )

    text = completion.choices[0].message.content or ""

    return _normalize_steps(_parse_json_response(text))


def _generate_gemini(prompt: str) -> dict:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    genai.configure(api_key=api_key)

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.0-flash",
    )

    model = genai.GenerativeModel(model_name)

    response = model.generate_content(prompt)

    return _normalize_steps(
        _parse_json_response(response.text or "")
    )


def extract_math_expression(question: str) -> str:
    """Use LLM to pull a SymPy-ready expression from natural language."""

    prompt = f"""Extract ONLY the mathematical expression from this user message.

User message:
{question}

Rules:
- Do NOT solve it.
- Do NOT explain it.
- Do NOT analyze the image.
- Do NOT output reasoning.
- Return JSON only.
- Use * for multiplication.
- Use / for division.
- Use ** for powers.
- Preserve parentheses.
- Preserve the complete expression.
- Do not invent missing numbers.

Examples:
"what is 4*2" -> {{"expression":"4*2"}}
"what is five plus three" -> {{"expression":"5+3"}}
"solve x+1=5" -> {{"expression":"x+1=5"}}
"6 ÷ 2(1+2) = ?" -> {{"expression":"6/2*(1+2)"}}
"9 - 3 ÷ 1/3 + 1 = ?" -> {{"expression":"9-3/(1/3)+1"}}

Return ONLY:
{{"expression":"..."}}"""

    if PROVIDER == "groq":
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        from groq import Groq

        client = Groq(api_key=api_key)

        model = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        )

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract math only. "
                        "Never solve. "
                        "Never output <think>. "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0,
        )

        text = completion.choices[0].message.content or ""

    elif PROVIDER == "gemini":
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            os.getenv(
                "GEMINI_MODEL",
                "gemini-2.0-flash",
            )
        )

        response = model.generate_content(prompt)
        text = response.text or ""

    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{PROVIDER}'"
        )

    data = _parse_json_response(text)

    expression = (data.get("expression") or "").strip()

    if not expression:
        raise ValueError("no_expression")

    return expression


def chat_with_history(
    message: str,
    history: list[dict],
    reply_style: str = "ur_roman",
) -> str:
    """Conversational reply using prior chat turns as context."""

    from app.services.reply_language import (
        language_instruction,
        normalize_style,
    )

    style = normalize_style(reply_style)
    lang = language_instruction(style)

    system = f"""You are MathVox, a friendly and concise math tutor.

{lang}

You understand Roman Urdu, Urdu, and English.

Use conversation history when the student refers to:
"it", "that", "woh", "pehle wala", "last one", or "problem 2".

Rules:
- Keep replies short.
- Do not reveal internal reasoning.
- Never output <think> or </think>.
- Do not discuss hidden analysis.
- If solving a simple calculation, give the answer with brief work.
- If explaining a previous equation, explain only that equation.
- Do not repeat unnecessary context.
"""

    groq_messages = [
        {
            "role": "system",
            "content": system,
        }
    ]

    for turn in history[-16:]:
        role = turn.get("role", "user")

        if role not in ("user", "assistant"):
            role = (
                "assistant"
                if role in ("bot", "assistant")
                else "user"
            )

        text = (turn.get("text") or "").strip()

        if text:
            groq_messages.append(
                {
                    "role": role,
                    "content": text[:3000],
                }
            )

    groq_messages.append(
        {
            "role": "user",
            "content": message.strip(),
        }
    )

    if PROVIDER == "groq":
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        from groq import Groq

        client = Groq(api_key=api_key)

        model = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        )

        completion = client.chat.completions.create(
            model=model,
            messages=groq_messages,
            temperature=0.3,
        )

        return _remove_thinking(
            completion.choices[0].message.content or ""
        ).strip()

    if PROVIDER == "gemini":
        import google.generativeai as genai

        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            os.getenv(
                "GEMINI_MODEL",
                "gemini-2.0-flash",
            )
        )

        parts = [
            system,
            "\n\nConversation:",
        ]

        for turn in history[-16:]:
            label = (
                "Student"
                if turn.get("role") == "user"
                else "MathVox"
            )

            parts.append(
                f"{label}: {turn.get('text', '')}"
            )

        parts.append(
            f"Student: {message.strip()}\nMathVox:"
        )

        response = model.generate_content(
            "\n".join(parts)
        )

        return _remove_thinking(
            response.text or ""
        ).strip()

    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{PROVIDER}'"
    )


def generate_explanation(
    question: str,
    answer: str,
    reply_style: str,
) -> dict:
    prompt = _build_prompt(
        question,
        answer,
        reply_style,
    )

    if PROVIDER == "groq":
        return _generate_groq(prompt)

    if PROVIDER == "gemini":
        return _generate_gemini(prompt)

    raise RuntimeError(
        f"Unknown LLM_PROVIDER '{PROVIDER}'. "
        "Use groq or gemini in .env"
    )