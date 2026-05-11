from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timedelta
from html import unescape
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import re
import threading
import time
from typing import Callable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ETFCOM_BASE_URL = "https://www.etf.com"
ETFCOM_NEWS_DAYS_BACK = 90
ETFCOM_NEWS_MAX_PAGES = 40
ETFDB_BASE_URL = "https://etfdb.com"
ETFDB_NEWS_DAYS_BACK = 90
ETFDB_NEWS_MAX_PAGES = 30
ETFSTREAM_BASE_URL = "https://www.etfstream.com"
ETFSTREAM_NEWS_DAYS_BACK = 90
ETFSTREAM_NEWS_MAX_PAGES = 30
ETFEXPRESS_BASE_URL = "https://etfexpress.com"
ETFEXPRESS_NEWS_DAYS_BACK = 90
ETFEXPRESS_NEWS_MAX_PAGES = 30
TRACKINSIGHT_BASE_URL = "https://www.trackinsight.com"
TRACKINSIGHT_NEWS_DAYS_BACK = 90
TRACKINSIGHT_NEWS_MAX_PAGES = 20
BASE_DIR = Path(__file__).resolve().parent
SEED_LAUNCHES_PATH = BASE_DIR / "etfcom_launches_seed.csv"
SEED_LAUNCHES_STATUS_PATH = BASE_DIR / "etfcom_launches_status.json"
SEED_NEWS_PATH = BASE_DIR / "etfcom_news_seed.csv"
ETFCOM_REQUEST_TIMEOUT = 15
ETFCOM_CURL_TIMEOUT = 12
SOURCE_DEAD_TTL_SECONDS = 900
NEWS_SOURCE_MAX_WORKERS = 5
_THREAD_LOCAL = threading.local()
_DEAD_HOSTS: dict[str, float] = {}
_DEAD_HOSTS_LOCK = threading.Lock()
ETFCOM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _clean_text(value):
    return " ".join((value or "").split())


def _parse_date(value, fmt):
    try:
        return datetime.strptime(value.strip(), fmt)
    except ValueError:
        return None


def _load_seed_rows(path):
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _get_session():
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(ETFCOM_HEADERS)
        _THREAD_LOCAL.session = session
    return session


def _get_host(url):
    try:
        return urlparse(url).netloc.lower()
    except ValueError:
        return ""


def _is_host_temporarily_dead(url):
    host = _get_host(url)
    if not host:
        return False

    with _DEAD_HOSTS_LOCK:
        retry_after = _DEAD_HOSTS.get(host)
        if not retry_after:
            return False
        if retry_after <= time.time():
            _DEAD_HOSTS.pop(host, None)
            return False
        return True


def _mark_host_temporarily_dead(url):
    host = _get_host(url)
    if not host:
        return

    with _DEAD_HOSTS_LOCK:
        _DEAD_HOSTS[host] = time.time() + SOURCE_DEAD_TTL_SECONDS


def _fetch_text(url):
    if _is_host_temporarily_dead(url):
        return ""

    session = _get_session()
    blocking_issue = False

    try:
        response = session.get(url, timeout=ETFCOM_REQUEST_TIMEOUT)
        response.raise_for_status()
        if "Just a moment" not in response.text[:5000]:
            return response.text
        blocking_issue = True
    except requests.HTTPError:
        return ""
    except requests.RequestException:
        blocking_issue = True

    curl_path = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_path or not blocking_issue:
        return ""

    try:
        completed = subprocess.run(
            [curl_path, "-A", ETFCOM_HEADERS["User-Agent"], "-L", url],
            capture_output=True,
            text=True,
            timeout=ETFCOM_CURL_TIMEOUT,
            check=False,
        )
        if completed.returncode == 0 and "Just a moment" not in completed.stdout[:5000]:
            return completed.stdout
    except (OSError, subprocess.SubprocessError):
        _mark_host_temporarily_dead(url)
        return ""

    _mark_host_temporarily_dead(url)
    return ""


def _split_author_and_date(value):
    cleaned = _clean_text(value)
    if "|" in cleaned:
        author, date_text = [part.strip() for part in cleaned.rsplit("|", 1)]
        return author, date_text
    return cleaned, ""


def _is_relevant_etfcom_news(title, category, author):
    author_text = (author or "").lower()
    title_text = (title or "").lower()
    category_text = (category or "").lower()

    if "financewire" in author_text:
        return False
    if category_text == "news" and "etf" not in title_text:
        return False
    return True


def _load_seed_news(limit=50):
    items = []
    seen_links = set()

    for row in _load_seed_rows(SEED_NEWS_PATH):
        title = _clean_text(unescape(row.get("title", "")))
        category = _clean_text(unescape(row.get("category", "")))
        author = _clean_text(unescape(row.get("author", "")))
        date_text = _clean_text(row.get("date", ""))
        href = _clean_text(row.get("link", ""))
        published_at = _parse_date(date_text, "%Y-%m-%d")
        link = urljoin(ETFCOM_BASE_URL, href)

        if not title or not published_at or link in seen_links:
            continue
        if not _is_relevant_etfcom_news(title, category, author):
            continue

        seen_links.add(link)
        items.append(
            {
                "category": category or "ETF.com",
                "title": title,
                "author": author or "ETF.com",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETF.com",
            }
        )

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items[:limit]


def _load_seed_launches(limit=50):
    items = []

    for row in _load_seed_rows(SEED_LAUNCHES_PATH):
        date_text = _clean_text(row.get("Inception Date", ""))
        ticker = _clean_text(row.get("Ticker", ""))
        fund_name = _clean_text(row.get("Fund Name", ""))
        published_at = _parse_date(date_text, "%m/%d/%Y")

        if not date_text or not ticker or not fund_name or not published_at:
            continue

        items.append(
            {
                "date": published_at.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "fund_name": fund_name,
                "link": urljoin(ETFCOM_BASE_URL, f"/{ticker}"),
                "published_at": published_at,
            }
        )

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items[:limit]


def _load_seed_launches_status(seed_items=None):
    if seed_items is None:
        seed_items = _load_seed_launches(limit=1000)

    metadata = {}
    if SEED_LAUNCHES_STATUS_PATH.exists():
        try:
            metadata = json.loads(SEED_LAUNCHES_STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

    refreshed_at = metadata.get("refreshed_at_utc", "")
    newest_launch_date = metadata.get("newest_launch_date", "")
    item_count = metadata.get("item_count")
    refresh_source = metadata.get("refresh_source", "Scheduled snapshot")
    refresh_success = metadata.get("refresh_success", bool(seed_items))

    if not newest_launch_date and seed_items:
        newest_launch_date = seed_items[0].get("date", "")
    if item_count is None:
        item_count = len(seed_items)

    refreshed_display = ""
    if refreshed_at:
        try:
            refreshed_dt = datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
            refreshed_display = refreshed_dt.astimezone(ZoneInfo("America/New_York")).strftime("%-m/%-d/%y %-I:%M %p ET")
        except ValueError:
            refreshed_display = refreshed_at

    stale = False
    if refreshed_at:
        try:
            refreshed_dt = datetime.fromisoformat(refreshed_at.replace("Z", "+00:00"))
            stale = (datetime.now(ZoneInfo("UTC")) - refreshed_dt.astimezone(ZoneInfo("UTC"))) > timedelta(hours=30)
        except ValueError:
            stale = False

    return {
        "refreshed_at_utc": refreshed_at,
        "refreshed_display": refreshed_display,
        "newest_launch_date": newest_launch_date,
        "item_count": item_count,
        "refresh_source": refresh_source,
        "refresh_success": refresh_success,
        "stale": stale,
    }


def _extract_launch_rows_from_text(html, limit=50):
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean_text(line) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]

    items = []
    seen = set()
    index = 0

    while index < len(lines) - 2 and len(items) < limit:
        date_text = lines[index]
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", date_text):
            index += 1
            continue

        ticker = lines[index + 1].strip().upper()
        published_at = _parse_date(date_text, "%m/%d/%Y")
        if not published_at or not re.fullmatch(r"[A-Z0-9]{2,10}", ticker):
            index += 1
            continue

        name_parts = []
        probe = index + 2
        while probe < len(lines) and len(name_parts) < 4:
            candidate = lines[probe]
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", candidate):
                break
            if candidate in {"Inception Date", "Ticker", "Fund Name"}:
                probe += 1
                continue
            name_parts.append(candidate)
            probe += 1

        fund_name = _clean_text(" ".join(name_parts))
        if "ETF" not in fund_name.upper():
            index += 1
            continue

        row_key = (date_text, ticker, fund_name)
        if row_key in seen:
            index = probe
            continue

        seen.add(row_key)
        items.append(
            {
                "date": published_at.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "fund_name": fund_name,
                "link": urljoin(ETFCOM_BASE_URL, f"/{ticker}"),
                "published_at": published_at,
            }
        )
        index = probe

    items.sort(key=lambda item: item["published_at"], reverse=True)
    if items:
        return items[:limit]

    raw_text = _clean_text(soup.get_text("\n", strip=True))
    section_start = raw_text.find("Inception DateTickerFund Name")
    if section_start == -1:
        section_start = raw_text.find("Inception Date | Ticker | Fund Name")
    if section_start == -1:
        return []

    section = raw_text[section_start:]
    for end_marker in ["Export", "Latest Market News", "### Latest Market News"]:
        end_index = section.find(end_marker)
        if end_index != -1:
            section = section[:end_index]
            break

    dense_pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s*([A-Z0-9]{2,10})\s*(.+?)(?=\d{2}/\d{2}/\d{4}\s*[A-Z0-9]{2,10}|$)",
        re.S,
    )

    dense_items = []
    seen_dense = set()
    for match in dense_pattern.finditer(section):
        date_text = _clean_text(match.group(1))
        ticker = _clean_text(match.group(2)).upper()
        fund_name = _clean_text(match.group(3))
        published_at = _parse_date(date_text, "%m/%d/%Y")

        if not published_at or not re.fullmatch(r"[A-Z0-9]{2,10}", ticker):
            continue
        if "ETF" not in fund_name.upper() and "FUND" not in fund_name.upper():
            continue

        row_key = (date_text, ticker, fund_name)
        if row_key in seen_dense:
            continue
        seen_dense.add(row_key)

        dense_items.append(
            {
                "date": published_at.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "fund_name": fund_name,
                "link": urljoin(ETFCOM_BASE_URL, f"/{ticker}"),
                "published_at": published_at,
            }
        )

    dense_items.sort(key=lambda item: item["published_at"], reverse=True)
    return dense_items[:limit]


def _parse_markdown_news(markdown_text, limit=50):
    if not markdown_text:
        return []

    items = []
    seen_links = set()
    pattern = re.compile(
        r"\n\s*(?P<category>[A-Za-z][^\n\[]{1,80}?)\s*\n\s*"
        r"\[(?P<title>[^\]]+)\]\((?P<href>[^)]+)\)\s*\n\s*"
        r"(?P<author>[^|\n]+)\s*\|\s*(?P<date>[A-Z][a-z]{2} \d{1,2}, \d{4})",
        re.MULTILINE,
    )

    for match in pattern.finditer(markdown_text):
        category = _clean_text(unescape(match.group("category")))
        title = _clean_text(unescape(match.group("title")))
        author = _clean_text(unescape(match.group("author")))
        date_text = _clean_text(match.group("date"))
        href = _clean_text(match.group("href"))
        published_at = _parse_date(date_text, "%b %d, %Y")
        link = urljoin(ETFCOM_BASE_URL, href)

        if not title or not href or title == "Latest News" or not published_at or link in seen_links:
            continue
        if not _is_relevant_etfcom_news(title, category, author):
            continue

        seen_links.add(link)
        items.append(
            {
                "category": category or "ETF.com",
                "title": title,
                "author": author or "ETF.com",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETF.com",
            }
        )

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items[:limit]


def _append_news_item(items, seen_links, title, category, author, date_text, href):
    title = _clean_text(unescape(title))
    category = _clean_text(unescape(category))
    author = _clean_text(unescape(author))
    href = _clean_text(href)
    published_at = _parse_date(_clean_text(date_text), "%b %d, %Y")
    link = urljoin(ETFCOM_BASE_URL, href)

    if not title or not href or not published_at or link in seen_links:
        return
    if "/media-center/" in href:
        return
    if not _is_relevant_etfcom_news(title, category, author):
        return

    seen_links.add(link)
    items.append(
        {
            "category": category or "ETF.com",
            "title": title,
            "author": author or "ETF.com",
            "date": published_at.strftime("%Y-%m-%d"),
            "published_at": published_at,
            "link": link,
            "source": "ETF.com",
        }
    )


def _get_recent_cutoff(days_back):
    return datetime.utcnow() - timedelta(days=days_back)


def _parse_long_date(value):
    value = _clean_text(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %b %Y"):
        parsed = _parse_date(value, fmt)
        if parsed:
            return parsed
    return None


def _extract_etfdb_news_items_from_soup(soup, items, seen_links):
    for title_link in soup.select("a[href]"):
        href = title_link.get("href", "").strip()
        href_match = re.search(r"^/news/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/[^/]+/?$", href)
        if not href_match:
            continue

        title = _clean_text(title_link.get_text(" ", strip=True))
        if len(title) < 10:
            continue

        published_at = datetime(
            int(href_match.group("year")),
            int(href_match.group("month")),
            int(href_match.group("day")),
        )
        link = urljoin(ETFDB_BASE_URL, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append(
            {
                "category": "ETFdb.com",
                "title": title,
                "author": "ETFdb.com",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETFdb.com",
            }
        )


def _extract_etfstream_news_items_from_soup(soup, items, seen_links):
    for title_link in soup.select("a[href*='/articles/']"):
        href = title_link.get("href", "").strip()
        title_blob = _clean_text(title_link.get_text(" ", strip=True))
        if not href or len(title_blob) < 12:
            continue
        if title_blob.lower() in {"news", "analysis", "education", "events", "reports"}:
            continue

        match = re.match(
            r"^(?:(?P<category>[A-Za-z&\-\s]+?)\s+)?(?P<title>.+?)\s+(?P<author>[A-Za-zÀ-ÿ,\.\s]+)\s+(?P<date>\d{2}\s+[A-Za-z]{3}\s+\d{4})(?:\s+Sponsored)?$",
            title_blob,
        )
        if not match:
            continue

        category = _clean_text(match.group("category") or "ETF Stream")
        title = _clean_text(match.group("title"))
        author = _clean_text(match.group("author"))
        published_at = _parse_long_date(match.group("date"))
        link = urljoin(ETFSTREAM_BASE_URL, href)

        if not title or not published_at or link in seen_links:
            continue

        seen_links.add(link)
        items.append(
            {
                "category": category,
                "title": title,
                "author": author or "ETF Stream",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETF Stream",
            }
        )


def _extract_etfexpress_news_items_from_soup(soup, items, seen_links):
    for title_link in soup.select("a[href]"):
        href = title_link.get("href", "").strip()
        href_match = re.search(r"/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/[^/]+/?$", href)
        if not href_match:
            continue

        title = _clean_text(title_link.get_text(" ", strip=True))
        if len(title) < 12 or title.lower() in {"news", "features", "reports", "launches"}:
            continue

        published_at = datetime(
            int(href_match.group("year")),
            int(href_match.group("month")),
            int(href_match.group("day")),
        )
        link = urljoin(ETFEXPRESS_BASE_URL, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append(
            {
                "category": "ETF Express",
                "title": title,
                "author": "ETF Express",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETF Express",
            }
        )


def _extract_trackinsight_news_items_from_soup(soup, items, seen_links):
    for title_link in soup.select("a[href*='/en/etf-news/']"):
        href = title_link.get("href", "").strip()
        if href.startswith("/en/etf-news?") or href.rstrip("/") == "/en/etf-news":
            continue

        title = _clean_text(title_link.get_text(" ", strip=True))
        if len(title) < 12:
            continue

        container = title_link
        context_text = ""
        for _ in range(5):
            container = container.parent
            if container is None:
                break
            context_text = _clean_text(container.get_text(" ", strip=True))
            if re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", context_text):
                break

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            context_text,
        )
        if not date_match:
            continue

        published_at = _parse_long_date(date_match.group(0))
        if not published_at:
            continue

        category = "Trackinsight"
        category_match = re.search(r"\b(Moving Markets|Smart Investing|Big Reads|Ask the Manager|Industry Opinion|Sponsored Content)\b", context_text)
        if category_match:
            category = category_match.group(1)

        link = urljoin(TRACKINSIGHT_BASE_URL, href)
        if link in seen_links:
            continue

        seen_links.add(link)
        items.append(
            {
                "category": category,
                "title": title,
                "author": "Trackinsight",
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "Trackinsight",
            }
        )


def _extract_etfdb_fund_flow_rows(soup):
    items = []

    for row in soup.select("table tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) < 8:
            continue

        issuer = cells[0]
        if not issuer or issuer.lower().startswith("issuers"):
            continue

        rank = ""
        for value in cells[1:4]:
            if re.fullmatch(r"\d+", value):
                rank = value
                break

        flow = ""
        for value in cells[1:8]:
            if re.fullmatch(r"\$[\d,]+\.\d{2}|N/A", value):
                flow = value
                break

        etf_count = ""
        for value in reversed(cells):
            if re.fullmatch(r"\d+", value):
                etf_count = value
                break

        link_tag = row.find("a", href=True)
        link = urljoin(ETFDB_BASE_URL, link_tag.get("href", "").strip()) if link_tag else ""

        if not issuer or not rank or not flow:
            continue

        items.append(
            {
                "issuer": issuer,
                "rank": int(rank),
                "flow": flow,
                "etf_count": etf_count,
                "link": link,
            }
        )

    deduped = []
    seen = set()
    for item in sorted(items, key=lambda item: (item["rank"], item["issuer"])):
        key = item["issuer"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_news_items_from_soup(soup, items, seen_links):
    selectors = [
        ("div.image-card", ".image-card__title a", ".image-card__category", ".image-card__author"),
        ("div.text-card", ".text-card__title a", ".text-card__topic", ".text-card__author"),
    ]

    for card_selector, title_selector, category_selector, author_selector in selectors:
        for card in soup.select(card_selector):
            title_link = card.select_one(title_selector)
            category_el = card.select_one(category_selector)
            author_el = card.select_one(author_selector)

            if not title_link or not author_el:
                continue

            href = title_link.get("href", "").strip()
            title = title_link.get_text(" ", strip=True)
            category = category_el.get_text(" ", strip=True) if category_el else ""
            author_text = author_el.get_text(" ", strip=True)
            author, date_text = _split_author_and_date(author_text)
            _append_news_item(items, seen_links, title, category, author, date_text, href)


def _finalize_news_items(items, cutoff, limit):
    items.sort(key=lambda item: item["published_at"], reverse=True)
    recent_items = [item for item in items if item["published_at"] >= cutoff]
    if recent_items:
        return recent_items[:limit]
    return items[:limit]


def _fetch_paged_news(
    page_builder: Callable[[int], str],
    extractor: Callable[[BeautifulSoup, list, set], None],
    days_back: int,
    max_pages: int,
    limit: int,
):
    cutoff = _get_recent_cutoff(days_back)
    items = []
    seen_links = set()

    for page_index in range(1, max_pages + 1):
        html = _fetch_text(page_builder(page_index))
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        before_count = len(items)
        extractor(soup, items, seen_links)

        if len(items) >= limit:
            break
        if items and min(item["published_at"] for item in items) <= cutoff and page_index >= 3:
            break
        if len(items) == before_count and page_index >= 3:
            break

    return _finalize_news_items(items, cutoff, limit)


def fetch_etfcom_news(limit=50):
    cutoff = _get_recent_cutoff(ETFCOM_NEWS_DAYS_BACK)
    markdown_text = _fetch_text(f"{ETFCOM_BASE_URL}/node/55188.md")
    markdown_items = _parse_markdown_news(markdown_text, limit=limit)
    if markdown_items:
        recent_markdown_items = [item for item in markdown_items if item["published_at"] >= cutoff]
        if len(recent_markdown_items) >= limit:
            return recent_markdown_items[:limit]

    items = []
    seen_links = set()

    for item in markdown_items:
        link = item.get("link", "")
        if link and link not in seen_links:
            seen_links.add(link)
            items.append(item)

    for page_index in range(ETFCOM_NEWS_MAX_PAGES):
        page_url = f"{ETFCOM_BASE_URL}/news?page={page_index}" if page_index else f"{ETFCOM_BASE_URL}/news"
        html = _fetch_text(page_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        before_count = len(items)
        _extract_news_items_from_soup(soup, items, seen_links)

        if len(items) >= limit:
            break
        if items and min(item["published_at"] for item in items) <= cutoff and page_index >= 2:
            break
        if len(items) == before_count and page_index >= 2:
            break

    items.sort(key=lambda item: item["published_at"], reverse=True)
    recent_items = [item for item in items if item["published_at"] >= cutoff]
    if recent_items:
        return recent_items[:limit]
    if items:
        return items[:limit]
    return _load_seed_news(limit=limit)


def fetch_etfdb_news(limit=50):
    return _fetch_paged_news(
        lambda page_index: f"{ETFDB_BASE_URL}/news/" if page_index == 1 else f"{ETFDB_BASE_URL}/news/page/{page_index}/",
        _extract_etfdb_news_items_from_soup,
        ETFDB_NEWS_DAYS_BACK,
        ETFDB_NEWS_MAX_PAGES,
        limit,
    )


def fetch_etfstream_news(limit=50):
    return _fetch_paged_news(
        lambda page_index: f"{ETFSTREAM_BASE_URL}/news" if page_index == 1 else f"{ETFSTREAM_BASE_URL}/news/page/{page_index}",
        _extract_etfstream_news_items_from_soup,
        ETFSTREAM_NEWS_DAYS_BACK,
        ETFSTREAM_NEWS_MAX_PAGES,
        limit,
    )


def fetch_etfexpress_news(limit=50):
    return _fetch_paged_news(
        lambda page_index: f"{ETFEXPRESS_BASE_URL}/news/" if page_index == 1 else f"{ETFEXPRESS_BASE_URL}/news/page/{page_index}/",
        _extract_etfexpress_news_items_from_soup,
        ETFEXPRESS_NEWS_DAYS_BACK,
        ETFEXPRESS_NEWS_MAX_PAGES,
        limit,
    )


def fetch_trackinsight_news(limit=50):
    return _fetch_paged_news(
        lambda page_index: f"{TRACKINSIGHT_BASE_URL}/en/etf-news" if page_index == 1 else f"{TRACKINSIGHT_BASE_URL}/en/etf-news?p={page_index}",
        _extract_trackinsight_news_items_from_soup,
        TRACKINSIGHT_NEWS_DAYS_BACK,
        TRACKINSIGHT_NEWS_MAX_PAGES,
        limit,
    )


def fetch_etf_news(limit=50):
    items = []
    seen_links = set()
    fetchers = (
        fetch_etfcom_news,
        fetch_etfdb_news,
        fetch_etfstream_news,
        fetch_etfexpress_news,
        fetch_trackinsight_news,
    )

    with ThreadPoolExecutor(max_workers=min(NEWS_SOURCE_MAX_WORKERS, len(fetchers))) as executor:
        futures = [executor.submit(fetcher, limit) for fetcher in fetchers]
        for future in as_completed(futures):
            try:
                source_items = future.result()
            except Exception:
                continue

            for item in source_items:
                link = item.get("link", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                items.append(item)

    items.sort(key=lambda item: item.get("published_at", datetime.min), reverse=True)
    return items[:limit]


def fetch_etfdb_fund_flows(limit=100):
    html = _fetch_text(
        f"{ETFDB_BASE_URL}/etfs/issuers/#issuer-power-rankings__fund-flow&sort_name=revenue_position&sort_order=asc&page=1"
    )
    if not html:
        html = _fetch_text(f"{ETFDB_BASE_URL}/etfs/issuers/")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = _extract_etfdb_fund_flow_rows(soup)
    return items[:limit]


def fetch_live_etfcom_launches(limit=50):
    aggregated_items = []
    seen_rows = set()

    def add_launch_item(item):
        row_key = (item["date"], item["ticker"], item["fund_name"])
        if row_key in seen_rows:
            return
        seen_rows.add(row_key)
        aggregated_items.append(item)

    csv_text = _fetch_text(f"{ETFCOM_BASE_URL}/launches/data/download?nopaging=1&page&_format=csv")
    if csv_text:
        reader = csv.DictReader(StringIO(csv_text))
        for row in reader:
            date_text = _clean_text(row.get("Inception Date", ""))
            ticker = _clean_text(row.get("Ticker", ""))
            fund_name = _clean_text(row.get("Fund Name", ""))
            published_at = _parse_date(date_text, "%m/%d/%Y")

            if not date_text or not ticker or not fund_name or not published_at:
                continue

            add_launch_item(
                {
                    "date": published_at.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "fund_name": fund_name,
                    "link": urljoin(ETFCOM_BASE_URL, f"/{ticker}"),
                    "published_at": published_at,
                }
            )

    launch_pages = [
        f"{ETFCOM_BASE_URL}/tools/etf-launches?page=1",
        f"{ETFCOM_BASE_URL}/tools/etf-launches",
        f"{ETFCOM_BASE_URL}/tools/etf-launches?nopaging=1&page=1",
        f"{ETFCOM_BASE_URL}/topics/etf-launches",
    ]

    for page_url in launch_pages:
        html = _fetch_text(page_url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.cols-3") or soup.find("table")
        if table:
            for row in table.select("tbody tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue

                date_text = _clean_text(cells[0].get_text(" ", strip=True))
                ticker_link = cells[1].find("a")
                ticker = _clean_text(cells[1].get_text(" ", strip=True))
                fund_name = _clean_text(cells[2].get_text(" ", strip=True))
                published_at = _parse_date(date_text, "%m/%d/%Y")
                link = urljoin(ETFCOM_BASE_URL, ticker_link.get("href", "").strip()) if ticker_link else ""

                if not date_text or not ticker or not fund_name or not published_at:
                    continue

                add_launch_item(
                    {
                        "date": published_at.strftime("%Y-%m-%d"),
                        "ticker": ticker,
                        "fund_name": fund_name,
                        "link": link,
                        "published_at": published_at,
                    }
                )

        text_rows = _extract_launch_rows_from_text(html, limit=limit)
        for item in text_rows:
            add_launch_item(item)

    aggregated_items.sort(key=lambda item: item["published_at"], reverse=True)
    return aggregated_items[:limit]


def _merge_launch_items(*launch_sets):
    merged_items = []
    seen_rows = set()

    for item in sorted(
        [item for launch_set in launch_sets for item in launch_set],
        key=lambda current: current.get("published_at", datetime.min),
        reverse=True,
    ):
        row_key = (item.get("date"), item.get("ticker"), item.get("fund_name"))
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        merged_items.append(item)

    return merged_items


def fetch_etfcom_launches(limit=50):
    live_items = fetch_live_etfcom_launches(limit=limit)
    seed_items = _load_seed_launches(limit=limit)
    merged_items = _merge_launch_items(live_items, seed_items)
    return merged_items[:limit]


def fetch_etfcom_launches_with_status(limit=50):
    items = fetch_live_etfcom_launches(limit=limit)
    seed_items = _load_seed_launches(limit=limit)
    merged_items = _merge_launch_items(items, seed_items)

    if items and seed_items:
        live_latest = items[0].get("published_at", datetime.min)
        seed_latest = seed_items[0].get("published_at", datetime.min)
        if seed_latest > live_latest:
            return {"items": merged_items[:limit], "status": "Fallback snapshot"}
        return {"items": merged_items[:limit], "status": "Live ETF.com"}
    if items:
        return {"items": merged_items[:limit], "status": "Live ETF.com"}

    return {"items": merged_items[:limit], "status": "Fallback snapshot"}


def fetch_scheduled_etfcom_launches_with_status(limit=50):
    seed_items = _load_seed_launches(limit=limit)
    if not seed_items:
        return {
            "items": [],
            "status": "Snapshot unavailable",
            "metadata": _load_seed_launches_status(seed_items=[]),
        }
    return {
        "items": seed_items[:limit],
        "status": "Scheduled snapshot",
        "metadata": _load_seed_launches_status(seed_items=seed_items),
    }
