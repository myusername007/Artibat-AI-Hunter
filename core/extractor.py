import re


PHONE_REGEX = re.compile(
    r"(?:(?:\+|00)33|0)\s*[1-9](?:[\s.\-]?\d{2}){4}"
)
EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
SURFACE_REGEX = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*m[²2]", re.IGNORECASE
)
BUDGET_REGEX = re.compile(
    r"(\d+(?:\s?\d{3})*)\s*(?:€|euros?|eur)", re.IGNORECASE
)
URGENCY_KEYWORDS = [
    "urgent", "rapidement", "dès que possible", "asap",
    "immédiatement", "vite", "pressé"
]


def extract_phone(text: str) -> str | None:
    match = PHONE_REGEX.search(text)
    if match:
        return re.sub(r"[\s.\-]", "", match.group())
    return None


def extract_email(text: str) -> str | None:
    match = EMAIL_REGEX.search(text)
    return match.group() if match else None


def extract_surface(text: str) -> float | None:
    match = SURFACE_REGEX.search(text)
    if match:
        return float(match.group(1).replace(",", "."))
    return None


def extract_budget(text: str) -> float | None:
    match = BUDGET_REGEX.search(text)
    if match:
        raw = match.group(1).replace(" ", "")
        return float(raw)
    return None


def has_urgency(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in URGENCY_KEYWORDS)