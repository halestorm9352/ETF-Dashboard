import re


LEVERAGED_THEME = "Leveraged / Inverse"
CRYPTO_THEME = "Crypto / Digital Assets"
OTHER_THEME = "Other"
THEME_ORDER = (LEVERAGED_THEME, CRYPTO_THEME, OTHER_THEME)

CRYPTO_TERMS = (
    "bitcoin",
    "blockchain",
    "cardano",
    "crypto",
    "cryptocurrency",
    "digital asset",
    "dogecoin",
    "btc",
    "ether",
    "eth",
    "ethereum",
    "litecoin",
    "solana",
    "xrp",
)


def _normalized_name(name: str) -> str:
    text = str(name or "").lower()
    text = text.replace("/", " ")
    return " ".join(text.split())


def _is_leveraged_or_inverse(name: str) -> bool:
    text = _normalized_name(name)
    if not text:
        return False

    if re.search(r"\blong[\s-]+short\b", text):
        return False

    if re.search(r"\b[+-]?\d+(?:\.\d+)?x\b", text, re.IGNORECASE):
        return True

    if re.search(r"\b(leveraged|inverse|ultra|ultrapro|ultrashort|geared)\b", text):
        return True

    if re.search(r"\b(bull|bear)\b", text):
        return True

    if re.search(r"\bshort\b", text) and not re.search(
        r"\bshort\s+(duration|term|maturity|bond|credit|income|municipal|muni|treasury)\b",
        text,
    ):
        return True

    return False


def _is_crypto_or_digital_assets(name: str) -> bool:
    text = _normalized_name(name)
    for term in CRYPTO_TERMS:
        if " " in term and term in text:
            return True
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


def classify_primary_theme(name: str) -> str:
    if _is_leveraged_or_inverse(name):
        return LEVERAGED_THEME
    if _is_crypto_or_digital_assets(name):
        return CRYPTO_THEME
    return OTHER_THEME


def summarize_themes(names) -> dict[str, int]:
    counts = {theme: 0 for theme in THEME_ORDER}
    for name in names:
        theme = classify_primary_theme(name)
        counts[theme] = counts.get(theme, 0) + 1
    return counts
