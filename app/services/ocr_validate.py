import re


# Supports:
# 2+5
# 12-7
# 8*4
# 9/3
# 9-3/1/3+1
# 2*(5+3)
# (8-2)/3
# 1/2+3/4
# 2^3+5
# 2+5=7
# 8+11=?
#
# This is intentionally a validation regex, not a full math parser.
EXPR_RE = re.compile(
    r"^[0-9A-Za-zxXyYzZ+\-*/().=^?×÷\[\]{}\s]+$"
)


# Simple expression used specifically for detecting
# single-digit addition worksheet problems.
SIMPLE_ADD_RE = re.compile(r"^(\d)\+(\d)$")


def _clean_expression(expr: str) -> str:
    """Normalize an OCR expression for validation."""

    clean = re.sub(r"\s+", "", (expr or "").strip())

    clean = (
        clean
        .replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )

    return clean


def _clean_raw(raw: str) -> str:
    """Normalize OCR raw text for comparison."""

    clean = re.sub(r"\s+", "", (raw or "").strip())

    clean = (
        clean
        .replace("×", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )

    return clean


def _is_valid_expression(expr: str) -> bool:
    """
    Basic safety/format validation.

    This does NOT try to mathematically evaluate the expression.
    SymPy is responsible for actual mathematical validation later.
    """

    if not expr:
        return False

    clean = _clean_expression(expr)

    if not clean:
        return False

    # Only allow characters commonly used in math expressions.
    if not EXPR_RE.fullmatch(clean):
        return False

    # Must contain at least one digit or variable.
    if not re.search(r"[0-9A-Za-z]", clean):
        return False

    return True


def expr_supported_in_raw(expr: str, raw: str) -> bool:
    """
    Reject expressions that are not reasonably grounded in OCR raw text.

    This supports complete expressions such as:
        9-3/1/3+1
        2*(5+3)
        1/2+3/4
        8+11=?
    """

    if not raw or not expr:
        return False

    clean_expr = _clean_expression(expr)
    clean_raw = _clean_raw(raw)

    if not _is_valid_expression(clean_expr):
        return False

    # Remove an unknown marker when comparing with OCR.
    expr_without_question = clean_expr.replace("?", "")
    raw_without_question = clean_raw.replace("?", "")

    # Exact match is the strongest signal.
    if expr_without_question in raw_without_question:
        return True

    # If OCR contains spaces or different formatting, compare
    # the individual meaningful characters in order.
    expr_chars = [
        c
        for c in expr_without_question
        if not c.isspace()
    ]

    raw_chars = [
        c
        for c in raw_without_question
        if not c.isspace()
    ]

    if not expr_chars:
        return False

    # Normalize multiplication/division symbols.
    expr_chars = [
        "*" if c in ("×",) else "/" if c in ("÷",) else c
        for c in expr_chars
    ]

    raw_chars = [
        "*" if c in ("×",) else "/" if c in ("÷",) else c
        for c in raw_chars
    ]

    normalized_expr = "".join(expr_chars)
    normalized_raw = "".join(raw_chars)

    if normalized_expr in normalized_raw:
        return True

    # For vertical worksheet expressions, OCR may insert
    # newlines between the numbers/operators.
    # Try a flexible regex representation.
    escaped_parts = []

    for char in normalized_expr:
        escaped_parts.append(re.escape(char))

    flexible_pattern = r"\s*".join(escaped_parts)

    if re.search(flexible_pattern, raw, re.IGNORECASE | re.MULTILINE):
        return True

    return False


def dedupe_expressions(expressions: list[str]) -> list[str]:
    """
    Clean, validate and deduplicate OCR expressions.

    Keeps complete expressions instead of restricting them
    to number-operator-number.
    """

    seen: set[str] = set()
    out: list[str] = []

    for expr in expressions:
        clean = _clean_expression(expr)

        # Remove trailing question marker only for dedupe purposes
        # when the expression is otherwise valid.
        if not _is_valid_expression(clean):
            continue

        if clean in seen:
            continue

        seen.add(clean)
        out.append(clean)

    return out


def filter_valid_expressions(
    expressions: list[str],
    raw: str,
) -> list[str]:
    """
    Keep only expressions that:
    1. have valid math-expression characters
    2. are grounded in the OCR raw text
    3. are not duplicates
    """

    if not expressions:
        return []

    seen: set[str] = set()
    out: list[str] = []

    for expr in expressions:
        clean = _clean_expression(expr)

        if not _is_valid_expression(clean):
            continue

        if clean in seen:
            continue

        if expr_supported_in_raw(clean, raw):
            seen.add(clean)
            out.append(clean)

    return out


def filter_single_digit_addition(
    exprs: list[str],
) -> list[str]:
    """
    Keep only genuine single-digit addition expressions.

    Examples:
        2+5  -> kept
        7+8  -> kept
        12+5 -> rejected
        2-5  -> rejected
        2+5*3 -> rejected
    """

    out: list[str] = []

    for expr in exprs:
        clean = _clean_expression(expr)

        match = SIMPLE_ADD_RE.fullmatch(clean)

        if match:
            out.append(
                f"{match.group(1)}+{match.group(2)}"
            )

    return out