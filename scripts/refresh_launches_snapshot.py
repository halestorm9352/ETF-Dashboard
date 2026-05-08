import csv
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "etfcom_launches_seed.csv"
STATUS_PATH = ROOT / "etfcom_launches_status.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etfcom import fetch_live_etfcom_launches
from sec_parsers import clean_html_text


def build_csv_text(items):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["Inception Date", "Ticker", "Fund Name"], lineterminator="\n")
    writer.writeheader()

    for item in items:
        published_at = item.get("published_at")
        if published_at is None:
            continue
        writer.writerow(
            {
                "Inception Date": published_at.strftime("%m/%d/%Y"),
                "Ticker": item.get("ticker", ""),
                "Fund Name": item.get("fund_name", ""),
            }
        )

    return buffer.getvalue()


def build_status_payload(items, refresh_source):
    newest = items[0].get("date", "") if items else ""
    return {
        "refreshed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "newest_launch_date": newest,
        "item_count": len(items),
        "refresh_source": refresh_source,
        "refresh_success": bool(items),
    }


def fetch_browser_launches():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    launch_urls = [
        "https://www.etf.com/tools/etf-launches",
        "https://www.etf.com/topics/etf-launches",
    ]

    items = []
    seen = set()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(30000)

        for url in launch_urls:
            try:
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(2500)
                text = page.locator("body").inner_text()
            except Exception:
                continue

            lines = [clean_html_text(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            index = 0
            while index < len(lines) - 2 and len(items) < 1000:
                date_text = lines[index]
                if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", date_text):
                    index += 1
                    continue

                ticker = lines[index + 1].strip().upper()
                published_at = datetime.strptime(date_text, "%m/%d/%Y")
                if not re.fullmatch(r"[A-Z0-9]{2,10}", ticker):
                    index += 1
                    continue

                name_parts = []
                probe = index + 2
                while probe < len(lines) and len(name_parts) < 4:
                    candidate = lines[probe]
                    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", candidate):
                        break
                    if candidate in {"Inception Date", "Ticker", "Fund Name", "ETF Launches", "Swipe"}:
                        probe += 1
                        continue
                    name_parts.append(candidate)
                    probe += 1

                fund_name = clean_html_text(" ".join(name_parts))
                if "ETF" not in fund_name.upper() and "FUND" not in fund_name.upper():
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
                        "link": f"https://www.etf.com/{ticker}",
                        "published_at": published_at,
                    }
                )
                index = probe

        browser.close()

    items.sort(key=lambda item: item["published_at"], reverse=True)
    return items


def main():
    items = fetch_live_etfcom_launches(limit=1000)
    browser_items = fetch_browser_launches()
    refresh_source = "direct fetch"
    if browser_items and (
        not items
        or browser_items[0].get("published_at") > items[0].get("published_at")
    ):
        items = browser_items
        refresh_source = "browser fallback"
    if not items:
        print("No live ETF.com launches were fetched. Leaving snapshot unchanged.")
        return

    csv_text = build_csv_text(items)
    status_payload = build_status_payload(items, refresh_source)
    status_text = json.dumps(status_payload, indent=2) + "\n"
    current_text = SEED_PATH.read_text(encoding="utf-8") if SEED_PATH.exists() else ""
    current_status_text = STATUS_PATH.read_text(encoding="utf-8") if STATUS_PATH.exists() else ""

    if csv_text == current_text and status_text == current_status_text:
        print("ETF.com launches snapshot is already current.")
        return

    SEED_PATH.write_text(csv_text, encoding="utf-8", newline="\n")
    STATUS_PATH.write_text(status_text, encoding="utf-8", newline="\n")
    newest = items[0].get("date", "unknown")
    print(f"Updated ETF.com launches snapshot. Newest launch date: {newest}")


if __name__ == "__main__":
    main()
