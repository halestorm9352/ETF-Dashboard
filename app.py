import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import html
import re

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
DATA_VERSION = "2026-03-25-filer-fix"


def extract_text(url, max_chars=20000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text[:max_chars]
    except requests.RequestException:
        return ""


def extract_etf_name(text):
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
    cleaned_text = clean_html_text(text)

    pipe_match = re.search(
        r'([A-Z]{2,6})\s*\|\s*([A-Za-z0-9&\-\.\s]{3,120}?(ETF|Fund))',
        cleaned_text,
        re.IGNORECASE,
    )
    if pipe_match:
        ticker = pipe_match.group(1).upper()
        if ticker != "CIK":
            return ticker

    ticker_cell_match = re.search(
        r'Ticker Symbol\s+([A-Z]{1,8})',
        cleaned_text,
        re.IGNORECASE,
    )
    if ticker_cell_match:
        ticker = ticker_cell_match.group(1).upper()
        if ticker != "CIK":
            return ticker

    return ""


def clean_html_text(value):
    without_tags = re.sub(r"<[^>]+>", " ", value)
    decoded = html.unescape(without_tags)
    return " ".join(decoded.split())


def build_sec_url(path_or_url):
    if path_or_url.startswith("http"):
        return path_or_url
    return f"https://www.sec.gov{path_or_url}"


def extract_supporting_document_urls(index_text):
    html_match = re.search(
        r'href="/ix\?doc=(/Archives/edgar/data/[^"]+\.htm)"',
        index_text,
        re.IGNORECASE,
    )
    xml_match = re.search(
        r'href="(/Archives/edgar/data/[^"]+_htm\.xml)"',
        index_text,
        re.IGNORECASE,
    )

    html_url = build_sec_url(html_match.group(1)) if html_match else ""
    xml_url = build_sec_url(xml_match.group(1)) if xml_match else ""
    return html_url, xml_url


def fetch_supporting_document_text(index_text):
    html_url, xml_url = extract_supporting_document_urls(index_text)
    html_text = extract_text(html_url, max_chars=120000) if html_url else ""
    xml_text = extract_text(xml_url, max_chars=120000) if xml_url else ""
    return html_text, xml_text


def fetch_recent_filings_for_cik(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        return {
            "filer_name": data.get("name", CIK_LOOKUP.get(cik, cik)),
            "recent": data.get("filings", {}).get("recent", {}),
        }
    except requests.RequestException:
        return {
            "filer_name": CIK_LOOKUP.get(cik, cik),
            "recent": {},
        }


def fetch_filings():
    results = []
    seen_links = set()
    cutoff_date = datetime.today() - timedelta(days=DAYS_BACK)

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

        for index, form in enumerate(forms):
            if form not in FORMS:
                continue

            if index >= len(filing_dates) or index >= len(accession_numbers):
                continue

            date_str = filing_dates[index]
            date = datetime.strptime(date_str, "%Y-%m-%d")
            if date < cutoff_date:
                continue

            accession_number = accession_numbers[index]
            accession_clean = accession_number.replace("-", "")
            filing_link = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession_clean}/{accession_number}-index.htm"
            )

            if filing_link in seen_links:
                continue

            text = extract_text(filing_link)
            seen_links.add(filing_link)

            ticker = extract_ticker(text)
            etf_name = extract_etf_name(text)

            if etf_name == "N/A" or not ticker:
                supporting_html, supporting_xml = fetch_supporting_document_text(text)

                if etf_name == "N/A" and supporting_html:
                    etf_name = extract_etf_name(supporting_html)
                if etf_name == "N/A" and supporting_xml:
                    etf_name = extract_etf_name(supporting_xml)

                if not ticker and supporting_html:
                    ticker = extract_ticker(supporting_html)
                if not ticker and supporting_xml:
                    ticker = extract_ticker(supporting_xml)

            results.append({
                "ticker": ticker,
                "etf_name": etf_name,
                "filer": filer_name,
                "form": form,
                "date": date_str,
                "link": filing_link
            })

            time.sleep(REQUEST_DELAY_SECONDS)

        time.sleep(REQUEST_DELAY_SECONDS)

    return results

st.set_page_config(page_title="ProShares ETF Filings", layout="wide")

st.title("ETF Filings")
st.write("Recent registration filings across the selected ETF issuers")


@st.cache_data(ttl=1800)
def load_filings(_data_version):
    return fetch_filings()

try:
    with st.spinner("Checking the SEC website for the latest filings..."):
        data = load_filings(DATA_VERSION)
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

        df = df.sort_values(by="date", ascending=False)
        st.success(f"Loaded {len(df)} filing(s).")
        st.dataframe(
            df[["ticker", "etf_name", "filer", "form", "date", "link"]],
            use_container_width=True,
        )

        for _, row in df.iterrows():
            st.markdown(f"### {row['etf_name']}")
            if row["ticker"]:
                st.markdown(f"**Ticker:** {row['ticker']}")
            st.markdown(f"**Filer:** {row['filer']}")
            st.markdown(f"**Form:** {row['form']} | **Date:** {row['date']}")
            st.markdown(f"[View Filing]({row['link']})")
            st.markdown("---")
    else:
        st.warning(
            "No recent filings were loaded right now. "
            "The SEC may be rate-limiting some requests, so please try again shortly."
        )
