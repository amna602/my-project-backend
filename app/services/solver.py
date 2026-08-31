import json
import re

from sympy import Eq, solve, sympify, symbols

from app.services.llm_client import extract_math_expression

FILLER_WORDS = (
    "explain",
    "how",
    "why",
    "what",
    "is",
    "the",
    "a",
    "an",
    "to",
    "of",
    "for",
    "me",
    "please",
    "can",
    "you",
    "show",
    "tell",
    "help",
    "solve",
    "calculate",
    "find",
    "evaluate",
    "compute",
    "answer",
    "equals",
    "equal",
    "whats",
    "what's",
)

WORD_TO_OP = (
    (r"\bplus\b", "+"),
    (r"\bminus\b", "-"),
    (r"\btimes\b", "*"),
    (r"\bmultiplied\s+by\b", "*"),
    (r"\bdivided\s+by\b", "/"),
    (r"\bover\b", "/"),
    (r"\bsquared\b", "**2"),
    (r"\bcubed\b", "**3"),
    (r"\bpercent\b", "/100"),
)

NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}


def _replace_number_words(text: str) -> str:
    for word, digit in NUMBER_WORDS.items():
        text = re.sub(rf"\b{word}\b", digit, text, flags=re.IGNORECASE)
    return text


def _replace_word_operators(text: str) -> str:
    for pattern, op in WORD_TO_OP:
        text = re.sub(pattern, op, text, flags=re.IGNORECASE)
    return text


def _remove_filler_words(text: str) -> str:
    for word in FILLER_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.IGNORECASE)
    return text


def _normalize_symbols(text: str) -> str:
    text = text.replace("×", "*").replace("÷", "/")
    text = text.replace("^", "**")
    text = re.sub(r"(\d)\s*\(\s*(\d)", r"\1*(\2", text)
    text = re.sub(r"\)\s*(\d)", r")*\1", text)
    # 5x, 2x, 3(x+1)
    text = re.sub(r"(\d)([xXyYzZ])", r"\1*\2", text)
    text = re.sub(r"([xXyYzZ])(\d)", r"\1*\2", text)
    text = re.sub(r"\)([xXyYzZ])", r")*\1", text)
    text = re.sub(r"([xXyYzZ])\(", r"\1*(", text)
    return text


def _extract_math_runs(text: str) -> str | None:
    """Pull the longest math-like chunk from mixed text."""
    compact = re.sub(r"\s+", "", text)
    runs = re.findall(r"[0-9xXyYzZ+\-*/().=]+", compact)
    runs = [
        r
        for r in runs
        if re.search(r"\d", r) or re.search(r"[xyzXYZ]\s*\*\*", r)
    ]
    if not runs:
        return None
    return max(runs, key=len)


def _pick_problem_line(raw: str) -> str:
    """Pick text to solve — keep full problem when it is one expression."""
    from app.services.math_extract import is_single_comprehensive_problem

    stripped = raw.strip()
    if is_single_comprehensive_problem(stripped):
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        return " ".join(lines) if len(lines) > 1 else stripped

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return stripped

    for ln in lines:
        if "=" in ln and re.search(r"[xyzXYZ]", ln, re.IGNORECASE):
            return ln
    for ln in lines:
        if re.search(r"[0-9xyzXYZ+\-*/^=]", ln, re.IGNORECASE):
            return ln
    return lines[0]


def _prepare_question(raw: str) -> str:
    from app.services.math_extract import is_single_comprehensive_problem

    if is_single_comprehensive_problem(raw):
        text = raw.replace("\n", " ").strip()
    else:
        text = _pick_problem_line(raw)
    text = re.sub(r"[?!.]+$", "", text).strip()
    text = _replace_number_words(text.lower())
    text = _replace_word_operators(text)
    text = _remove_filler_words(text)
    text = _normalize_symbols(text)

    cleaned = _extract_math_runs(text)
    if not cleaned:
        cleaned = re.sub(r"[^0-9xXyYzZ+\-*/().=]", "", text.replace(" ", ""))

    if not cleaned:
        raise ValueError("no_expression")

    if cleaned.endswith("="):
        cleaned = cleaned.rstrip("=")
        if not cleaned:
            raise ValueError("no_expression")

    return cleaned


def _format_number(value: float, symbolic=None) -> str:
    if symbolic is not None and float(symbolic).is_integer():
        return str(int(float(symbolic)))
    if value.is_integer():
        return str(int(value))
    return f"{symbolic if symbolic is not None else value} ≈ {value:.4g}"


def _format_symbol_solutions(symbol_name: str, solutions) -> str:
    if not solutions:
        return "No solution"

    parts = []
    for sol in solutions:
        if sol.is_real:
            parts.append(_format_number(float(sol), sol))
        else:
            parts.append(str(sol))

    label = symbol_name.lower()
    if len(parts) == 1:
        return f"{label} = {parts[0]}"
    return f"{label} = {', '.join(parts)}"


def _solve_prepared(expr: str, original: str) -> dict:
    if "=" in expr and re.search(r"[xyzXYZ]", expr):
        left, right = expr.split("=", 1)
        if not left or not right:
            raise ValueError("invalid_equation")

        var_match = re.search(r"([xyzXYZ])", expr)
        var_name = var_match.group(1).lower() if var_match else "x"
        var = symbols(var_name)

        eq = Eq(sympify(left), sympify(right))
        result = solve(eq, var)

        answer = _format_symbol_solutions(var_name, result)
        return {"question": original, "answer": answer}

    if "=" in expr:
        left, right = expr.split("=", 1)
        if not right:
            expr = left
        else:
            left_val = float(sympify(left))
            right_val = float(sympify(right))
            if abs(left_val - right_val) < 1e-9:
                return {
                    "question": original,
                    "answer": _format_number(left_val, left_val),
                }
            return {
                "question": original,
                "answer": f"Not equal: left={left_val:g}, right={right_val:g}",
            }

    result = sympify(expr)
    val = float(result)
    return {"question": original, "answer": _format_number(val, result)}


def solve_math(question: str):
    original = question.strip()
    if not original:
        return {"error": "Please type a math question."}

    work = _pick_problem_line(original)
    expr = None
    try:
        expr = _prepare_question(work)
        print("SOLVER INPUT:", repr(original))
        print("PREPARED EXPR:", repr(expr))
        return _solve_prepared(expr, original)
    except ValueError:
        pass
    except Exception:
        pass

    try:
        expr = extract_math_expression(original)
        expr = _prepare_question(expr)
        return _solve_prepared(expr, original)
    except RuntimeError:
        return {
            "error": "Could not understand the question. Try: 4*2, what is 5+3, or x+1=5.",
        }
    except Exception:
        return {
            "error": "Could not solve this problem. Try writing the equation more clearly.",
        }


def solve_math_many(question: str) -> dict:
    from app.services.math_extract import split_questions

    parts = split_questions(question)
    if not parts:
        return {"error": "No math problems found. Type or upload clearer text."}

    if len(parts) == 1:
        single = solve_math(parts[0])
        if "error" in single:
            return single
        return {
            "results": [single],
            "count": 1,
            "question": single["question"],
            "answer": single["answer"],
        }

    results = []
    for part in parts:
        outcome = solve_math(part)
        if "error" in outcome:
            results.append(
                {
                    "question": part,
                    "answer": None,
                    "error": outcome["error"],
                }
            )
        else:
            results.append(outcome)

    summary_lines = []
    for i, row in enumerate(results, start=1):
        if row.get("error"):
            summary_lines.append(f"{i}. {row['question']} → {row['error']}")
        else:
            summary_lines.append(f"{i}. {row['question']} = {row['answer']}")

    return {
        "results": results,
        "count": len(results),
        "question": question.strip()[:500],
        "answer": "\n".join(summary_lines),
    }
