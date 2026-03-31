from datetime import datetime
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from config import COMMON_MATCH_WORDS, NEWS_QUERIES, TRUSTED_NEWS_SOURCES
from http_utils import get_response_text
from sec_parsers import sanitize_ticker


def build_google_news_rss_url(query):
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def split_news_title_and_source(title, fallback_source):
    title = title.strip()

    dash_split = re.split(r"\s+[â€”â€“-]\s+", title)
    if len(dash_split) >= 2:
        possible_source = dash_split[-1].strip()
        if 2 <= len(possible_source) <= 60:
            return " - ".join(dash_split[:-1]).strip(), possible_source

    return title, fallback_source


def clean_news_headline_and_source(title, fallback_source):
    title = (title or "").strip()
    dash_split = re.split(r"\s+[â€”â€“-]\s+", title)
    if len(dash_split) >= 2:
        possible_source = dash_split[-1].strip()
        if 2 <= len(possible_source) <= 60:
            return " - ".join(dash_split[:-1]).strip(), possible_source
    return title, fallback_source


def parse_news_datetime(pub_date):
    pub_date = str(pub_date or "").strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(pub_date, fmt)
        except ValueError:
            continue
    return None


def normalize_news_source(source, link=""):
    source_text = f"{source} {link}".lower()
    for needle, label in TRUSTED_NEWS_SOURCES.items():
        if needle in source_text:
            return label
    return ""


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

            normalized_source = normalize_news_source(source_text, link)
            if not normalized_source:
                continue

            seen_links.add(link)
            source = normalized_source
            title, source = clean_news_headline_and_source(title, source)
            published_at = parse_news_datetime(pub_date)

            items.append(
                {
                    "source": source.strip(),
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "published_at": published_at,
                }
            )

    items.sort(
        key=lambda item: (
            item.get("published_at") is None,
            -(item["published_at"].timestamp()) if item.get("published_at") else 0,
        )
    )
    return items


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
