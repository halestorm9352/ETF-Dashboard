import importlib

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from html import escape

try:
    from config import (
        classify_flow_group,
        CIK_GROUP_LOOKUP,
        CIK_GROUP_OPTIONS,
        DATA_VERSION,
        FLOW_VIEW_OPTIONS,
    )
except ImportError:
    from config import (
        CIK_GROUP_LOOKUP,
        CIK_GROUP_OPTIONS,
        DATA_VERSION,
        infer_cik_group_name,
    )

    FLOW_VIEW_OPTIONS = ("All", "Top 3", "The Field", "Series Trusts")
    _TOP_FLOW_GROUPS = {"BlackRock", "SPDR", "Vanguard"}
    _SERIES_TRUST_FLOW_GROUPS = {
        "EA Series Trust",
        "ETF Architect",
        "ETF Opportunities Trust",
        "ETF Series Solutions",
        "Exchange Traded Concepts Trust",
        "Financial Investors Trust",
        "Investment Managers Series Trust",
        "Northern Lights",
        "TIDAL",
    }

    def classify_flow_group(group_name):
        if group_name in _TOP_FLOW_GROUPS:
            return "Top 3"
        if group_name in _SERIES_TRUST_FLOW_GROUPS:
            return "Series Trusts"
        return "The Field"

import sec_parsers as sec_parsers_module

if not hasattr(sec_parsers_module, "extract_rule_485_effectiveness"):
    sec_parsers_module = importlib.reload(sec_parsers_module)

import sec_filings as sec_filings_module

if not all(
    hasattr(sec_filings_module, name)
    for name in ("derive_latest_fund_rows", "fetch_filing_events")
):
    sec_filings_module = importlib.reload(sec_filings_module)

derive_latest_fund_rows = sec_filings_module.derive_latest_fund_rows
fetch_filing_events = sec_filings_module.fetch_filing_events
sanitize_ticker = sec_parsers_module.sanitize_ticker
from theme_classifier import THEME_ORDER, classify_primary_theme, summarize_themes


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
        animation: etfTickerMove 900s linear infinite;
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

    .etf-theme-strip {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
        gap: 0.75rem;
        margin: 0.2rem 0 1rem;
    }

    .etf-theme-card {
        border: 1px solid var(--etf-border);
        background: rgba(18, 23, 34, 0.74);
        border-radius: 16px;
        padding: 0.8rem 0.9rem;
    }

    .etf-theme-label {
        color: var(--etf-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.62rem;
        margin-bottom: 0.25rem;
    }

    .etf-theme-value {
        font-size: 1.35rem;
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

    .etf-status-line {
        font-size: 0.86rem;
        margin-top: -0.15rem;
        margin-bottom: 0.8rem;
    }

    .etf-status-live {
        color: var(--etf-accent);
    }

    .etf-status-fallback {
        color: #d8b44a;
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

    div[data-testid="stFormSubmitButton"] > button {
        width: 100%;
        min-height: 3.15rem;
        white-space: nowrap;
        background: #000000 !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        border-radius: 14px !important;
    }

    div[data-testid="stFormSubmitButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] > button:focus {
        background: #111111 !important;
        color: #ffffff !important;
        border-color: rgba(255, 255, 255, 0.28) !important;
    }

    div[data-testid="stDownloadButton"] > button {
        min-height: 2.85rem;
        white-space: nowrap;
        background: #000000 !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        border-radius: 14px !important;
        padding: 0.2rem 1rem !important;
        font-weight: 700 !important;
    }

    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:focus {
        background: #111111 !important;
        color: #ffffff !important;
        border-color: rgba(255, 255, 255, 0.28) !important;
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
def load_filing_events(data_version, refresh_token, start_date, end_date, selected_ciks):
    return fetch_filing_events(start_date, end_date, ciks=selected_ciks)


def _issuer_groups_for_segment(segment):
    if segment == "All":
        return list(CIK_GROUP_OPTIONS)
    return [
        group_name
        for group_name in CIK_GROUP_OPTIONS
        if classify_flow_group(group_name) == segment
    ]


def _classify_filing_stage(form):
    form_value = str(form or "").upper()
    if form_value in {"S-1", "N-1A"}:
        return "Initial filing"
    if form_value == "485APOS":
        return "Rule 485(a) amendment"
    if form_value == "485BPOS":
        return "Rule 485(b) amendment"
    return "Filing"


def _earliest_auto_effective_date(row):
    filing_date = row.get("date")
    if pd.isna(filing_date):
        return pd.NaT

    designated_date = str(row.get("designated_effective_date", "") or "").strip()
    if designated_date:
        parsed_date = pd.to_datetime(designated_date, errors="coerce")
        if not pd.isna(parsed_date):
            return parsed_date

    effectiveness_days = row.get("effectiveness_days")
    parsed_days = pd.to_numeric(effectiveness_days, errors="coerce")
    if not pd.isna(parsed_days):
        return filing_date + pd.Timedelta(days=int(parsed_days))
    return pd.NaT


def _readiness_status(row, today):
    ticker = sanitize_ticker(row.get("ticker", ""))
    readiness_date = row.get("earliest_auto_effective_date")
    form_value = str(row.get("form", "")).upper()

    if form_value in {"S-1", "N-1A"}:
        return "Initial review"
    if pd.isna(readiness_date):
        return "Timing not detected"
    if ticker == "Not Listed":
        return "Needs ticker"
    if readiness_date.date() <= today:
        return "Launch candidate"
    return "Waiting on effectiveness"


def _add_launch_readiness_columns(df):
    enriched_df = df.copy()
    today = datetime.today().date()
    enriched_df["filing_stage"] = enriched_df["form"].apply(_classify_filing_stage)
    enriched_df["earliest_auto_effective_date"] = enriched_df.apply(_earliest_auto_effective_date, axis=1)
    enriched_df["launch_readiness"] = enriched_df.apply(lambda row: _readiness_status(row, today), axis=1)
    enriched_df["days_to_readiness"] = enriched_df["earliest_auto_effective_date"].apply(
        lambda value: "" if pd.isna(value) else (value.date() - today).days
    )
    return enriched_df


default_end = datetime.today().date()
year_start = datetime(default_end.year, 1, 1).date()
default_start = max(year_start, default_end - timedelta(days=14))
if "search_start_date" not in st.session_state:
    st.session_state.search_start_date = default_start
if "search_end_date" not in st.session_state:
    st.session_state.search_end_date = default_end
if "search_issuer_segment" not in st.session_state:
    st.session_state.search_issuer_segment = "All"
if st.session_state.search_issuer_segment not in FLOW_VIEW_OPTIONS:
    st.session_state.search_issuer_segment = "All"
if "search_issuer_groups" not in st.session_state:
    st.session_state.search_issuer_groups = []
if "search_refresh_token" not in st.session_state:
    st.session_state.search_refresh_token = 0
if "search_requested" not in st.session_state:
    st.session_state.search_requested = False
st.markdown(
    """
    <div class="etf-brand">ETF Dash</div>
    <div class="etf-tagline">Tracking ETF registration filing activity.</div>
    """,
    unsafe_allow_html=True,
)

news_items = []

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
                <div class="etf-ticker-track" id="ticker-track">""" + ticker_items_html + """</div>
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
        const originalMarkup = track.innerHTML;

        if (originalMarkup) {
            track.innerHTML = originalMarkup + originalMarkup;
        }

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
                const pixelsPerMs = singleWidth / 900000;
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
    center_col = st.container()

    with center_col:
        st.markdown('<div class="etf-section-title">Filings</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Search SEC filings by date range, with the newest filings displayed first.</div>',
            unsafe_allow_html=True,
        )
        issuer_group_options = _issuer_groups_for_segment(st.session_state.search_issuer_segment)
        st.session_state.search_issuer_groups = [
            group_name
            for group_name in st.session_state.search_issuer_groups
            if group_name in issuer_group_options
        ]
        with st.form("date_filter_form"):
            filter_cols = st.columns([0.95, 1.35, 0.8, 0.8, 0.65])
            filter_cols[0].selectbox(
                "Segment",
                options=FLOW_VIEW_OPTIONS,
                key="search_issuer_segment",
                help="Filter SEC filing searches by broad issuer buckets.",
            )
            filter_cols[1].multiselect(
                "Issuers",
                options=issuer_group_options,
                key="search_issuer_groups",
                help="Choose one or more issuer groups inside the selected segment.",
            )
            filter_cols[2].date_input(
                "Start date",
                min_value=year_start,
                max_value=default_end,
                key="search_start_date",
                format="MM/DD/YYYY",
            )
            filter_cols[3].date_input(
                "End date",
                min_value=year_start,
                max_value=default_end,
                key="search_end_date",
                format="MM/DD/YYYY",
            )
            search_submitted = filter_cols[4].form_submit_button("Search", use_container_width=True)
        st.caption("Leave issuers blank to search all issuers in the selected segment.")

        if search_submitted:
            if st.session_state.search_start_date < year_start:
                st.session_state.search_start_date = year_start
            if st.session_state.search_end_date < year_start:
                st.session_state.search_end_date = year_start
            st.session_state.search_requested = True
            st.session_state.search_refresh_token += 1

        if not st.session_state.search_requested:
            st.info("Choose a date range and click Search to run the SEC scrape.")
        elif st.session_state.search_start_date > st.session_state.search_end_date:
            st.warning("Start date must be on or before end date.")
        else:
            selected_group_names = st.session_state.search_issuer_groups or []
            selected_ciks = []
            seen_selected_ciks = set()
            segment_group_names = _issuer_groups_for_segment(st.session_state.search_issuer_segment)
            groups_to_search = selected_group_names or segment_group_names
            for group_name in groups_to_search:
                for cik in CIK_GROUP_LOOKUP.get(group_name, []):
                    if cik not in seen_selected_ciks:
                        seen_selected_ciks.add(cik)
                        selected_ciks.append(cik)
            selected_ciks = tuple(sorted(seen_selected_ciks))

            try:
                with st.spinner("Searching SEC filings for the selected date range..."):
                    filing_events = load_filing_events(
                        DATA_VERSION,
                        st.session_state.search_refresh_token,
                        st.session_state.search_start_date,
                        st.session_state.search_end_date,
                        selected_ciks,
                    )
            except Exception as exc:
                st.error(
                    "The app could not load fresh SEC filing data right now. "
                    "Please try again in a minute."
                )
                st.caption(f"Temporary data source issue: {type(exc).__name__}")
            else:
                event_df = pd.DataFrame(filing_events)
                snapshot_df = pd.DataFrame(derive_latest_fund_rows(filing_events))
                df = snapshot_df
                if not df.empty:
                    required_columns = [
                        "ticker",
                        "ticker_at_filing",
                        "etf_name",
                        "filer",
                        "form",
                        "date",
                        "accepted_at",
                        "link",
                        "accession_number",
                        "effectiveness_basis",
                        "effectiveness_days",
                        "designated_effective_date",
                        "effectiveness_label",
                        "event_id",
                    ]
                    for column in required_columns:
                        if column not in df.columns:
                            df[column] = ""
                        if column not in event_df.columns:
                            event_df[column] = ""

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
                    filtered_df["themes"] = filtered_df["etf_name"].apply(classify_primary_theme)
                    filtered_df = _add_launch_readiness_columns(filtered_df)

                    event_df["date"] = pd.to_datetime(event_df["date"], errors="coerce")
                    event_df = event_df.dropna(subset=["date"]).copy()
                    event_df["ticker"] = event_df["ticker"].apply(sanitize_ticker)
                    event_df["ticker_at_filing"] = event_df["ticker_at_filing"].apply(sanitize_ticker)
                    event_df["themes"] = event_df["etf_name"].apply(classify_primary_theme)
                    event_df = _add_launch_readiness_columns(event_df)
                    event_df = event_df.sort_values(
                        by=["date", "accepted_at", "link", "ticker", "etf_name"],
                        ascending=[False, False, True, True, True],
                        kind="stable",
                    )

                    display_df = filtered_df.copy()
                    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
                    display_df["earliest_auto_effective_date"] = display_df[
                        "earliest_auto_effective_date"
                    ].dt.strftime("%Y-%m-%d")
                    display_df["earliest_auto_effective_date"] = display_df[
                        "earliest_auto_effective_date"
                    ].fillna("")
                    event_display_df = event_df.copy()
                    event_display_df["date"] = event_display_df["date"].dt.strftime("%Y-%m-%d")
                    event_display_df["earliest_auto_effective_date"] = event_display_df[
                        "earliest_auto_effective_date"
                    ].dt.strftime("%Y-%m-%d")
                    event_display_df["earliest_auto_effective_date"] = event_display_df[
                        "earliest_auto_effective_date"
                    ].fillna("")
                    filings_count = len(display_df)
                    filing_event_count = len(event_display_df)
                    listed_tickers = int((filtered_df["ticker"] != "Not Listed").sum())
                    distinct_filers = int(filtered_df["filer"].nunique())
                    launch_candidates = int((filtered_df["launch_readiness"] == "Launch candidate").sum())
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
                        f'<div class="etf-card"><div class="etf-card-label">Launch Candidates</div><div class="etf-card-value">{launch_candidates}</div></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"Latest filing: {latest_date}. Snapshot contains {filings_count} funds derived from "
                        f"{filing_event_count} filing events. Readiness timing follows the checked Rule 485 "
                        "option in each filing when detected."
                    )

                    theme_counts = summarize_themes(filtered_df["etf_name"])
                    theme_cards = "".join(
                        f"""
                        <div class="etf-theme-card">
                            <div class="etf-theme-label">{escape(theme)}</div>
                            <div class="etf-theme-value">{theme_counts.get(theme, 0)}</div>
                        </div>
                        """
                        for theme in THEME_ORDER
                    )
                    st.markdown(
                        f"""
                        <div class="etf-section-copy">Top filing themes from ETF names.</div>
                        <div class="etf-theme-strip">{theme_cards}</div>
                        """,
                        unsafe_allow_html=True,
                    )

                    export_columns = [
                        "ticker",
                        "etf_name",
                        "themes",
                        "filer",
                        "form",
                        "filing_stage",
                        "date",
                        "effectiveness_label",
                        "earliest_auto_effective_date",
                        "days_to_readiness",
                        "launch_readiness",
                        "link",
                    ]
                    export_df = display_df[export_columns].copy()
                    launch_candidate_df = export_df[
                        export_df["launch_readiness"] == "Launch candidate"
                    ].copy()
                    amendment_df = export_df[
                        export_df["form"].isin(["485APOS", "485BPOS"])
                    ].copy()
                    event_export_columns = [
                        "event_id",
                        "accession_number",
                        "ticker_at_filing",
                        "ticker",
                        "etf_name",
                        "themes",
                        "filer",
                        "form",
                        "filing_stage",
                        "date",
                        "effectiveness_label",
                        "earliest_auto_effective_date",
                        "days_to_readiness",
                        "launch_readiness",
                        "link",
                    ]
                    event_export_df = event_display_df[event_export_columns].copy()
                    export_file_prefix = (
                        f"etf_dash_filings_"
                        f"{st.session_state.search_start_date.isoformat()}_to_"
                        f"{st.session_state.search_end_date.isoformat()}"
                    )

                    description_cols = st.columns(4)
                    description_cols[0].caption(
                        "One latest row per ETF in the selected period."
                    )
                    description_cols[1].caption(
                        "Snapshot funds with a ticker whose detected effective date has arrived."
                    )
                    description_cols[2].caption(
                        "Latest snapshot rows filed as 485APOS or 485BPOS amendments."
                    )
                    description_cols[3].caption(
                        "Every filing occurrence, including repeated amendments for the same fund."
                    )
                    export_cols = st.columns(4)
                    export_cols[0].download_button(
                        "Latest snapshot",
                        data=export_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"{export_file_prefix}.csv",
                        mime="text/csv",
                        key="download_filings_csv",
                        use_container_width=True,
                    )
                    export_cols[1].download_button(
                        "Launch candidates",
                        data=launch_candidate_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"{export_file_prefix}_launch_candidates.csv",
                        mime="text/csv",
                        key="download_launch_candidates_csv",
                        use_container_width=True,
                    )
                    export_cols[2].download_button(
                        "Amendments",
                        data=amendment_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"{export_file_prefix}_amendments.csv",
                        mime="text/csv",
                        key="download_amendments_csv",
                        use_container_width=True,
                    )
                    export_cols[3].download_button(
                        "Filing events",
                        data=event_export_df.to_csv(index=False).encode("utf-8"),
                        file_name=f"{export_file_prefix}_filing_events.csv",
                        mime="text/csv",
                        key="download_filing_events_csv",
                        use_container_width=True,
                    )

                    st.success(
                        f"Loaded {filings_count} latest fund snapshot row(s) from "
                        f"{filing_event_count} filing event(s)."
                    )
                    snapshot_tab, events_tab = st.tabs(["Latest snapshot", "Filing events"])
                    with snapshot_tab:
                        st.caption(
                            "Current view: one row per ETF, using its most recent filing in the selected period."
                        )
                        st.dataframe(
                            export_df,
                            use_container_width=True,
                            hide_index=True,
                        )
                    with events_tab:
                        st.caption(
                            "History view: every filing event is retained, so the same ETF may appear more than once."
                        )
                        st.dataframe(
                            event_export_df,
                            use_container_width=True,
                            hide_index=True,
                        )
                else:
                    st.warning("No recent filings were loaded right now. The SEC may be rate-limiting some requests, so please try again shortly.")

