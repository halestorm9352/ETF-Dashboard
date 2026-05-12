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
        ETFCOM_DATA_VERSION,
        FLOW_VIEW_OPTIONS,
        FUND_FLOWS_PAGE_SIZE,
        LAUNCHES_PAGE_SIZE,
        normalize_flow_issuer_group,
    )
except ImportError:
    from config import (
        CIK_GROUP_LOOKUP,
        CIK_GROUP_OPTIONS,
        DATA_VERSION,
        ETFCOM_DATA_VERSION,
        FUND_FLOWS_PAGE_SIZE,
        infer_cik_group_name,
        LAUNCHES_PAGE_SIZE,
    )

    FLOW_VIEW_OPTIONS = ("All", "Top 3", "The Field", "Series Trusts")
    _TOP_FLOW_GROUPS = {"BlackRock", "SPDR", "Vanguard"}
    _SERIES_TRUST_FLOW_GROUPS = {
        "EA Series Trust",
        "ETF Opportunities",
        "ETF Series Solutions",
        "Exchange Traded Concepts",
        "Financial Investors Trust",
        "Investment Managers Series",
        "Northern Lights",
        "Tidal",
    }

    def normalize_flow_issuer_group(name):
        if not name:
            return "Issuer"
        return infer_cik_group_name(name)

    def classify_flow_group(group_name):
        if group_name in _TOP_FLOW_GROUPS:
            return "Top 3"
        if group_name in _SERIES_TRUST_FLOW_GROUPS:
            return "Series Trusts"
        return "The Field"
try:
    from etfcom import (
        fetch_etf_news,
        fetch_scheduled_etfcom_launches_with_status,
        fetch_etfdb_fund_flows,
    )
except ImportError:
    from etfcom import fetch_etf_news

    def fetch_etfdb_fund_flows(limit=100):
        return []

    def fetch_scheduled_etfcom_launches_with_status(limit=100):
        return {"items": [], "status": "Unavailable"}
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
def load_filings(_data_version, start_date, end_date, selected_ciks):
    return fetch_filings(start_date, end_date, ciks=selected_ciks)


@st.cache_data(ttl=3600)
def load_etfcom_news(_version):
    return fetch_etf_news(limit=600)


def load_etfcom_launches(_version):
    return fetch_scheduled_etfcom_launches_with_status(limit=1000)


@st.cache_data(ttl=43200)
def load_etfdb_fund_flows(_version):
    return fetch_etfdb_fund_flows(limit=250)


FLOW_FACTOR_OPTIONS = ("Flows", "AUM")


def _render_launch_cards(items):
    return "".join(
        f"""
        <div class="etf-news-item">
            <div class="etf-news-source">{escape(item.get("date", ""))}</div>
            <a class="etf-news-title" href="{escape(item.get("link", "#"))}" target="_blank">{escape(item.get("ticker", ""))}</a>
            <div class="etf-news-kicker">{escape(item.get("fund_name", ""))}</div>
        </div>
        """
        for item in items
    )


def _render_fund_flow_cards(items, factor="Flows"):
    rendered_items = []
    for item in items:
        issuer_title = escape(item.get("issuer", "Issuer"))
        issuer_link = escape(item.get("link", ""))
        flow_category = escape(item.get("flow_category", "All"))
        rank_value = item.get("aum_rank") if factor == "AUM" else item.get("rank", "")
        rank = escape(str(rank_value))
        issuer_markup = (
            f'<a class="etf-news-title" href="{issuer_link}" target="_blank">{issuer_title}</a>'
            if issuer_link else f'<div class="etf-news-title">{issuer_title}</div>'
        )
        meta_label = "AUM" if factor == "AUM" else "3M Fund Flow"
        meta_value = escape(str(item.get("aum", "N/A"))) if factor == "AUM" else escape(str(item.get("flow", "")))
        rendered_items.append(
            f"""
            <div class="etf-news-item">
                <div class="etf-news-source">{flow_category} | Rank {rank}</div>
                {issuer_markup}
                <div class="etf-news-meta">{meta_label}: {meta_value}</div>
                <div class="etf-news-kicker">Listed ETFs: {escape(str(item.get("etf_count", "")))}</div>
            </div>
            """
        )
    return "".join(rendered_items)


def _sort_fund_flow_items(items, factor):
    ranked_items = list(items)
    if factor == "AUM":
        ranked_items.sort(
            key=lambda item: (
                item.get("aum_rank") is None,
                item.get("aum_rank", 10**9),
                item.get("issuer", ""),
            )
        )
    else:
        ranked_items.sort(key=lambda item: (item.get("rank", 10**9), item.get("issuer", "")))
    return ranked_items


def _prepare_fund_flow_items(items):
    prepared_items = []
    for item in items:
        issuer_group = normalize_flow_issuer_group(item.get("issuer", ""))
        prepared_items.append(
            {
                **item,
                "issuer_group": issuer_group,
                "flow_category": classify_flow_group(issuer_group),
            }
        )
    return prepared_items


default_end = datetime.today().date()
year_start = datetime(default_end.year, 1, 1).date()
default_start = max(year_start, default_end - timedelta(days=14))
if "search_start_date" not in st.session_state:
    st.session_state.search_start_date = default_start
if "search_end_date" not in st.session_state:
    st.session_state.search_end_date = default_end
if "search_issuer_groups" not in st.session_state:
    st.session_state.search_issuer_groups = []
if "search_requested" not in st.session_state:
    st.session_state.search_requested = False
if "launches_visible_count" not in st.session_state:
    st.session_state.launches_visible_count = LAUNCHES_PAGE_SIZE
if "fund_flows_visible_count" not in st.session_state:
    st.session_state.fund_flows_visible_count = FUND_FLOWS_PAGE_SIZE
if "fund_flow_view" not in st.session_state:
    st.session_state.fund_flow_view = "All"
if "fund_flow_factor" not in st.session_state:
    st.session_state.fund_flow_factor = "Flows"

st.markdown(
    """
    <div class="etf-brand">ETF Dash</div>
    <div class="etf-tagline">Tracking new ETF launches, registration filings, and the surrounding market conversation.</div>
    """,
    unsafe_allow_html=True,
)

news_items = load_etfcom_news(ETFCOM_DATA_VERSION)
fund_flow_items = _prepare_fund_flow_items(load_etfdb_fund_flows(ETFCOM_DATA_VERSION))

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
        launches_payload = load_etfcom_launches(ETFCOM_DATA_VERSION)
        launches_items = launches_payload.get("items", []) if isinstance(launches_payload, dict) else launches_payload
        launches_metadata = launches_payload.get("metadata", {}) if isinstance(launches_payload, dict) else {}
        refreshed_display = launches_metadata.get("refreshed_display", "")
        if refreshed_display:
            st.caption(f"Updated: {refreshed_display}")
        if launches_items:
            launches_container = st.container(height=760)
            visible_launch_count = min(st.session_state.launches_visible_count, len(launches_items))
            launches_container.markdown(
                _render_launch_cards(launches_items[:visible_launch_count]),
                unsafe_allow_html=True,
            )
            launch_controls = st.columns(2)
            if visible_launch_count < len(launches_items):
                if launch_controls[0].button(
                    f"Load {LAUNCHES_PAGE_SIZE} more",
                    key="launches_load_more",
                    use_container_width=True,
                ):
                    st.session_state.launches_visible_count += LAUNCHES_PAGE_SIZE
            elif visible_launch_count > LAUNCHES_PAGE_SIZE:
                if launch_controls[0].button(
                    "Show fewer",
                    key="launches_show_fewer",
                    use_container_width=True,
                ):
                    st.session_state.launches_visible_count = LAUNCHES_PAGE_SIZE
        else:
            st.caption("ETF.com launches were not available right now.")

    with center_col:
        st.markdown('<div class="etf-section-title">Filings</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="etf-section-copy">Search SEC filings by date range, with the newest filings displayed first.</div>',
            unsafe_allow_html=True,
        )
        with st.form("date_filter_form"):
            filter_cols = st.columns([1.45, 0.82, 0.82, 0.5])
            filter_cols[0].multiselect(
                "Issuer groups",
                options=CIK_GROUP_OPTIONS,
                key="search_issuer_groups",
                help="Choose one or more issuer groups. Leave blank to search all configured groups.",
            )
            filter_cols[1].date_input("Start date", min_value=year_start, max_value=default_end, key="search_start_date")
            filter_cols[2].date_input("End date", min_value=year_start, max_value=default_end, key="search_end_date")
            search_submitted = filter_cols[3].form_submit_button("Search")
        st.caption("Leave issuer groups blank to search all configured issuers.")

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
            selected_group_names = st.session_state.search_issuer_groups or []
            selected_ciks = []
            seen_selected_ciks = set()
            groups_to_search = selected_group_names or CIK_GROUP_OPTIONS
            for group_name in groups_to_search:
                for cik in CIK_GROUP_LOOKUP.get(group_name, []):
                    if cik not in seen_selected_ciks:
                        seen_selected_ciks.add(cik)
                        selected_ciks.append(cik)
            selected_ciks = tuple(sorted(seen_selected_ciks))

            try:
                with st.spinner("Searching SEC filings for the selected date range..."):
                    data = load_filings(
                        DATA_VERSION,
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

                    export_df = display_df[["ticker", "etf_name", "filer", "date", "link"]].copy()
                    export_csv = export_df.to_csv(index=False).encode("utf-8")
                    export_file_name = (
                        f"etf_dash_filings_"
                        f"{st.session_state.search_start_date.isoformat()}_to_"
                        f"{st.session_state.search_end_date.isoformat()}.csv"
                    )

                    export_cols = st.columns([1, 1.15, 1])
                    export_cols[1].download_button(
                        "Download",
                        data=export_csv,
                        file_name=export_file_name,
                        mime="text/csv",
                        key="download_filings_csv",
                        use_container_width=True,
                    )

                    st.success(f"Loaded {filings_count} filing(s) in the selected date range.")
                    st.dataframe(
                        export_df,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("No recent filings were loaded right now. The SEC may be rate-limiting some requests, so please try again shortly.")

    with flows_col:
        st.markdown('<div class="etf-section-title">Issuer Pulse</div>', unsafe_allow_html=True)
        flow_view = st.radio(
            "Fund flow view",
            FLOW_VIEW_OPTIONS,
            horizontal=True,
            key="fund_flow_view",
            label_visibility="collapsed",
        )
        flow_factor = st.radio(
            "Fund flow factor",
            FLOW_FACTOR_OPTIONS,
            horizontal=True,
            key="fund_flow_factor",
            label_visibility="collapsed",
        )

        filtered_fund_flow_items = (
            fund_flow_items
            if flow_view == "All"
            else [item for item in fund_flow_items if item.get("flow_category") == flow_view]
        )
        filtered_fund_flow_items = _sort_fund_flow_items(filtered_fund_flow_items, flow_factor)

        if filtered_fund_flow_items:
            flows_container = st.container(height=760)
            visible_flow_count = min(st.session_state.fund_flows_visible_count, len(filtered_fund_flow_items))
            flows_container.markdown(
                _render_fund_flow_cards(filtered_fund_flow_items[:visible_flow_count], factor=flow_factor),
                unsafe_allow_html=True,
            )
            flow_controls = st.columns(2)
            if visible_flow_count < len(filtered_fund_flow_items):
                if flow_controls[0].button(
                    f"Load {FUND_FLOWS_PAGE_SIZE} more",
                    key="fund_flows_load_more",
                    use_container_width=True,
                ):
                    st.session_state.fund_flows_visible_count += FUND_FLOWS_PAGE_SIZE
            elif visible_flow_count > FUND_FLOWS_PAGE_SIZE:
                if flow_controls[0].button(
                    "Show fewer",
                    key="fund_flows_show_fewer",
                    use_container_width=True,
                ):
                    st.session_state.fund_flows_visible_count = FUND_FLOWS_PAGE_SIZE
        else:
            st.caption("No issuer rows matched that flow view right now.")
