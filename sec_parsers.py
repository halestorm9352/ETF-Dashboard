import html
import re
from typing import Any

from bs4 import BeautifulSoup

from config import INVALID_TICKERS


def clean_html_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    decoded = re.sub(r"[\u2000-\u200f\u2028-\u202f\u205f\u2060\ufeff]", " ", decoded)
    return " ".join(decoded.split())


def normalize_etf_name(value: str) -> str:
    cleaned = clean_html_text(value).upper()
    cleaned = re.sub(r"[^A-Z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


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


def extract_ticker(text: str) -> str:
    cleaned_text = clean_html_text(text)

    bracketed_pipe_match = re.search(
        r'\[\s*([A-Z]{1,8})\s*\]\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
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
            if re.fullmatch(r"[A-Z]{1,8}", ticker_candidate) and ticker_candidate not in INVALID_TICKERS:
                return ticker_candidate

    name_ticker_pipe_match = re.search(
        r'[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund)\s*\|\s*([A-Z]{1,8})\s*\|',
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
            r'Ticker Symbol\s*:?\s*([A-Z]{2,8})\b',
            ticker_snippet,
            re.IGNORECASE,
        )
        if ticker_label_match:
            ticker = ticker_label_match.group(1).upper()
            if ticker not in INVALID_TICKERS:
                return ticker

    prospectus_table_match = re.search(
        r'Fund\s+Ticker\s+Principal U\.S\. Listing Exchange.*?(?:ETF|Fund)\s+([A-Z]{1,8})\b',
        cleaned_text,
        re.IGNORECASE,
    )
    if prospectus_table_match:
        ticker = prospectus_table_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    pipe_match = re.search(
        r'([A-Z]{2,6})\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if pipe_match:
        ticker = pipe_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    ticker_cell_match = re.search(
        r'Ticker Symbol\s+([A-Z]{1,8})',
        cleaned_text,
        re.IGNORECASE,
    )
    if ticker_cell_match:
        ticker = ticker_cell_match.group(1).upper()
        if ticker not in INVALID_TICKERS:
            return ticker

    series_ticker_match = re.search(
        r'Class/Contract\s+C\d+\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund)\s+([A-Z]{1,8})(?=\s+(?:Status\s+Name\s+Ticker\s+Symbol|Mailing\s+Address|Business\s+Address|$))',
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
    if re.fullmatch(r"[A-Z]{1,8}", ticker) and ticker not in INVALID_TICKERS:
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

    exact_name_match = re.search(
        r'([A-Za-z0-9&,\.\-\s]+)\s*\(Exact Name of Registrant as Specified in Charter\)',
        clean_html_text(text),
        re.IGNORECASE,
    )
    if exact_name_match:
        return " ".join(exact_name_match.group(1).split()).upper()

    return ""


def extract_series_entries(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    soup = BeautifulSoup(text, "html.parser")
    parsed_entries: list[dict[str, str]] = []
    for row in soup.select("tr.contractRow"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        name = clean_html_text(cells[2].get_text(" ", strip=True))
        ticker = clean_html_text(cells[3].get_text(" ", strip=True)).upper()
        if not name:
            continue
        if ticker and not re.fullmatch(r"[A-Z]{1,8}", ticker):
            ticker = ""
        parsed_entries.append(
            {
                "etf_name": name,
                "ticker": ticker if ticker not in INVALID_TICKERS else "",
            }
        )

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
        if ticker and not re.fullmatch(r"[A-Z]{1,8}", ticker):
            ticker = ""
        entries.append(
            {
                "etf_name": name,
                "ticker": ticker if ticker not in INVALID_TICKERS else "",
            }
        )

    if entries:
        return entries

    cleaned_text = clean_html_text(text)
    text_matches = re.findall(
        r'Series\s+S\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+'
        r'Class/Contract\s+C\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))'
        r'(?:\s+([A-Z]{1,8}))?(?=\s+(?:Status\s+Name\s+Ticker\s+Symbol|Mailing\s+Address|Business\s+Address|$))',
        cleaned_text,
        re.IGNORECASE,
    )
    for _series_name, _series_suffix, contract_name, _contract_suffix, ticker in text_matches:
        if not contract_name:
            continue
        entries.append(
            {
                "etf_name": contract_name.strip(),
                "ticker": ticker.upper() if ticker and ticker.upper() not in INVALID_TICKERS else "",
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

    for match in re.finditer(
        r'\[\s*([A-Z]{1,8})\s*\]\s*\|\s*([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(2), match.group(1))

    for match in re.finditer(
        r'\b([A-Z]{2,8})\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,120}?(ETF|Fund))\s+'
        r'(ProShares\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,160}?(ETF|Fund))\s+is\s+listed\s+on\b',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(4), match.group(1))

    for match in re.finditer(
        r'\b([A-Z]{2,8})\s+(ProShares\s+[A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,160}?(ETF|Fund))'
        r'(?=\s+[A-Z]{2,8}\s+ProShares|\s+Each Fund is listed on|\s+Each ETF is listed on|\s+is listed on\b)',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(2), match.group(1))

    for match in re.finditer(
        r'([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s*\|\s*([A-Z]{1,8})\s*\|\s*(?:NYSE|NASDAQ|CBOE|BZX|ARCA|STOCK\s+EXCHANGE)',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(1), match.group(3))

    for match in re.finditer(
        r'Series\s+S\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+'
        r'Class/Contract\s+C\d+\s+([A-Z][A-Za-z0-9&\-\.\(\)/,\s]{3,180}?(ETF|Fund))\s+([A-Z]{1,8})',
        cleaned_text,
        re.IGNORECASE,
    ):
        add_pair(match.group(3), match.group(5))

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
