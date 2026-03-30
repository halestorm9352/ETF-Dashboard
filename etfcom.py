from datetime import datetime
import shutil
import subprocess
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ETFCOM_BASE_URL = "https://www.etf.com"
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


def _fetch_text(url):
    session = requests.Session()
    session.headers.update(ETFCOM_HEADERS)

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        if "Just a moment" not in response.text[:5000]:
            return response.text
    except requests.RequestException:
        pass

    curl_path = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_path:
        return ""

    try:
        completed = subprocess.run(
            [curl_path, "-A", ETFCOM_HEADERS["User-Agent"], "-L", url],
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        if completed.returncode == 0 and "Just a moment" not in completed.stdout[:5000]:
            return completed.stdout
    except (OSError, subprocess.SubprocessError):
        return ""

    return ""


def _split_author_and_date(value):
    cleaned = _clean_text(value)
    if "|" in cleaned:
        author, date_text = [part.strip() for part in cleaned.rsplit("|", 1)]
        return author, date_text
    return cleaned, ""


def fetch_etfcom_news(limit=50):
    html = _fetch_text(f"{ETFCOM_BASE_URL}/latest-news")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_links = set()

    for card in soup.select("div.image-card"):
        title_link = card.select_one(".image-card__title a")
        category_el = card.select_one(".image-card__category")
        author_el = card.select_one(".image-card__author")

        if not title_link:
            continue

        href = title_link.get("href", "").strip()
        title = _clean_text(title_link.get_text(" ", strip=True))
        category = _clean_text(category_el.get_text(" ", strip=True)) if category_el else ""
        author_text = _clean_text(author_el.get_text(" ", strip=True)) if author_el else ""
        author, date_text = _split_author_and_date(author_text)
        published_at = _parse_date(date_text, "%b %d, %Y")
        link = urljoin(ETFCOM_BASE_URL, href)

        if not title or not href or link in seen_links or not published_at:
            continue
        if "/media-center/" in href:
            continue

        seen_links.add(link)
        items.append(
            {
                "category": category or "ETF.com",
                "title": title,
                "author": author,
                "date": published_at.strftime("%Y-%m-%d"),
                "published_at": published_at,
                "link": link,
                "source": "ETF.com",
            }
        )

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items[:limit]


def fetch_etfcom_launches(limit=50):
    html = _fetch_text(f"{ETFCOM_BASE_URL}/tools/etf-launches?nopaging=1&page=1")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.cols-3") or soup.find("table")
    if not table:
        return []

    items = []
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

        items.append(
            {
                "date": published_at.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "fund_name": fund_name,
                "link": link,
                "published_at": published_at,
            }
        )

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items[:limit]
