import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

HEADERS = {
    "User-Agent": "ETF Dashboard (jhaley1212@gmail.com)"
}

CIK_ENTRIES = [
    ("0001761055", "BlackRock ETF Trust"),
    ("0001804196", "BlackRock ETF Trust II"),
    ("0001100663", "iShares Trust"),
    ("0000920905", "iShares, Inc."),
    ("0001414509", "iShares U.S. ETF Trust"),
    ("0001337567", "iShares Gold Trust"),
    ("0000932472", "Vanguard Index Funds"),
    ("0000932473", "Vanguard Bond Index Funds"),
    ("0000932474", "Vanguard International Equity Index Funds"),
    ("0000932476", "Vanguard Fixed Income Securities Funds"),
    ("0000882184", "Vanguard Whitehall Funds"),
    ("0000932478", "Vanguard World Funds"),
    ("0000932477", "SPDR Series Trust"),
    ("0001064642", "SPDR Index Shares Funds"),
    ("0001350487", "SPDR S&P 500 ETF Trust"),
    ("0001364742", "SPDR MSCI World StrategicFactors ETF Trust"),
    ("0001400683", "SPDR ICE Preferred Securities ETF Trust"),
    ("0001454967", "SPDR DoubleLine Total Return Tactical ETF"),
    ("0001683863", "SPDR SSGA Active ETF Trust"),
    ("0000920903", "Invesco Exchange-Traded Fund Trust"),
    ("0001333493", "Invesco Actively Managed Exchange-Traded Fund Trust"),
    ("0001592900", "Invesco Capital Management LLC"),
    ("0001424958", "Invesco PowerShares Capital Management LLC"),
    ("0001452937", "Invesco DB Multi-Sector Commodity Trust"),
    ("0001452938", "Invesco DB Commodity Index Tracking Fund"),
    ("0001064641", "PowerShares Exchange-Traded Fund Trust"),
    ("0000862557", "PowerShares Capital Management LLC"),
    ("0001454889", "Schwab Strategic Trust"),
    ("0001454888", "Schwab Capital Trust"),
    ("0001109241", "JPMorgan Trust I"),
    ("0000926343", "JPMorgan Trust II"),
    ("0001587982", "JPMorgan Exchange-Traded Fund Trust"),
    ("0000351430", "Dimensional Investment Group Inc."),
    ("0000317845", "Dimensional Investment Trust"),
    ("0000925961", "Dimensional Fund Advisors LP"),
    ("0001582982", "Dimensional ETF Trust"),
    ("0001090372", "First Trust Exchange-Traded Fund"),
    ("0001090373", "First Trust Exchange-Traded Fund II"),
    ("0001090374", "First Trust Exchange-Traded Fund III"),
    ("0001279890", "First Trust Exchange-Traded AlphaDEX Fund"),
    ("0001320414", "First Trust Exchange-Traded Fund IV"),
    ("0001137360", "VanEck ETF Trust"),
    ("0000863064", "VanEck Vectors ETF Trust"),
    ("0001015965", "VanEck VIP Trust"),
    ("0001137361", "VanEck Funds Trust"),
    ("0000748653", "VanEck Merk Gold Trust"),
    ("0000315066", "Fidelity Covington Trust"),
    ("0000036405", "Fidelity Salem Street Trust"),
    ("0000350966", "Fidelity Securities Fund"),
    ("0000819118", "Fidelity Advisor Series I"),
    ("0000819119", "Fidelity Advisor Series II"),
    ("0001582982", "Fidelity Exchange-Traded Fund Trust"),
    ("0000051931", "American Funds Insurance Series"),
    ("0000316077", "American Funds Investment Company of America"),
    ("0000316054", "American Funds Washington Mutual Investors Fund"),
    ("0000316053", "American Funds Growth Fund of America"),
    ("0001582983", "Capital Group Exchange-Traded Fund Trust"),
    ("0001471855", "American Century ETF Trust"),
    ("0000354908", "American Century Investment Trust"),
    ("0000804239", "American Century Mutual Funds, Inc."),
    ("0000914862", "American Century Quantitative Equity Funds"),
    ("0000914863", "American Century Strategic Asset Allocations, Inc."),
    ("0001174610", "ProShares Trust"),
    ("0001318342", "ProShares Trust II"),
    ("0001308648", "ProShares Trust III"),
    ("0001103453", "ProFunds"),
    ("0000899140", "ProFunds Trust"),
    ("0001350487", "WisdomTree Trust"),
    ("0001378992", "WisdomTree Trust II"),
    ("0001414508", "WisdomTree Trust III"),
    ("0001633061", "WisdomTree Continuous Commodity Index Fund"),
    ("0001432353", "Global X Funds"),
    ("0001432354", "Global X Funds II"),
    ("0000886982", "Goldman Sachs ETF Trust"),
    ("0001582981", "Goldman Sachs ActiveBeta ETF Trust"),
    ("0001424958", "Direxion Shares ETF Trust"),
    ("0001318343", "Direxion Shares ETF Trust II"),
    ("0001308649", "Direxion Shares ETF Trust III"),
    ("0001174610", "PIMCO ETF Trust"),
    ("0000926128", "PIMCO Funds: Global Investors Series plc"),
    ("0000819116", "PIMCO Equity Series"),
    ("0000036405", "Franklin Templeton ETF Trust"),
    ("0000354960", "Franklin Templeton Investment Funds"),
    ("0000038777", "Franklin Custodian Funds"),
    ("0000036406", "Franklin Strategic Series"),
    ("0000036407", "Franklin Income Securities Trust"),
    ("0001582984", "Janus Henderson ETF Trust"),
    ("0000319376", "Janus Aspen Series"),
    ("0000712973", "Janus Investment Fund"),
    ("0001084613", "Janus Henderson Capital Funds plc"),
    ("0001620069", "Pacer Funds Trust"),
    ("0001685581", "Pacer Funds Trust II"),
    ("0001683862", "Innovator ETFs Trust"),
    ("0001587982", "DBX ETF Trust"),
    ("0001587983", "PGIM ETF Trust"),
    ("0000723058", "Northern Lights Fund Trust"),
    ("0001137360", "abrdn ETF Trust"),
    ("0000315067", "T. Rowe Price Exchange-Traded Funds"),
    ("0001881741", "NEOS ETF Trust"),
    ("0001587984", "VictoryShares ETF Trust"),
    ("0001283333", "ALPS ETF Trust"),
    ("0001587985", "Amplify ETF Trust"),
    ("0001725210", "Grayscale Investments LLC"),
    ("0001110805", "Nuveen ETF Trust"),
    ("0000915802", "BNY Mellon ETF Trust"),
    ("0001579982", "ARK ETF Trust"),
    ("0001644419", "Alpha Architect ETF Trust"),
    ("0001644418", "Simplify ETF Trust"),
    ("0001350488", "John Hancock Exchange-Traded Fund Trust"),
    ("0001350489", "Eaton Vance ETF Trust"),
    ("0001615774", "GraniteShares ETF Trust"),
    ("0001540305", "KraneShares Trust"),
    ("0001566219", "BMO ETF Trust"),
    ("0001587987", "Columbia ETF Trust"),
    ("0001587988", "Principal Exchange-Traded Funds"),
    ("0001924868", "YieldMax ETF Trust"),
    ("0001934941", "F/m ETF Trust"),
    ("0001771146", "Roundhill ETF Trust"),
    ("0001771147", "Defiance ETF Trust"),
    ("0001877260", "BondBloxx ETF Trust"),
]

CIK_LOOKUP = {}
for cik, name in CIK_ENTRIES:
    if cik not in CIK_LOOKUP:
        CIK_LOOKUP[cik] = name

CIKS = list(CIK_LOOKUP.keys())
FORMS = ["S-1", "N-1A", "485BPOS", "485APOS"]
DAYS_BACK = 60
REQUEST_DELAY_SECONDS = 0.35
INDEX_PAGE_MAX_CHARS = 60000
DATA_VERSION = "2026-03-30-ticker-sanitize-and-filing-briefs"
INVALID_TICKERS = {"CIK", "ETF", "FUND"}
NEWS_QUERIES = ('"recent ETF filings"', "ETF filings", "new ETF launches")
COMMON_MATCH_WORDS = {
    "etf",
    "fund",
    "trust",
    "daily",
    "long",
    "short",
    "ultra",
    "capital",
    "shares",
    "index",
    "income",
    "growth",
    "target",
}


@st.cache_resource
def get_http_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_response_text(url, max_chars, retries=3):
    session = get_http_session()
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            return response.text[:max_chars]
        except requests.RequestException:
            if attempt == retries - 1:
                return ""
            time.sleep(1.0 + attempt)


def extract_text(url, max_chars=INDEX_PAGE_MAX_CHARS):
    return get_response_text(url, max_chars)


def build_google_news_rss_url(query):
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def split_news_title_and_source(title, fallback_source):
    title = title.strip()

    dash_split = re.split(r"\s+[—–-]\s+", title)
    if len(dash_split) >= 2:
        possible_source = dash_split[-1].strip()
        if 2 <= len(possible_source) <= 60:
            return " - ".join(dash_split[:-1]).strip(), possible_source

    return title, fallback_source


def clean_news_headline_and_source(title, fallback_source):
    title = (title or "").strip()
    dash_split = re.split(r"\s+[—–-]\s+", title)
    if len(dash_split) >= 2:
        possible_source = dash_split[-1].strip()
        if 2 <= len(possible_source) <= 60:
            return " - ".join(dash_split[:-1]).strip(), possible_source
    return title, fallback_source


def fetch_news_items(queries=None):
    items = []
    seen_links = set()

    for query in (queries or NEWS_QUERIES):
        feed_url = build_google_news_rss_url(query)
        feed_text = get_response_text(feed_url, max_chars=120000, retries=2)
        if not feed_text:
            continue

        try:
            root = ET.fromstring(feed_text)
        except ET.ParseError:
            continue

        for entry in root.findall(".//item"):
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            pub_date = (entry.findtext("pubDate") or "").strip()
            source_text = (entry.findtext("source") or "").strip()

            if not title or not link or link in seen_links:
                continue

            seen_links.add(link)
            source = source_text or "News"
            title, source = clean_news_headline_and_source(title, source)

            items.append(
                {
                    "source": source.strip(),
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                }
            )

    return items


def extract_etf_name(text):
    bracketed_pipe_match = re.search(
        r'\[\s*[A-Z]{1,8}\s*\]\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        clean_html_text(text),
        re.IGNORECASE,
    )
    if bracketed_pipe_match:
        return bracketed_pipe_match.group(1).strip()

    pipe_match = re.search(
        r'([A-Z]{2,6})\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        clean_html_text(text),
        re.IGNORECASE,
    )
    if pipe_match:
        return pipe_match.group(2).strip()

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
        r'<td[^>]*>(.*?)</td>\s*<td[^>]*>.*?</td>\s*</tr>',
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

    fallback_text = clean_html_text(text)
    fallback = re.search(r'([A-Z][A-Za-z0-9&\s\-]{5,100}(ETF|Fund))', fallback_text)
    return fallback.group(1).strip() if fallback else "N/A"


def extract_ticker(text):
    bracketed_pipe_match = re.search(
        r'\[\s*([A-Z]{1,8})\s*\]\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        clean_html_text(text),
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

    cleaned_text = clean_html_text(text)

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

    return ""


def sanitize_ticker(value):
    ticker = str(value or "").strip().upper()
    if re.fullmatch(r"[A-Z]{1,8}", ticker) and ticker not in INVALID_TICKERS:
        return ticker
    return "Not Listed"


def extract_filer_name(text):
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


def extract_series_entries(text):
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
    return entries


def clean_html_text(value):
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    decoded = re.sub(r"[\u2000-\u200f\u2028-\u202f\u205f\u2060\ufeff]", " ", decoded)
    return " ".join(decoded.split())


def normalize_match_text(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def extract_match_terms(value):
    return {
        word
        for word in normalize_match_text(value).split()
        if len(word) >= 4 and word not in COMMON_MATCH_WORDS
    }


def match_news_to_etfs(news_title, filings_df, limit=3):
    news_text = normalize_match_text(news_title)
    matches = []

    for _, row in filings_df.iterrows():
        etf_name = str(row.get("etf_name", "")).strip()
        ticker = str(row.get("ticker", "")).strip().upper()
        if not etf_name:
            continue

        score = 0
        if ticker and ticker not in {"", "Not Listed"} and re.search(rf"\b{re.escape(ticker.lower())}\b", news_text):
            score += 3

        terms = extract_match_terms(etf_name)
        overlap = sum(1 for term in terms if re.search(rf"\b{re.escape(term)}\b", news_text))
        if overlap >= 2:
            score += overlap

        if score > 0:
            label = ticker if ticker and ticker != "Not Listed" else etf_name
            matches.append((score, label))

    matches.sort(key=lambda item: (-item[0], item[1]))
    unique = []
    seen = set()
    for _, label in matches:
        if label not in seen:
            seen.add(label)
            unique.append(label)
        if len(unique) >= limit:
            break

    return ", ".join(unique) if unique else ""


def build_filing_blurbs(filings_df, limit=12):
    if filings_df.empty:
        return []

    blurbs = []
    recent_rows = filings_df.sort_values(by="date", ascending=False).head(limit)
    for _, row in recent_rows.iterrows():
        etf_name = str(row.get("etf_name", "")).strip() or "ETF Filing"
        filer = str(row.get("filer", "")).strip()
        form = str(row.get("form", "")).strip()
        link = str(row.get("link", "")).strip()
        ticker = sanitize_ticker(row.get("ticker", ""))
        date_value = row.get("date")
        date_label = date_value.strftime("%Y-%m-%d") if hasattr(date_value, "strftime") else str(date_value)

        blurbs.append(
            {
                "headline": etf_name,
                "source": "Recent ETF Filings",
                "matching_tickers": ticker,
                "link": link,
                "blurb": f"{form} filed on {date_label} by {filer}.",
            }
        )

    return blurbs


def format_news_date(pub_date):
    pub_date = str(pub_date or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(pub_date, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return pub_date


def build_sec_url(path_or_url):
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.sec.gov{path_or_url}"


def extract_supporting_document_urls(index_text):
    prioritized_paths = []

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


def fetch_supporting_document_texts(index_text, max_documents=4):
    documents = []
    for url in extract_supporting_document_urls(index_text)[:max_documents]:
        max_chars = 300000
        if url.lower().endswith("_htm.xml"):
            max_chars = 120000

        text = extract_text(url, max_chars=max_chars)
        if text:
            documents.append(text)

    return documents


def fetch_recent_filings_for_cik(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    session = get_http_session()
    for attempt in range(3):
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            data = response.json()
            return {
                "filer_name": data.get("name", CIK_LOOKUP.get(cik, cik)),
                "recent": data.get("filings", {}).get("recent", {}),
            }
        except requests.RequestException:
            if attempt == 2:
                return {
                    "filer_name": CIK_LOOKUP.get(cik, cik),
                    "recent": {},
                }
            time.sleep(1.0 + attempt)


def fetch_filings(start_date=None, end_date=None):
    results = []
    seen_links = set()
    start_bound = datetime.combine(start_date, datetime.min.time()) if start_date else datetime.today() - timedelta(days=DAYS_BACK)
    end_bound = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.today()

    for cik in CIKS:
        cik_data = fetch_recent_filings_for_cik(cik)
        filer_name = str(cik_data.get("filer_name", CIK_LOOKUP.get(cik, cik))).upper()
        recent = cik_data.get("recent", {})
        if not recent:
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])

        for index, form in enumerate(forms):
            if form not in FORMS:
                continue

            if index >= len(filing_dates) or index >= len(accession_numbers):
                continue

            date_str = filing_dates[index]
            date = datetime.strptime(date_str, "%Y-%m-%d")
            if date < start_bound or date > end_bound:
                continue

            accession_number = accession_numbers[index]
            accession_clean = accession_number.replace("-", "")
            filing_link = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_clean}/{accession_number}-index.htm"
            )
            primary_document = primary_documents[index] if index < len(primary_documents) else ""
            primary_document_url = ""
            if primary_document:
                primary_document_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accession_clean}/{primary_document}"
                )

            if filing_link in seen_links:
                continue

            seen_links.add(filing_link)
            index_text = extract_text(filing_link, max_chars=INDEX_PAGE_MAX_CHARS)
            filing_filer_name = extract_filer_name(index_text) or filer_name
            series_entries = extract_series_entries(index_text)
            primary_ticker = ""
            primary_etf_name = "N/A"

            if primary_document_url:
                primary_text = extract_text(primary_document_url, max_chars=300000)
                if primary_text:
                    primary_ticker = extract_ticker(primary_text)
                    primary_etf_name = extract_etf_name(primary_text)
                    parsed_filer_name = extract_filer_name(primary_text)
                    if parsed_filer_name:
                        filing_filer_name = parsed_filer_name

            if index_text and ((not series_entries) or any(not entry["ticker"] for entry in series_entries)):
                for supporting_text in fetch_supporting_document_texts(index_text):
                    if not primary_ticker:
                        primary_ticker = extract_ticker(supporting_text)
                    if primary_etf_name == "N/A":
                        primary_etf_name = extract_etf_name(supporting_text)
                    if not filing_filer_name:
                        filing_filer_name = extract_filer_name(supporting_text)
                    if primary_ticker and primary_etf_name != "N/A" and filing_filer_name:
                        break

            resolved_filer_name = filing_filer_name or filer_name
            rows_to_append = []

            if series_entries:
                for entry in series_entries:
                    row_name = entry["etf_name"] or primary_etf_name
                    row_ticker = entry["ticker"]
                    if len(series_entries) == 1 and not row_ticker:
                        row_ticker = primary_ticker
                    rows_to_append.append(
                        {
                            "ticker": sanitize_ticker(row_ticker),
                            "etf_name": row_name,
                            "filer": resolved_filer_name,
                            "form": form,
                            "date": date_str,
                            "link": filing_link,
                        }
                    )
            else:
                fallback_name = primary_etf_name if primary_etf_name != "N/A" else extract_etf_name(index_text)
                fallback_ticker = primary_ticker or extract_ticker(index_text) or "Not Listed"
                rows_to_append.append(
                    {
                        "ticker": sanitize_ticker(fallback_ticker),
                        "etf_name": fallback_name,
                        "filer": resolved_filer_name,
                        "form": form,
                        "date": date_str,
                        "link": filing_link,
                    }
                )

            for row in rows_to_append:
                if "ETF" not in str(row["etf_name"]).upper():
                    continue
                results.append(row)

            time.sleep(REQUEST_DELAY_SECONDS)

        time.sleep(REQUEST_DELAY_SECONDS)

    return results

st.set_page_config(page_title="ETF Dash", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=PT+Sans+Narrow:wght@400;700&display=swap');

    :root {
        --etf-accent: #138a36;
        --etf-card: #121722;
        --etf-border: rgba(255, 255, 255, 0.08);
        --etf-muted: #aeb7c7;
        --etf-text: #f3f6fb;
        --etf-soft: #0f131b;
    }

    html, body, [class*="css"], [data-testid="stAppViewContainer"], [data-testid="stMarkdownContainer"],
    [data-testid="stDataFrame"], [data-testid="stForm"], [data-testid="stDateInputField"] input,
    button, table, thead, tbody, tr, th, td, input {
        font-family: 'PT Sans Narrow', sans-serif !important;
        color: var(--etf-text);
    }

    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
        background: #0f131b !important;
    }

    .block-container {
        padding-top: 3.1rem;
        max-width: 1400px;
    }

    .etf-brand {
        font-size: 2.05rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        margin-bottom: 0.15rem;
        color: var(--etf-accent);
    }

    .etf-tagline {
        color: var(--etf-muted);
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }

    .etf-card {
        border: 1px solid var(--etf-border);
        background: var(--etf-card);
        border-radius: 18px;
        padding: 1rem 1.1rem;
        margin-bottom: 1rem;
    }

    .etf-card-label {
        color: var(--etf-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
        margin-bottom: 0.35rem;
    }

    .etf-card-value {
        font-size: 1.65rem;
        font-weight: 700;
    }

    .etf-section-title {
        font-size: 1.35rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
        color: var(--etf-text);
    }

    .etf-section-copy {
        color: var(--etf-muted);
        margin-bottom: 0.8rem;
    }

    .etf-feature-title {
        font-size: 1.3rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .etf-feature-meta {
        color: var(--etf-muted);
        font-size: 0.95rem;
    }

    .etf-news-item {
        padding: 0.95rem 0;
        border-bottom: 1px solid var(--etf-border);
    }

    .etf-news-item:last-child {
        border-bottom: none;
        padding-bottom: 0;
    }

    .etf-news-source {
        color: var(--etf-accent);
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .etf-news-meta {
        color: var(--etf-muted);
        font-size: 0.9rem;
    }

    .etf-news-title {
        display: block;
        font-size: 1.02rem;
        font-weight: 700;
        line-height: 1.35;
        margin: 0.3rem 0 0.2rem;
        text-decoration: none;
    }

    .etf-news-title:hover {
        text-decoration: underline;
    }

    .etf-news-kicker {
        color: var(--etf-muted);
        font-size: 0.88rem;
        margin-top: 0.15rem;
    }

    .etf-news-rail {
        max-height: 1450px;
        overflow-y: auto;
        padding-right: 0.5rem;
    }

    a, a:visited {
        color: #1357c5;
    }

    [data-testid="stDateInputField"] input, div[data-baseweb="input"] input {
        background: #1d2330 !important;
        color: var(--etf-text) !important;
    }

    div[data-baseweb="base-input"] {
        background: #1d2330 !important;
        border: 1px solid var(--etf-border) !important;
    }

    div[data-testid="stForm"] {
        border: 1px solid var(--etf-border);
        border-radius: 16px;
        padding: 0.8rem 0.9rem 0.2rem;
        background: var(--etf-card);
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--etf-border);
        border-radius: 16px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=1800)
def load_filings(_data_version, start_date, end_date):
    return fetch_filings(start_date, end_date)


@st.cache_data(ttl=1800)
def load_news(_query):
    return fetch_news_items(_query)


def build_news_fallback_from_filings(filings_df, limit=6):
    fallback_items = []
    if filings_df.empty:
        return fallback_items

    for _, row in filings_df.sort_values(by="date", ascending=False).head(limit).iterrows():
        fallback_items.append(
            {
                "source": "ETF Dash",
                "title": str(row.get("etf_name", "")).strip() or "ETF Filing",
                "link": str(row.get("link", "")).strip(),
                "pub_date": str(row.get("date", "")),
                "summary": f"{row.get('form', '')} filed by {row.get('filer', '')}",
            }
        )

    return fallback_items


default_end = datetime.today().date()
year_start = datetime(default_end.year, 1, 1).date()
default_start = max(year_start, default_end - timedelta(days=14))
if "search_start_date" not in st.session_state:
    st.session_state.search_start_date = default_start
if "search_end_date" not in st.session_state:
    st.session_state.search_end_date = default_end
if "search_requested" not in st.session_state:
    st.session_state.search_requested = False

st.markdown(
    """
    <div class="etf-brand">ETF Dash</div>
    <div class="etf-tagline">Tracking new ETF launches, registration filings, and the surrounding market conversation.</div>
    """,
    unsafe_allow_html=True,
)

search_submitted = False
with st.container():
    left_col, right_col = st.columns([2.25, 1], gap="large")

    with left_col:
        st.markdown('<div class="etf-section-title">ETF Filings</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Search SEC filings by date range, with the newest filings displayed first.</div>',
            unsafe_allow_html=True,
        )
        with st.form("date_filter_form"):
            filter_cols = st.columns([1, 1, 0.45])
            filter_cols[0].date_input("Start date", min_value=year_start, max_value=default_end, key="search_start_date")
            filter_cols[1].date_input("End date", min_value=year_start, max_value=default_end, key="search_end_date")
            search_submitted = filter_cols[2].form_submit_button("Search")

    with right_col:
        st.markdown('<div class="etf-section-title">ETF News</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Recent Google headlines around ETF filings and launches.</div>',
            unsafe_allow_html=True,
        )
        news_items = load_news(NEWS_QUERIES)
        if news_items:
            news_container = st.container(height=1450)
            for item in news_items[:40]:
                news_date = format_news_date(item.get("pub_date", ""))
                news_container.markdown(
                    f"""
                    <div class="etf-news-item">
                        <div class="etf-news-source">{item.get("source", "News")}</div>
                        <a class="etf-news-title" href="{item.get("link", "#")}" target="_blank">{item.get("title", "Headline")}</a>
                        <div class="etf-news-meta">{news_date}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        elif st.session_state.search_requested:
            fallback_items = build_news_fallback_from_filings(
                pd.DataFrame(load_filings(DATA_VERSION, st.session_state.search_start_date, st.session_state.search_end_date))
            )
            news_container = st.container(height=1450)
            for item in fallback_items:
                news_container.markdown(
                    f"""
                    <div class="etf-news-item">
                        <div class="etf-news-source">{item.get("source", "ETF Dash")}</div>
                        <a class="etf-news-title" href="{item.get("link", "#")}" target="_blank">{item.get("title", "Headline")}</a>
                        <div class="etf-news-kicker">{item.get("summary", "")}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("News headlines will appear here once Google returns results or after you run a filing search.")

if search_submitted:
    if st.session_state.search_start_date < year_start:
        st.session_state.search_start_date = year_start
    if st.session_state.search_end_date < year_start:
        st.session_state.search_end_date = year_start
    st.session_state.search_requested = True

if not st.session_state.search_requested:
    st.info("Choose a date range and click Search to run the SEC scrape.")
elif st.session_state.search_start_date > st.session_state.search_end_date:
    st.warning("Start date must be on or before end date.")
else:
    try:
        with st.spinner("Searching SEC filings for the selected date range..."):
            data = load_filings(DATA_VERSION, st.session_state.search_start_date, st.session_state.search_end_date)
    except Exception as exc:
        st.error(
            "The app could not load fresh SEC filing data right now. "
            "Please try again in a minute."
        )
        st.caption(f"Temporary data source issue: {type(exc).__name__}")
    else:
        df = pd.DataFrame(data)
        if not df.empty:
            for column in ["ticker", "etf_name", "filer", "form", "date", "link"]:
                if column not in df.columns:
                    df[column] = ""

            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).sort_values(by="date", ascending=False)
            filtered_df = df[
                (df["date"].dt.date >= st.session_state.search_start_date)
                & (df["date"].dt.date <= st.session_state.search_end_date)
            ].copy()
            filtered_df = filtered_df.sort_values(by="date", ascending=False)
            filtered_df["ticker"] = filtered_df["ticker"].apply(sanitize_ticker)
            display_df = filtered_df.copy()
            display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
            filings_count = len(display_df)
            listed_tickers = int((filtered_df["ticker"] != "Not Listed").sum())
            distinct_filers = int(filtered_df["filer"].nunique())
            latest_date = display_df.iloc[0]["date"] if not display_df.empty else "N/A"
            stat_cols = st.columns(4)
            stat_cols[0].markdown(
                f'<div class="etf-card"><div class="etf-card-label">Filings Loaded</div><div class="etf-card-value">{filings_count}</div></div>',
                unsafe_allow_html=True,
            )
            stat_cols[1].markdown(
                f'<div class="etf-card"><div class="etf-card-label">Tickers Listed</div><div class="etf-card-value">{listed_tickers}</div></div>',
                unsafe_allow_html=True,
            )
            stat_cols[2].markdown(
                f'<div class="etf-card"><div class="etf-card-label">Distinct Filers</div><div class="etf-card-value">{distinct_filers}</div></div>',
                unsafe_allow_html=True,
            )
            stat_cols[3].markdown(
                f'<div class="etf-card"><div class="etf-card-label">Latest Filing</div><div class="etf-card-value">{latest_date}</div></div>',
                unsafe_allow_html=True,
            )

            featured = display_df.iloc[0].to_dict()
            st.markdown(
                f"""
                <div class="etf-card">
                    <div class="etf-card-label">Featured Filing</div>
                    <div class="etf-feature-title">{featured.get("etf_name", "ETF Filing")}</div>
                    <div class="etf-feature-meta">{featured.get("form", "")} | {featured.get("date", "")} | {featured.get("filer", "")}</div>
                    <div style="margin-top:0.65rem;"><a href="{featured.get('link', '#')}" target="_blank">Open SEC Filing</a></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.success(f"Loaded {filings_count} filing(s) in the selected date range.")
            st.dataframe(
                display_df[["ticker", "etf_name", "filer", "form", "date", "link"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("No recent filings were loaded right now. The SEC may be rate-limiting some requests, so please try again shortly.")
