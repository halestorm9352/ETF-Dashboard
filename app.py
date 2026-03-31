import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

from config import DATA_VERSION, ETFCOM_DATA_VERSION
from etfcom import fetch_etf_news, fetch_etfcom_launches
from news_sources import format_news_date
from sec_filings import fetch_filings
from sec_parsers import sanitize_ticker


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
        font-size: 0.66rem;
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


@st.cache_data(ttl=3600)
def load_etfcom_news(_version):
    return fetch_etf_news(limit=800)


@st.cache_data(ttl=3600)
def load_etfcom_launches(_version):
    return fetch_etfcom_launches(limit=1000)


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
    launches_col, center_col, news_col = st.columns([1.05, 1.8, 1.05], gap="large")

    with launches_col:
        st.markdown('<div class="etf-section-title">Launches</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Recent launches from ETF.com.</div>',
            unsafe_allow_html=True,
        )
        launches_items = load_etfcom_launches(ETFCOM_DATA_VERSION)
        if launches_items:
            launches_container = st.container(height=760)
            for item in launches_items[:1000]:
                launches_container.markdown(
                    f"""
                    <div class="etf-news-item">
                        <div class="etf-news-source">{item.get("date", "")}</div>
                        <a class="etf-news-title" href="{item.get("link", "#")}" target="_blank">{item.get("ticker", "")}</a>
                        <div class="etf-news-kicker">{item.get("fund_name", "")}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("ETF.com launches were not available right now.")

    with center_col:
        st.markdown('<div class="etf-section-title">Filings</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Search SEC filings by date range, with the newest filings displayed first.</div>',
            unsafe_allow_html=True,
        )
        with st.form("date_filter_form"):
            filter_cols = st.columns([1, 1, 0.45])
            filter_cols[0].date_input("Start date", min_value=year_start, max_value=default_end, key="search_start_date")
            filter_cols[1].date_input("End date", min_value=year_start, max_value=default_end, key="search_end_date")
            search_submitted = filter_cols[2].form_submit_button("Search")

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
                    df = df.dropna(subset=["date"])
                    filtered_df = df[
                        (df["date"].dt.date >= st.session_state.search_start_date)
                        & (df["date"].dt.date <= st.session_state.search_end_date)
                    ].copy()
                    filtered_df = filtered_df.sort_values(
                        by=["date", "link", "ticker", "etf_name"],
                        ascending=[False, True, True, True],
                        kind="stable",
                    )
                    filtered_df["ticker"] = filtered_df["ticker"].apply(sanitize_ticker)
                    display_df = filtered_df.copy()
                    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
                    filings_count = len(display_df)
                    listed_tickers = int((filtered_df["ticker"] != "Not Listed").sum())
                    distinct_filers = int(filtered_df["filer"].nunique())
                    latest_dt = filtered_df.iloc[0]["date"] if not filtered_df.empty else None
                    latest_date = (
                        f"{latest_dt.month}/{latest_dt.day}/{latest_dt.year % 100:02d}"
                        if latest_dt is not None else "N/A"
                    )
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

                    st.success(f"Loaded {filings_count} filing(s) in the selected date range.")
                    st.dataframe(
                        display_df[["ticker", "etf_name", "filer", "date", "link"]],
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("No recent filings were loaded right now. The SEC may be rate-limiting some requests, so please try again shortly.")

    with news_col:
        st.markdown('<div class="etf-section-title">News</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Recent headlines from ETF.com, ETFdb.com, ETF Stream, ETF Express, and Trackinsight.</div>',
            unsafe_allow_html=True,
        )
        news_items = load_etfcom_news(ETFCOM_DATA_VERSION)
        if news_items:
            news_container = st.container(height=760)
            for item in news_items[:800]:
                news_date = item.get("date", "") or format_news_date(item.get("pub_date", ""))
                news_container.markdown(
                    f"""
                    <div class="etf-news-item">
                        <div class="etf-news-source">{item.get("category", item.get("source", "ETF.com"))}</div>
                        <a class="etf-news-title" href="{item.get("link", "#")}" target="_blank">{item.get("title", "Headline")}</a>
                        <div class="etf-news-meta">{item.get("author", item.get("source", "ETF.com"))} | {news_date}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("ETF.com and ETFdb.com headlines will appear here once the feeds refresh.")
