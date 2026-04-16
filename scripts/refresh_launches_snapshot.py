import csv
from io import StringIO
from pathlib import Path

from etfcom import fetch_live_etfcom_launches


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "etfcom_launches_seed.csv"


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


def main():
    items = fetch_live_etfcom_launches(limit=1000)
    if not items:
        print("No live ETF.com launches were fetched. Leaving snapshot unchanged.")
        return

    csv_text = build_csv_text(items)
    current_text = SEED_PATH.read_text(encoding="utf-8") if SEED_PATH.exists() else ""

    if csv_text == current_text:
        print("ETF.com launches snapshot is already current.")
        return

    SEED_PATH.write_text(csv_text, encoding="utf-8", newline="\n")
    newest = items[0].get("date", "unknown")
    print(f"Updated ETF.com launches snapshot. Newest launch date: {newest}")


if __name__ == "__main__":
    main()
