import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from html import escape

from config import DATA_VERSION, ETFCOM_DATA_VERSION
try:
    from etfcom import fetch_etf_news, fetch_etfcom_launches, fetch_etfdb_fund_flows
except ImportError:
    from etfcom import fetch_etf_news, fetch_etfcom_launches

    def fetch_etfdb_fund_flows(limit=100):
        return []
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

    .etf-ticker-shell {
        border: 1px solid var(--etf-border);
        background: var(--etf-card);
        border-radius: 16px;
        overflow: hidden;
        margin: 0.5rem 0 1.25rem;
    }

    .etf-ticker-label {
        color: var(--etf-accent);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 0.7rem 1rem 0.45rem;
        border-bottom: 1px solid var(--etf-border);
    }

    .etf-ticker-window {
        overflow: hidden;
        white-space: nowrap;
        position: relative;
    }

    .etf-ticker-track {
        display: inline-flex;
        align-items: center;
        gap: 2.5rem;
        width: max-content;
        padding: 0.8rem 0;
        animation: etfTickerMove 450s linear infinite;
    }

    .etf-ticker-shell:hover .etf-ticker-track {
        animation-play-state: paused;
    }

    .etf-ticker-item {
        display: inline-flex;
        align-items: center;
        gap: 0.65rem;
    }

    .etf-ticker-item a {
        font-weight: 700;
        text-decoration: none;
    }

    .etf-ticker-meta {
        color: var(--etf-muted);
        font-size: 0.85rem;
    }

    @keyframes etfTickerMove {
        from {
            transform: translateX(0);
        }
        to {
            transform: translateX(-50%);
        }
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


@st.cache_data(ttl=43200)
def load_etfdb_fund_flows(_version):
    return fetch_etfdb_fund_flows(limit=250)


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

news_items = load_etfcom_news(ETFCOM_DATA_VERSION)
fund_flow_items = load_etfdb_fund_flows(ETFCOM_DATA_VERSION)

if news_items:
    ticker_items_html = "".join(
        [
            (
                f'<span class="etf-ticker-item">'
                f'<a href="{escape(item.get("link", "#"))}" target="_blank">{escape(item.get("title", "Headline"))}</a>'
                f'<span class="etf-ticker-meta">{escape(item.get("source", "ETF"))} | {escape(item.get("date", ""))}</span>'
                f'</span>'
            )
            for item in news_items[:60]
        ]
    )
    ticker_component_html = """
    <!doctype html>
    <html>
    <head>
    <style>
    @import url('https://fonts.googleapis.com/css2?family=PT+Sans+Narrow:wght@400;700&display=swap');

    :root {
        --etf-accent: #138a36;
        --etf-card: #121722;
        --etf-border: rgba(255, 255, 255, 0.08);
        --etf-muted: #aeb7c7;
        --etf-text: #f3f6fb;
    }

    html, body {
        margin: 0;
        padding: 0;
        background: transparent;
        color: var(--etf-text);
        font-family: 'PT Sans Narrow', sans-serif;
    }

    .etf-ticker-shell {
        border: 1px solid var(--etf-border);
        background: var(--etf-card);
        border-radius: 16px;
        overflow: hidden;
    }

    .etf-ticker-label {
        color: var(--etf-accent);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        padding: 0.7rem 1rem 0.45rem;
        border-bottom: 1px solid var(--etf-border);
    }

    .etf-ticker-window {
        overflow: hidden;
        white-space: nowrap;
        position: relative;
    }

    .etf-ticker-track {
        display: inline-flex;
        align-items: center;
        gap: 2.5rem;
        width: max-content;
        padding: 0.8rem 0;
        will-change: transform;
    }

    .etf-ticker-item {
        display: inline-flex;
        align-items: center;
        gap: 0.65rem;
    }

    .etf-ticker-item a {
        font-weight: 700;
        text-decoration: none;
        color: #41a5ff;
    }

    .etf-ticker-meta {
        color: var(--etf-muted);
        font-size: 0.85rem;
    }

    .etf-ticker-scrubber-wrap {
        padding: 0.25rem 1rem 0.8rem;
        border-top: 1px solid var(--etf-border);
        background: rgba(255, 255, 255, 0.015);
    }

    .etf-ticker-scrubber {
        width: 100%;
        margin: 0;
        accent-color: var(--etf-accent);
        background: transparent;
    }

    .etf-ticker-scrubber::-webkit-slider-runnable-track {
        height: 6px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.12);
    }

    .etf-ticker-scrubber::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        margin-top: -4px;
        background: var(--etf-accent);
        border: 0;
        cursor: pointer;
    }

    .etf-ticker-scrubber::-moz-range-track {
        height: 6px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.12);
        border: 0;
    }

    .etf-ticker-scrubber::-moz-range-thumb {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: var(--etf-accent);
        border: 0;
        cursor: pointer;
    }
    </style>
    </head>
    <body>
        <div class="etf-ticker-shell" id="ticker-shell">
            <div class="etf-ticker-label">News Wire</div>
            <div class="etf-ticker-window">
                <div class="etf-ticker-track" id="ticker-track">""" + ticker_items_html + ticker_items_html + """</div>
            </div>
            <div class="etf-ticker-scrubber-wrap">
                <input
                    class="etf-ticker-scrubber"
                    id="ticker-scrubber"
                    type="range"
                    min="0"
                    max="100"
                    value="0"
                    aria-label="News wire scrubber"
                />
            </div>
        </div>

        <script>
        const shell = document.getElementById("ticker-shell");
        const track = document.getElementById("ticker-track");
        const scrubber = document.getElementById("ticker-scrubber");

        let singleWidth = 0;
        let offset = 0;
        let lastFrame = null;
        let hoverPaused = false;
        let dragging = false;

        function measureTrack() {
            singleWidth = track.scrollWidth / 2;
            scrubber.max = Math.max(1, Math.round(singleWidth));
            scrubber.value = Math.min(Number(scrubber.value || 0), Number(scrubber.max));
        }

        function applyOffset() {
            if (!singleWidth) {
                return;
            }
            const normalized = ((offset % singleWidth) + singleWidth) % singleWidth;
            track.style.transform = `translateX(${-normalized}px)`;
            if (!dragging) {
                scrubber.value = Math.round(normalized);
            }
        }

        function tick(timestamp) {
            if (lastFrame === null) {
                lastFrame = timestamp;
            }

            const elapsed = timestamp - lastFrame;
            lastFrame = timestamp;

            if (!hoverPaused && !dragging && singleWidth > 0) {
                const pixelsPerMs = singleWidth / 450000;
                offset += elapsed * pixelsPerMs;
                if (offset >= singleWidth) {
                    offset -= singleWidth;
                }
                applyOffset();
            }

            window.requestAnimationFrame(tick);
        }

        shell.addEventListener("mouseenter", () => {
            hoverPaused = true;
        });

        shell.addEventListener("mouseleave", () => {
            hoverPaused = false;
        });

        scrubber.addEventListener("pointerdown", () => {
            dragging = true;
        });

        scrubber.addEventListener("pointerup", () => {
            dragging = false;
        });

        scrubber.addEventListener("input", (event) => {
            dragging = true;
            offset = Number(event.target.value || 0);
            applyOffset();
        });

        scrubber.addEventListener("change", () => {
            dragging = false;
        });

        window.addEventListener("resize", () => {
            measureTrack();
            applyOffset();
        });

        measureTrack();
        applyOffset();
        window.requestAnimationFrame(tick);
        </script>
    </body>
    </html>
    """
    components.html(
        ticker_component_html,
        height=126,
        scrolling=False,
    )

search_submitted = False
with st.container():
    launches_col, center_col, flows_col = st.columns([1.05, 1.8, 1.05], gap="large")

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

    with flows_col:
        st.markdown('<div class="etf-section-title">Fund Flows</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">ETFdb issuer power rankings sorted by fund flows.</div>',
            unsafe_allow_html=True,
        )
        if fund_flow_items:
            flows_container = st.container(height=760)
            for item in fund_flow_items[:250]:
                issuer_title = escape(item.get("issuer", "Issuer"))
                issuer_link = escape(item.get("link", ""))
                issuer_markup = (
                    f'<a class="etf-news-title" href="{issuer_link}" target="_blank">{issuer_title}</a>'
                    if issuer_link else f'<div class="etf-news-title">{issuer_title}</div>'
                )
                flows_container.markdown(
                    f"""
                    <div class="etf-news-item">
                        <div class="etf-news-source">Rank {escape(str(item.get("rank", "")))}</div>
                        {issuer_markup}
                        <div class="etf-news-meta">3M Fund Flow: {escape(str(item.get("flow", "")))}</div>
                        <div class="etf-news-kicker">Listed ETFs: {escape(str(item.get("etf_count", "")))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("ETFdb fund flow rankings were not available right now.")
