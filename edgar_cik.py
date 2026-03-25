import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import re

HEADERS = {
    "User-Agent": "jhaley1212@gmail.com"
}

CIK = "0001174610"
FORMS = ["S-1", "N-1A", "485BPOS", "485APOS"]
DAYS_BACK = 60


def extract_text(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text[:20000]
    except requests.RequestException:
        return ""


def extract_etf_name(text):
    match = re.search(r'([A-Z][A-Za-z0-9\s\-]{5,100}(ETF|Fund))', text)
    return match.group(1).strip() if match else "N/A"


def extract_strategy(text):
    patterns = [
        r"investment objective.*?\.",
        r"principal investment strategy.*?\.",
        r"principal investment strategies.*?\."
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return "N/A"


def fetch_filings():
    results = []
    cutoff_date = datetime.today() - timedelta(days=DAYS_BACK)

    for form in FORMS:
        start = 0

        while True:
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={CIK}&type={form}&owner=exclude&count=100&start={start}&output=atom"

            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)

            entries = root.findall("{http://www.w3.org/2005/Atom}entry")

            if not entries:
                break

            stop_loop = False

            for entry in entries:
                link = entry.find("{http://www.w3.org/2005/Atom}link").attrib["href"]
                date_str = entry.find("{http://www.w3.org/2005/Atom}updated").text[:10]

                date = datetime.strptime(date_str, "%Y-%m-%d")

                if date < cutoff_date:
                    stop_loop = True
                    break

                text = extract_text(link)

                etf_name = extract_etf_name(text)
                strategy = extract_strategy(text)

                results.append({
                    "etf_name": etf_name,
                    "strategy": strategy,
                    "form": form,
                    "date": date_str,
                    "link": link
                })

                time.sleep(0.2)

            if stop_loop:
                break

            start += 100

    return results
