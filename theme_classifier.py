import re


LEVERAGED_THEME = "Leveraged / Inverse"
CRYPTO_THEME = "Crypto / Digital Assets"
OPTIONS_INCOME_THEME = "Options Income / Covered Call"
FIXED_INCOME_THEME = "Fixed Income / Credit"
COMMODITIES_THEME = "Commodities / Gold / Energy"
INTERNATIONAL_THEME = "International / Emerging Markets"
DIVIDEND_THEME = "Dividend / Income"
TARGET_MATURITY_THEME = "Target Maturity"
FACTOR_THEME = "Factor / Quant / Active"
THEMATIC_EQUITY_THEME = "Thematic Equity"
OTHER_THEME = "Other"
THEME_ORDER = (
    LEVERAGED_THEME,
    CRYPTO_THEME,
    OPTIONS_INCOME_THEME,
    FIXED_INCOME_THEME,
    COMMODITIES_THEME,
    INTERNATIONAL_THEME,
    DIVIDEND_THEME,
    TARGET_MATURITY_THEME,
    FACTOR_THEME,
    THEMATIC_EQUITY_THEME,
    OTHER_THEME,
)

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

OPTIONS_INCOME_TERMS = (
    "buffer",
    "buywrite",
    "covered call",
    "defined outcome",
    "downside protection",
    "income premium",
    "options income",
    "premium income",
    "putwrite",
    "tail risk",
)

FIXED_INCOME_TERMS = (
    "aggregate bond",
    "bank loan",
    "bond",
    "core plus",
    "credit",
    "debt",
    "duration",
    "fixed income",
    "high yield",
    "income opportunities",
    "loan",
    "mortgage",
    "municipal",
    "muni",
    "securitized",
    "treasury",
    "ultrashort bond",
)

COMMODITIES_TERMS = (
    "agriculture",
    "commodity",
    "copper",
    "energy",
    "gold",
    "metals",
    "natural gas",
    "oil",
    "silver",
    "uranium",
)

INTERNATIONAL_TERMS = (
    "asia",
    "china",
    "developed ex us",
    "emerging market",
    "emerging markets",
    "europe",
    "ex us",
    "frontier",
    "global ex us",
    "international",
    "japan",
    "latin america",
)

DIVIDEND_TERMS = (
    "dividend",
    "equity income",
    "free cash flow",
    "high income",
    "shareholder yield",
    "yield",
)

TARGET_MATURITY_TERMS = (
    "target maturity",
    "defined maturity",
    "maturity bond",
)

FACTOR_TERMS = (
    "active",
    "alpha",
    "dynamic",
    "equal weight",
    "factor",
    "fundamental",
    "low volatility",
    "momentum",
    "quality",
    "quant",
    "value",
)

THEMATIC_EQUITY_TERMS = (
    "ai",
    "artificial intelligence",
    "biotech",
    "cybersecurity",
    "data center",
    "defense",
    "disruptive",
    "electric vehicle",
    "fintech",
    "infrastructure",
    "innovation",
    "nuclear",
    "robotics",
    "semiconductor",
    "space",
    "technology",
)


def _normalized_name(name: str) -> str:
    text = str(name or "").lower()
    text = text.replace("/", " ")
    return " ".join(text.split())


def _has_theme_term(text: str, terms: tuple[str, ...]) -> bool:
    for term in terms:
        if " " in term and term in text:
            return True
        if re.search(rf"\b{re.escape(term)}\b", text):
            return True
    return False


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
    return _has_theme_term(text, CRYPTO_TERMS)


def classify_primary_theme(name: str) -> str:
    text = _normalized_name(name)

    if _is_leveraged_or_inverse(name):
        return LEVERAGED_THEME
    if _is_crypto_or_digital_assets(name):
        return CRYPTO_THEME
    if _has_theme_term(text, OPTIONS_INCOME_TERMS):
        return OPTIONS_INCOME_THEME
    if _has_theme_term(text, TARGET_MATURITY_TERMS):
        return TARGET_MATURITY_THEME
    if _has_theme_term(text, FIXED_INCOME_TERMS):
        return FIXED_INCOME_THEME
    if _has_theme_term(text, COMMODITIES_TERMS):
        return COMMODITIES_THEME
    if _has_theme_term(text, INTERNATIONAL_TERMS):
        return INTERNATIONAL_THEME
    if _has_theme_term(text, DIVIDEND_TERMS):
        return DIVIDEND_THEME
    if _has_theme_term(text, FACTOR_TERMS):
        return FACTOR_THEME
    if _has_theme_term(text, THEMATIC_EQUITY_TERMS):
        return THEMATIC_EQUITY_THEME
    return OTHER_THEME


def summarize_themes(names) -> dict[str, int]:
    counts = {theme: 0 for theme in THEME_ORDER}
    for name in names:
        theme = classify_primary_theme(name)
        counts[theme] = counts.get(theme, 0) + 1
    return counts
