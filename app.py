import streamlit as st
import pandas as pd
import requests
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import html
import re

HEADERS = {
    "User-Agent": "ETF Dashboard (jhaley1212@gmail.com)"
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

    fallback_text = clean_html_text(text)
    fallback = re.search(r'([A-Z][A-Za-z0-9&\s\-]{5,100}(ETF|Fund))', fallback_text)
    return fallback.group(1).strip() if fallback else "N/A"


def clean_html_text(value):
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    return " ".join(decoded.split())


def fetch_filings():
    results = []
    seen_links = set()
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
                if link in seen_links:
                    continue

                seen_links.add(link)

                results.append({
                    "etf_name": extract_etf_name(text),
                    "form": form,
                    "date": date_str,
                    "link": link
                })

                time.sleep(0.2)

            if stop_loop:
                break

            start += 100

    return results

st.set_page_config(page_title="ProShares ETF Filings", layout="wide")

st.title("ProShares ETF Filings")
st.write("Recent ProShares registration filings")


@st.cache_data(ttl=60)
def load_filings():
    return fetch_filings()

try:
    with st.spinner("Checking the SEC website for the latest filings..."):
        data = load_filings()
except Exception as exc:
    st.error(
        "The app could not reach the SEC website right now. "
        "Please wait a moment and the page will try again automatically."
    )
    st.exception(exc)
else:
    df = pd.DataFrame(data)

    if not df.empty:
        df = df.sort_values(by="date", ascending=False)
        st.success(f"Loaded {len(df)} filing(s).")
        st.dataframe(
            df[["etf_name", "form", "date", "link"]],
            use_container_width=True,
        )

        for _, row in df.iterrows():
            st.markdown(f"### {row['etf_name']}")
            st.markdown(f"**Form:** {row['form']} | **Date:** {row['date']}")
            st.markdown(f"[View Filing]({row['link']})")
            st.markdown("---")
    else:
        st.info("No recent filings were found in the current search window.")
