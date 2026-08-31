import re

MATH_EXPR = re.compile(
    r"(\d+)\s*([+\-*/])\s*(\d+)(?:\s*=\s*(\d+|\?))?",
    re.IGNORECASE,
)

SIMPLE_ADD = re.compile(r"^\d{1,2}[+\-]\d{1,2}$")

SKIP_LINE = re.compile(
    r"^(single|digit|addition|subtraction|worksheet|name|date|page|www\.|http)",
    re.IGNORECASE,
)

WORKSHEET_HINT = re.compile(
    r"single\s*digit|digit\s*addition|worksheet|sheet\s*\d|"
    r"solve\s+the\s+problems|education\.com|suncatcher",
    re.IGNORECASE,
)

ADD_PAIR = re.compile(r"(\d{1,2})\s*\+\s*(\d{1,2})")


def _clean_expr(a: str, op: str, b: str, rhs: str | None = None) -> str:
    expr = f"{a}{op}{b}"
    if rhs is not None and rhs not in ("", "?"):
        expr += f"={rhs}"
    return expr


def _normalize_expr(expr: str) -> str:
    s = expr.strip()
    if "=" in s and s.endswith("?"):
        s = s.split("=")[0].strip()
    return re.sub(r"\s+", "", s)


def is_worksheet_like(text: str) -> bool:
    return bool(WORKSHEET_HINT.search(text or ""))


def scan_addition_pairs(text: str, *, single_digit_only: bool = False) -> list[str]:
    """Find every a+b in run-on OCR (e.g. '1 + 7 +6 7 +5')."""
    if not text:
        return []
    fixed = text
    for old, new in (("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("|", "1")):
        fixed = fixed.replace(old, new)

    found: list[str] = []
    seen: set[str] = set()
    for m in ADD_PAIR.finditer(fixed):
        a, b = m.group(1), m.group(2)
        expr = _normalize_expr(f"{a}+{b}")
        if single_digit_only and not re.match(r"^\d\+\d$", expr):
            continue
        if expr not in seen:
            seen.add(expr)
            found.append(expr)
    return found


def is_single_comprehensive_problem(text: str) -> bool:
    """One problem to solve as a whole — not a worksheet of separate items."""
    t = (text or "").strip()
    if not t:
        return True

    lower = t.lower()

    if is_worksheet_like(t):
        pairs = scan_addition_pairs(t, single_digit_only=True)
        if len(pairs) >= 2:
            return False

    if re.search(
        r"\b(solve|find|calculate|evaluate|simplify|factor|expand|derive|"
        r"integral|equation|value of|how much|what is|whats)\b",
        lower,
    ):
        if re.search(r"solve\s+the\s+problems", lower) and is_worksheet_like(t):
            pass
        else:
            return True

    if re.search(r"[xyzXYZ]", t):
        return True

    if re.search(r"\^|\*\*|sqrt|√|log|sin|cos|tan|\(|\)|/", lower):
        return True

    lines = [ln.strip() for ln in t.replace("\r", "").split("\n") if ln.strip()]
    non_skip = [ln for ln in lines if not SKIP_LINE.match(ln)]

    if len(non_skip) <= 1:
        compact = re.sub(r"\s+", "", non_skip[0] if non_skip else t)
        ops = len(re.findall(r"[+\-*/]", compact))
        if ops >= 2 and not re.fullmatch(r"(\d{1,2}[+\-]\d{1,2})+", compact):
            return True
        if "=" in compact and len(compact) > 12:
            return True
        if re.search(r"\d{2,}", compact) and ops >= 1:
            return True
    else:
        if any("=" in ln for ln in non_skip) and re.search(r"[xyzXYZ]", t, re.I):
            return True
        if not all(SIMPLE_ADD.match(re.sub(r"\s+", "", ln)) for ln in non_skip):
            if any(re.search(r"[xyzXYZ=^*()]", ln) for ln in non_skip):
                return True

    return False


def is_worksheet_batch(text: str, expressions: list[str]) -> bool:
    """Many separate tiny problems (e.g. 2+1, 7+6 on a worksheet)."""
    if not expressions or len(expressions) < 2:
        return False
    if is_single_comprehensive_problem(text):
        return False
    return all(SIMPLE_ADD.match(_normalize_expr(e)) for e in expressions)


def _exprs_are_fragments(text: str, expressions: list[str]) -> bool:
    """e.g. '2+3+4+5' wrongly split into 2+3, 3+4, 4+5."""
    if len(expressions) < 2:
        return False
    if is_worksheet_like(text) and len(expressions) >= 2:
        return False
    compact = re.sub(r"\s+", "", text)
    total_ops = len(re.findall(r"[+\-*/]", compact))
    if total_ops > len(expressions):
        return True
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) <= 1:
        return True
    return False


def extract_expressions_from_text(text: str) -> list[str]:
    if not text:
        return []

    if is_worksheet_like(text):
        pairs = scan_addition_pairs(text, single_digit_only=True)
        if len(pairs) >= 2:
            return pairs[:50]

    if is_single_comprehensive_problem(text):
        return []

    fixed = text
    for old, new in (("O", "0"), ("o", "0"), ("l", "1"), ("I", "1"), ("|", "1")):
        fixed = fixed.replace(old, new)

    found: list[str] = []
    seen: set[str] = set()

    for m in MATH_EXPR.finditer(fixed):
        rhs = m.group(4) if m.lastindex and m.lastindex >= 4 else None
        expr = _normalize_expr(_clean_expr(m.group(1), m.group(2), m.group(3), rhs))
        if expr and expr not in seen:
            seen.add(expr)
            found.append(expr)

    lines = [ln.strip() for ln in fixed.replace("\r", "").split("\n") if ln.strip()]
    i = 0
    while i < len(lines) - 1:
        if SKIP_LINE.match(lines[i]):
            i += 1
            continue
        top = re.match(r"^(\d+)$", lines[i])
        plus = re.match(r"^\+?\s*(\d+)\s*$", lines[i + 1])
        if top and plus:
            expr = _normalize_expr(f"{top.group(1)}+{plus.group(1)}")
            if expr not in seen:
                seen.add(expr)
                found.append(expr)
            i += 2
            continue
        i += 1

    for line in lines:
        if SKIP_LINE.match(line):
            continue
        compact = _normalize_expr(line)
        if SIMPLE_ADD.match(compact) and compact not in seen:
            seen.add(compact)
            found.append(compact)

    return found[:50]


def split_questions(text: str) -> list[str]:
    """Return one item for a single problem, or many for worksheet batches."""
    t = (text or "").strip()
    if not t:
        return []

    if is_single_comprehensive_problem(t):
        return [t]

    exprs = extract_expressions_from_text(t)

    if exprs and _exprs_are_fragments(t, exprs):
        return [t]

    if is_worksheet_batch(t, exprs):
        return exprs

    if is_worksheet_like(t):
        pairs = scan_addition_pairs(t, single_digit_only=True)
        if len(pairs) >= 2:
            return pairs

    if len(exprs) == 1:
        return exprs

    if exprs and len(exprs) > 1 and not is_worksheet_like(t):
        return [t]

    lines = [
        ln.strip()
        for ln in t.replace("\r", "").split("\n")
        if ln.strip() and not SKIP_LINE.match(ln.strip())
    ]
    if len(lines) == 1:
        return lines
    if len(lines) > 1 and is_single_comprehensive_problem(t):
        return [t]

    if len(lines) > 1 and all(
        SIMPLE_ADD.match(re.sub(r"\s+", "", ln)) for ln in lines
    ):
        return [_normalize_expr(re.sub(r"\s+", "", ln)) for ln in lines]

    return [t] if t else lines[:50]


def format_for_client(raw_text: str, expressions: list[str]) -> str:
    if is_single_comprehensive_problem(raw_text or ""):
        return (raw_text or "").strip()[:4000]

    exprs = [_normalize_expr(e) for e in expressions if e and e.strip()]
    if exprs and is_worksheet_batch(raw_text or "", exprs):
        return "\n".join(exprs)
    if exprs:
        return "\n".join(exprs)
    cleaned = re.sub(r"[ \t]+", " ", (raw_text or "").strip())
    return cleaned[:4000] if cleaned else ""
