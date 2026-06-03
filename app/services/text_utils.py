import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().split())


def section_matches(left: str, right: str) -> bool:
    return normalize_text(left) == normalize_text(right)

