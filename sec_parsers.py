import html
import re
from typing import Any

from bs4 import BeautifulSoup

from config import INVALID_TICKERS
from vehicle_classifier import (
    UNKNOWN_VEHICLE,
    classify_vehicle,
    is_share_class_name,
    uses_parent_series_identity,
)


MODULE_CONTRACT_VERSION = 12
# Continue the integer previously stamped from MODULE_CONTRACT_VERSION; stored
# rows are version 12, so 13 was the first dedicated parser version. Version 14
# bounds primary-document identity extraction to prospectus front matter, and
# version 15 adds exchange-listing evidence to vehicle classification. Bump this
# whenever parser logic, fetch reach, or parse-time enrichment changes parsed
# event values.
PARSER_VERSION = 15
EFFECTIVENESS_LEGACY_WINDOW_CHARS = 120_000
EFFECTIVENESS_SCAN_CAP_CHARS = 1_000_000
EFFECTIVENESS_WINDOW_BEFORE_CHARS = 2_000
EFFECTIVENESS_WINDOW_AFTER_CHARS = 8_000
EFFECTIVENESS_ANCHOR = "it is proposed that this filing will become effective"
EFFECTIVENESS_FALLBACK_ANCHOR = "pursuant to paragraph"


def clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    decoded = re.sub(r"[\u2000-\u200f\u2028-\u202f\u205f\u2060\ufeff]", " ", decoded)
    return " ".join(decoded.split())


def detect_exchange_listed(text: str) -> bool:
    if not text:
        return False

    cleaned_text = clean_html_text(text)
    if re.search(
        r"\bas with all exchange[- ]traded funds\b",
        cleaned_text,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"\b(?:the\s+)?fund\s+is\s+an?\s+exchange[- ]traded fund\b",
        cleaned_text,
        re.IGNORECASE,
    ):
        return True

    shares = r"(?:fund(?:['\u2019]s)?\s+shares|shares\s+of\s+the\s+fund)"
    exchange = (
        r"(?:NYSE(?:\s+Arca)?|Cboe(?:\s+BZX)?|Nasdaq|BZX|"
        r"national securities exchange|[A-Z][A-Za-z&.\- ]{0,40}\s+Exchange)"
    )
    if re.search(
        rf"\b{shares}\b.{{0,140}}\b(?:listed(?:\s+and\s+traded)?|traded)\b"
        rf".{{0,80}}\b(?:on|upon)\s+(?:the\s+)?{exchange}\b",
        cleaned_text,
        re.IGNORECASE,
    ):
        return True

    for market_match in re.finditer(
        rf"\b{shares}\b.{{0,180}}\b(?:trade|traded|bought\s+and\s+sold)\b"
        r".{0,120}\bat market prices\b",
        cleaned_text,
        re.IGNORECASE,
    ):
        context = cleaned_text[
            max(0, market_match.start() - 200) : market_match.end() + 400
        ]
        if re.search(rf"\b{exchange}\b", context, re.IGNORECASE):
            return True
    return False


def normalize_etf_name(value: str) -> str:
    cleaned = clean_html_text(value).upper()
    cleaned = re.sub(r"[^A-Z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def _clean_series_entry_name(value: str) -> str:
    cleaned = clean_html_text(value)
    cleaned = re.sub(r"^(?:new|existing|active|inactive)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _split_series_contract_name_and_ticker(value: str) -> tuple[str, str]:
    cleaned = _clean_series_entry_name(value)
    ticker_match = re.search(r"\s+([A-Z]{3,4})$", cleaned)
    if not ticker_match:
        return cleaned, ""

    ticker = ticker_match.group(1).upper()
    if ticker in INVALID_TICKERS:
        return cleaned, ""
    return cleaned[: ticker_match.start()].strip(), ticker


def extract_etf_name(text: str) -> str:
    cleaned_text = clean_html_text(text)

    bracketed_pipe_match = re.search(
        r'\[\s*[A-Z]{1,8}\s*\]\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if bracketed_pipe_match:
        return bracketed_pipe_match.group(1).strip()

    name_pipe_match = re.search(
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s*\|\s*[A-Z]{1,8}\s*\|',
        cleaned_text,
        re.IGNORECASE,
    )
    if name_pipe_match:
        return name_pipe_match.group(1).strip()

    pipe_match = re.search(
        r'([A-Z]{2,6})\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if pipe_match:
        return pipe_match.group(2).strip()

    duplicated_header_match = re.search(
        r'\b[A-Z]{2,8}\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,120}?(ETF|Fund))\s+'
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if duplicated_header_match:
        return duplicated_header_match.group(3).strip()

    listed_name_match = re.search(
        r'\b([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if listed_name_match:
        return listed_name_match.group(1).strip()

    series_text_match = re.search(
        r'Series\s+S\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+Class/Contract',
        cleaned_text,
        re.IGNORECASE,
    )
    if series_text_match:
        return series_text_match.group(1).strip()

    generic_series_text_match = re.search(
        r'Series\s+S\d+\s+(?:new|existing|active|inactive)?\s*'
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?)\s+'
        r'Class/Contract\s+C\d+\s+'
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?)(?=\s+(?:Mailing\s+Address|Business\s+Address|$))',
        cleaned_text,
        re.IGNORECASE,
    )
    if generic_series_text_match:
        name, _ticker = _split_series_contract_name_and_ticker(generic_series_text_match.group(2))
        if name:
            return name

    series_match = re.search(
        r'<td[^>]*class="seriesName"[^>]*>.*?</td>\s*'
        r'<td[^>]*class="seriesCell"[^>]*>.*?</td>\s*'
        r'<td[^>]*class="seriesCell"[^>]*>(.*?)</td>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if series_match:
        name = clean_html_text(series_match.group(1))
        if name:
            return name

    contract_match = re.search(
        r'<tr[^>]*class="contractRow"[^>]*>.*?'
        r'<td[^>]*>.*?</td>\s*<td[^>]*>.*?</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if contract_match:
        name = clean_html_text(contract_match.group(1))
        if name:
            return name

    heading_match = re.search(
        r'<oef:RiskReturnHeading[^>]*>(.*?)</oef:RiskReturnHeading>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if heading_match:
        name = clean_html_text(heading_match.group(1))
        if name:
            return name

    fallback = re.search(r'([A-Z][A-Za-z0-9&\s\-]{5,100}(ETF|Fund))', cleaned_text)
    return fallback.group(1).strip() if fallback else "N/A"


def extract_ticker(
    text: str,
    named_ticker_pairs: list[dict[str, str]] | None = None,
) -> str:
    cleaned_text = clean_html_text(text)

    named_pairs = (
        named_ticker_pairs
        if named_ticker_pairs is not None
        else extract_named_ticker_pairs(text)
    )
    if len(named_pairs) == 1:
        single_ticker = named_pairs[0].get("ticker", "")
        if single_ticker and single_ticker != "Not Listed":
            return single_ticker

    bracketed_pipe_match = re.search(
        r'\[\s*([A-Z]{3,4})\s*\]\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if bracketed_pipe_match:
        ticker = bracketed_pipe_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    contract_row_match = re.search(
        r'<tr[^>]*class="contractRow"[^>]*>(.*?)</tr>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if contract_row_match:
        td_matches = re.findall(r'<td[^>]*>(.*?)</td>', contract_row_match.group(1), re.IGNORECASE | re.DOTALL)
        if td_matches:
            ticker_candidate = clean_html_text(td_matches[-1]).upper()
            if re.fullmatch(r"[A-Z]{3,4}", ticker_candidate) and ticker_candidate not in INVALID_TICKERS:
                return ticker_candidate

    duplicated_proshares_name_match = re.search(
        r'\b(?P<ticker>[A-Z]{3,4})\s+'
        r'(?P<short_name>[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,120}?(?:ETF|Fund))\s+'
        r'ProShares\s+(?P=short_name)\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if duplicated_proshares_name_match:
        ticker = duplicated_proshares_name_match.group("ticker").upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    duplicated_full_name_match = re.search(
        r'\b(?P<ticker>[A-Z]{3,4})\s+'
        r'(?P<full_name>ProShares\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,160}?(?:ETF|Fund))\s+'
        r'(?P=full_name)\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if duplicated_full_name_match:
        ticker = duplicated_full_name_match.group("ticker").upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    quoted_prose_match = re.search(
        r'\bunder\s+the\s+ticker\s+symbol\s+"([A-Z]{3,4})\.?"',
        cleaned_text,
        re.IGNORECASE,
    )
    if quoted_prose_match:
        ticker = quoted_prose_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    name_ticker_pipe_match = re.search(
        r'[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund)\s*\|\s*([A-Z]{3,4})\s*\|',
        cleaned_text,
        re.IGNORECASE,
    )
    if name_ticker_pipe_match:
        ticker = name_ticker_pipe_match.group(2).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    raw_label_match = re.search(r'Ticker Symbol', text, re.IGNORECASE)
    if raw_label_match:
        ticker_snippet = clean_html_text(text[raw_label_match.start(): raw_label_match.start() + 2000])
        ticker_label_match = re.search(
            r'Ticker Symbol\s*:?\s*([A-Z]{3,4})\b',
            ticker_snippet,
            re.IGNORECASE,
        )
        if ticker_label_match:
            ticker = ticker_label_match.group(1).upper()
            if ticker not in INVALID_TICKERS:
                return ticker

    prospectus_table_match = re.search(
        r'Fund\s+Ticker\s+Principal U\.S\. Listing Exchange.*?(?:ETF|Fund)\s+([A-Z]{3,4})\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if prospectus_table_match:
        ticker = prospectus_table_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    pipe_match = re.search(
        r'([A-Z]{3,4})\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if pipe_match:
        ticker = pipe_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    ticker_cell_match = re.search(
        r'Ticker Symbol\s+([A-Z]{3,4})',
        cleaned_text,
        re.IGNORECASE,
    )
    if ticker_cell_match:
        ticker = ticker_cell_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    series_ticker_match = re.search(
        r'Class/Contract\s+C\d+\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund)\s+([A-Z]{3,4})(?=\s+(?:Status\s+Name\s+Ticker\s+Symbol|Mailing\s+Address|Business\s+Address|$))',
        cleaned_text,
        re.IGNORECASE,
    )
    if series_ticker_match:
        ticker = series_ticker_match.group(2).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    return ""


def sanitize_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2,5}", ticker) and ticker not in INVALID_TICKERS:
        return ticker
    return "Not Listed"


def extract_filer_name(text: str) -> str:
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")
    company = soup.select_one("span.companyName")
    if company:
        company_text = clean_html_text(company.get_text(" ", strip=True))
        company_text = re.sub(r"\s*\(Filer\).*", "", company_text, flags=re.IGNORECASE)
        if company_text:
            return company_text.upper()

    company_match = re.search(
        r'<span class="companyName">(.*?)\s*\(Filer\)',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if company_match:
        return clean_html_text(company_match.group(1)).upper()

    line_text = soup.get_text("\n")
    lines = [clean_html_text(line) for line in line_text.splitlines()]
    for index, line in enumerate(lines):
        if "Exact Name of Registrant as Specified in Charter" not in line:
            continue
        for previous_line in reversed(lines[max(0, index - 5):index]):
            if previous_line and re.search(r"[A-Za-z]", previous_line):
                return previous_line.upper()

    exact_name_match = re.search(
        r'([A-Za-z0-9&,\.\-\s]+)\s*\(Exact Name of Registrant as Specified in Charter\)',
        clean_html_text(text),
        re.IGNORECASE,
    )
    if exact_name_match:
        return " ".join(exact_name_match.group(1).split()).upper()

    return ""


def _is_checked_effectiveness_marker(value: str) -> bool:
    marker = html.unescape(str(value or "")).strip().upper()
    compact = re.sub(r"[\s\[\]\(\)]+", "", marker)
    return compact in {
        "X",
        "\u00de",
        "\u00fe",
        "\u2611",
        "\u2612",
        "\u25a0",
        "\u25cf",
    }


_EFFECTIVENESS_MARKER_RE = re.compile(
    r"\[\s*(?:X)?\s*\]|[\u00a8\u00fe\u2610\u2611\u2612\u25a0\u25cf]|\b[OQX]\b",
    re.IGNORECASE,
)


def _effectiveness_cover_window(text: str) -> str:
    scan_text = text[:EFFECTIVENESS_SCAN_CAP_CHARS]
    lowered = scan_text.lower()
    anchor_offset = lowered.find(EFFECTIVENESS_ANCHOR)
    if anchor_offset < 0:
        anchor_offset = lowered.find(EFFECTIVENESS_FALLBACK_ANCHOR)
    if anchor_offset < 0:
        return text[:EFFECTIVENESS_LEGACY_WINDOW_CHARS]
    return text[
        max(0, anchor_offset - EFFECTIVENESS_WINDOW_BEFORE_CHARS):
        anchor_offset + EFFECTIVENESS_WINDOW_AFTER_CHARS
    ]


def _nearest_effectiveness_marker(value: str, phrase_offset: int) -> str:
    prefix = value[max(0, phrase_offset - 160):phrase_offset]
    matches = list(_EFFECTIVENESS_MARKER_RE.finditer(prefix))
    return matches[-1].group(0) if matches else ""


def _checked_effectiveness_option(value: str, options):
    lowered = value.lower()
    for phrase, basis, days, label in options:
        for phrase_match in re.finditer(re.escape(phrase), lowered):
            marker = _nearest_effectiveness_marker(value, phrase_match.start())
            if _is_checked_effectiveness_marker(marker):
                return {
                    "effectiveness_basis": basis,
                    "effectiveness_days": days,
                    "designated_effective_date": "",
                    "effectiveness_label": label,
                }
    return None


_DESIGNATED_EFFECTIVE_DATE_RE = re.compile(
    r"\bon\s+\(?([A-Z][a-z]+\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\)?\s+"
    r"pursuant\s+to\s+(?:paragraph\s+\((a|b)\)|rule\s+485\s*\((a|b)\)|"
    r"rule\s+485,?\s+paragraph\s+\((a|b)\))",
    re.IGNORECASE,
)


def _designated_effectiveness_result(match) -> dict[str, Any]:
    designated_date = match.group(1)
    paragraph = (match.group(2) or match.group(3) or match.group(4)).lower()
    return {
        "effectiveness_basis": f"rule_485_{paragraph}_designated_date",
        "effectiveness_days": None,
        "designated_effective_date": designated_date,
        "effectiveness_label": (
            f"Designated date {designated_date} (Rule 485({paragraph}))"
        ),
    }


def _checked_designated_effectiveness(value: str):
    for match in _DESIGNATED_EFFECTIVE_DATE_RE.finditer(value):
        marker = _nearest_effectiveness_marker(value, match.start())
        if _is_checked_effectiveness_marker(marker):
            return _designated_effectiveness_result(match)
    return None


def extract_rule_485_effectiveness(text: str) -> dict[str, Any]:
    default = {
        "effectiveness_basis": "",
        "effectiveness_days": None,
        "designated_effective_date": "",
        "effectiveness_label": "",
    }
    if not text:
        return default

    cover_page_text = _effectiveness_cover_window(text)
    soup = BeautifulSoup(cover_page_text, "html.parser")
    options = (
        (
            "immediately upon filing",
            "rule_485_b_immediate",
            0,
            "Immediately upon filing (Rule 485(b))",
        ),
        (
            "60 days after filing",
            "rule_485_a1_60_days",
            60,
            "60 days after filing (Rule 485(a)(1))",
        ),
        (
            "75 days after filing",
            "rule_485_a2_75_days",
            75,
            "75 days after filing (Rule 485(a)(2))",
        ),
    )

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        cell_texts = [clean_html_text(cell.get_text(" ", strip=True)) for cell in cells]
        row_text = " ".join(cell_texts)
        row_html = str(row)
        if re.search(r"<input[^>]+checked", row_html, re.IGNORECASE):
            lower_row_text = row_text.lower()
            for phrase, basis, days, label in options:
                if phrase in lower_row_text:
                    return {
                        "effectiveness_basis": basis,
                        "effectiveness_days": days,
                        "designated_effective_date": "",
                        "effectiveness_label": label,
                    }
            designated_match = _DESIGNATED_EFFECTIVE_DATE_RE.search(row_text)
            if designated_match:
                return _designated_effectiveness_result(designated_match)

        selected_option = _checked_effectiveness_option(row_text, options)
        if selected_option:
            return selected_option
        designated_result = _checked_designated_effectiveness(row_text)
        if designated_result:
            return designated_result

    cleaned_text = clean_html_text(cover_page_text)
    selected_option = _checked_effectiveness_option(cleaned_text, options)
    if selected_option:
        return selected_option
    designated_result = _checked_designated_effectiveness(cleaned_text)
    if designated_result:
        return designated_result

    direct_designated_match = re.search(
        rf"{re.escape(EFFECTIVENESS_ANCHOR)}\s+"
        rf"{_DESIGNATED_EFFECTIVE_DATE_RE.pattern}",
        cleaned_text,
        re.IGNORECASE,
    )
    if direct_designated_match:
        return _designated_effectiveness_result(direct_designated_match)

    return default


def extract_series_entries(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    soup = BeautifulSoup(text, "html.parser")
    parsed_entries: list[dict[str, str]] = []
    current_series_id = ""
    current_series_name = ""
    for row in soup.find_all("tr"):
        series_cell = row.find("td", class_="seriesName")
        if series_cell:
            series_match = re.search(r"\b(S\d{9})\b", series_cell.get_text(" ", strip=True))
            current_series_id = series_match.group(1) if series_match else ""
            series_name_cells = row.find_all("td", class_="seriesCell")
            current_series_name = (
                clean_html_text(series_name_cells[-1].get_text(" ", strip=True))
                if series_name_cells
                else ""
            )
            continue

        row_classes = row.get("class", [])
        if "contractRow" not in row_classes:
            continue
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        class_match = re.search(r"\b(C\d{9})\b", cells[0].get_text(" ", strip=True))
        class_id = class_match.group(1) if class_match else ""
        class_name = clean_html_text(cells[2].get_text(" ", strip=True))
        ticker = clean_html_text(cells[3].get_text(" ", strip=True)).upper()
        if not class_name:
            continue
        structured_ticker = sanitize_ticker(ticker)
        ticker = "" if structured_ticker == "Not Listed" else structured_ticker
        entry = {
            "etf_name": (
                current_series_name
                if current_series_name and is_share_class_name(class_name)
                else class_name
            ),
            "class_name": class_name,
            "ticker": ticker if ticker not in INVALID_TICKERS else "",
            "series_id": current_series_id,
            "series_name": current_series_name,
            "class_id": class_id,
        }
        entry["vehicle"] = classify_vehicle(entry)
        entry["identity_scope"] = (
            "series" if uses_parent_series_identity(entry) else "class"
        )
        parsed_entries.append(entry)

    if parsed_entries:
        return parsed_entries

    entries = []
    contract_rows = re.findall(
        r'<tr[^>]*class="contractRow"[^>]*>.*?<td[^>]*>.*?</td>\s*<td[^>]*>.*?</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    for name_html, ticker_html in contract_rows:
        name = clean_html_text(name_html)
        ticker = clean_html_text(ticker_html).upper()
        if not name:
            continue
        if ticker and not re.fullmatch(r"[A-Z]{3,4}", ticker):
            ticker = ""
        entries.append(
            {
                "etf_name": name,
                "class_name": name,
                "ticker": ticker if ticker not in INVALID_TICKERS else "",
                "series_id": "",
                "series_name": "",
                "class_id": "",
                "vehicle": UNKNOWN_VEHICLE,
                "identity_scope": "name",
            }
        )

    if entries:
        return entries

    cleaned_text = clean_html_text(text)
    text_matches = re.findall(
        r'Series\s+S\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+'
        r'Class/Contract\s+C\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))'
        r'(?:\s+([A-Z]{3,4}))?(?=\s+(?:Status\s+Name\s+Ticker\s+Symbol|Mailing\s+Address|Business\s+Address|$))',
        cleaned_text,
        re.IGNORECASE,
    )
    for _series_name, _series_suffix, contract_name, _contract_suffix, ticker in text_matches:
        if not contract_name:
            continue
        entries.append(
            {
                "etf_name": contract_name.strip(),
                "class_name": contract_name.strip(),
                "ticker": ticker.upper() if ticker and ticker.upper() not in INVALID_TICKERS else "",
                "series_id": "",
                "series_name": "",
                "class_id": "",
                "vehicle": UNKNOWN_VEHICLE,
                "identity_scope": "name",
            }
        )
    generic_text_matches = re.finditer(
        r'Series\s+S\d+\s+(?:new|existing|active|inactive)?\s*'
        r'(?P<series_name>[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?)\s+'
        r'Class/Contract\s+C\d+\s+'
        r'(?P<contract_name>[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?)'
        r'(?=\s+(?:Status\s+Name\s+Ticker\s+Symbol|Mailing\s+Address|Business\s+Address|$))',
        cleaned_text,
        re.IGNORECASE,
    )
    seen_generic_entries = {
        (normalize_etf_name(entry["etf_name"]), entry.get("ticker", ""))
        for entry in entries
    }
    for match in generic_text_matches:
        name, ticker = _split_series_contract_name_and_ticker(match.group("contract_name"))
        if not name:
            name = _clean_series_entry_name(match.group("series_name"))
        if not name:
            continue

        row_key = (normalize_etf_name(name), ticker)
        if row_key in seen_generic_entries:
            continue
        seen_generic_entries.add(row_key)
        entries.append(
            {
                "etf_name": name,
                "class_name": name,
                "ticker": ticker if ticker and ticker.upper() not in INVALID_TICKERS else "",
                "series_id": "",
                "series_name": "",
                "class_id": "",
                "vehicle": UNKNOWN_VEHICLE,
                "identity_scope": "name",
            }
        )
    return entries


def extract_named_ticker_pairs(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    cleaned_text = clean_html_text(text)
    pairs: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    def add_pair(name: str, ticker: str) -> None:
        clean_name = clean_html_text(name)
        clean_ticker = sanitize_ticker(ticker)
        if clean_ticker == "Not Listed" or "ETF" not in clean_name.upper():
            return
        key = (normalize_etf_name(clean_name), clean_ticker)
        if key in seen_keys:
            return
        seen_keys.add(key)
        pairs.append({"etf_name": clean_name, "ticker": clean_ticker})

    soup = BeautifulSoup(text, "html.parser")
    exchange_words = r"(?:NYSE|NASDAQ|CBOE|Cboe|ARCA|Arca|BZX|Exchange|Stock\s+Exchange)"

    for row in soup.find_all("tr"):
        cells = [clean_html_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        cells = [cell for cell in cells if cell]
        if not cells or any("ticker symbol" in cell.lower() for cell in cells):
            continue

        for index, cell in enumerate(cells):
            parenthetical_match = re.search(
                r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(?:ETF|Fund))\s*\(\s*([A-Z]{3,4})\s*\)',
                cell,
                re.IGNORECASE,
            )
            if parenthetical_match:
                add_pair(parenthetical_match.group(1), parenthetical_match.group(2))

            if "ETF" not in cell.upper() and "FUND" not in cell.upper():
                continue
            if index + 1 >= len(cells):
                continue
            ticker = sanitize_ticker(cells[index + 1])
            if ticker == "Not Listed":
                continue
            add_pair(cell, ticker)

    for match in re.finditer(
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(?:ETF|Fund))\s*\(\s*([A-Z]{3,4})\s*\)',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(1), match.group(2))

    for match in re.finditer(
        r'(?:Fund\s+Name\s+Ticker\s+Symbol\s+Exchange\s+)?'
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(?:ETF|Fund))\s+'
        r'([A-Z]{3,4})\s+'
        rf'{exchange_words}',
        cleaned_text,
        re.IGNORECASE,
    ):
        name = re.sub(
            r'^(?:Fund\s+Name\s+Ticker\s+Symbol\s+Exchange\s+)',
            "",
            match.group(1),
            flags=re.IGNORECASE,
        )
        add_pair(name, match.group(2))

    for match in re.finditer(
        r'\[\s*([A-Z]{3,4})\s*\]\s*\|\s*([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(2), match.group(1))

    for match in re.finditer(
        r'\b([A-Z]{3,4})\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,120}?(ETF|Fund))\s+'
        r'(ProShares\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,160}?(ETF|Fund))\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(4), match.group(1))

    for match in re.finditer(
        r'\b([A-Z]{3,4})\s+(ProShares\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,160}?(ETF|Fund))'
        r'(?=\s+[A-Z]{3,4}\s+ProShares|\s+Each Fund is listed on|\s+Each ETF is listed on|\s+is listed on\b)',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(2), match.group(1))

    for match in re.finditer(
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s*\|\s*([A-Z]{3,4})\s*\|\s*(?:NYSE|NASDAQ|CBOE|BZX|ARCA|STOCK\s+EXCHANGE)',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(1), match.group(3))

    for match in re.finditer(
        r'Series\s+S\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+'
        r'Class/Contract\s+C\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+([A-Z]{3,4})',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(3), match.group(5))

    line_text = BeautifulSoup(text, "html.parser").get_text("\n")
    for raw_line in line_text.splitlines():
        line = clean_html_text(raw_line)
        line_match = re.fullmatch(
            r'([A-Z]{3,4})\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,140}?(ETF|Fund))',
            line,
            re.IGNORECASE,
        )
        if line_match:
            add_pair(line_match.group(2), line_match.group(1))

        parenthetical_match = re.fullmatch(
            r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,140}?(ETF|Fund))\s*\(\s*([A-Z]{3,4})\s*\)',
            line,
            re.IGNORECASE,
        )
        if parenthetical_match:
            add_pair(parenthetical_match.group(1), parenthetical_match.group(3))

    return pairs


def build_sec_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.sec.gov{path_or_url}"


def extract_supporting_document_urls(index_text: str) -> list[str]:
    if not index_text:
        return []

    soup = BeautifulSoup(index_text, "html.parser")
    prioritized_paths = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if "/Archives/edgar/data/" not in href:
            continue
        filename = href.rsplit("/", 1)[-1].lower()
        if filename in {"index.htm", "index.html"}:
            continue
        if href.lower().startswith("/ix?doc="):
            href = href.split("/ix?doc=", 1)[-1]
        if href not in prioritized_paths:
            prioritized_paths.append(href)

    if prioritized_paths:
        return [build_sec_url(path) for path in prioritized_paths]

    ix_primary_matches = re.findall(
        r'href="/ix\?doc=(/Archives/edgar/data/[^"]+\.(?:htm|html))"',
        index_text,
        re.IGNORECASE,
    )
    direct_primary_matches = re.findall(
        r'<tr[^>]*>\s*<td[^>]*>\s*1\s*</td>.*?href="(/Archives/edgar/data/[^"]+\.(?:htm|html))"',
        index_text,
        re.IGNORECASE | re.DOTALL,
    )
    xml_matches = re.findall(
        r'href="(/Archives/edgar/data/[^"]+_htm\.xml)"',
        index_text,
        re.IGNORECASE,
    )
    txt_matches = re.findall(
        r'href="(/Archives/edgar/data/[^"]+\.txt)"',
        index_text,
        re.IGNORECASE,
    )
    direct_html_matches = re.findall(
        r'href="(/Archives/edgar/data/[^"]+\.(?:htm|html))"',
        index_text,
        re.IGNORECASE,
    )

    for group in [ix_primary_matches, direct_primary_matches, xml_matches, txt_matches, direct_html_matches]:
        for path in group:
            filename = path.rsplit("/", 1)[-1].lower()
            if filename in {"index.htm", "index.html"}:
                continue
            if path not in prioritized_paths:
                prioritized_paths.append(path)

    return [build_sec_url(path) for path in prioritized_paths]
