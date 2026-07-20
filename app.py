import importlib
from io import BytesIO

import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from config import (
    classify_flow_group,
    CIK_GROUP_LOOKUP,
    CIK_GROUP_OPTIONS,
    DATA_VERSION,
    FLOW_VIEW_OPTIONS,
)


EXPECTED_MODULE_CONTRACT_VERSION = 11


def _require_current_module_contract(module):
    if getattr(module, "MODULE_CONTRACT_VERSION", None) != EXPECTED_MODULE_CONTRACT_VERSION:
        module = importlib.reload(module)
    if getattr(module, "MODULE_CONTRACT_VERSION", None) != EXPECTED_MODULE_CONTRACT_VERSION:
        st.error("Deployed modules are out of sync; reboot the app.")
        st.stop()
    return module

import sec_parsers as sec_parsers_module

sec_parsers_module = _require_current_module_contract(sec_parsers_module)

import sec_filings as sec_filings_module

sec_filings_module = _require_current_module_contract(sec_filings_module)

derive_latest_fund_rows = sec_filings_module.derive_latest_fund_rows
fetch_filing_events = sec_filings_module.fetch_filing_events
normalize_event_ticker = sec_filings_module.normalize_event_ticker
from theme_classifier import THEME_ORDER, classify_primary_theme, summarize_themes
from readiness import add_launch_readiness_columns


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
    event_results = fetch_filing_events(start_date, end_date, ciks=selected_ciks)
    return (
        list(event_results),
        list(event_results.statuses),
        dict(event_results.mapping_status),
        datetime.now(timezone.utc),
    )


def _issuer_groups_for_segment(segment):
    if segment == "All":
        return list(CIK_GROUP_OPTIONS)
    return [
        group_name
        for group_name in CIK_GROUP_OPTIONS
        if classify_flow_group(group_name) == segment
    ]


def _latest_snapshot_workbook(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Latest Snapshot")
        worksheet = writer.sheets["Latest Snapshot"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(
                max(max_length + 2, 12),
                48,
            )
    return output.getvalue()


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
if "search_force_refresh" not in st.session_state:
    st.session_state.search_force_refresh = False


def _submit_filing_search():
    if st.session_state.search_start_date < year_start:
        st.session_state.search_start_date = year_start
    if st.session_state.search_end_date < year_start:
        st.session_state.search_end_date = year_start
    st.session_state.search_requested = True
    if st.session_state.search_force_refresh:
        st.session_state.search_refresh_token += 1
    st.session_state.search_force_refresh = False


st.markdown(
    """
    <div class="etf-brand">ETF Dash</div>
    <div class="etf-tagline">A live snapshot of ETF registration activity from SEC filings.</div>
    """,
    unsafe_allow_html=True,
)

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
            filter_cols = st.columns([0.9, 1.3, 0.75, 0.75, 0.7, 0.55])
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
            filter_cols[4].checkbox(
                "Force refresh",
                key="search_force_refresh",
                help="Bypass the 30-minute cache for this search only.",
            )
            filter_cols[5].form_submit_button(
                "Search",
                use_container_width=True,
                on_click=_submit_filing_search,
            )
        st.caption("Leave issuers blank to search all issuers in the selected segment.")

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
                    (
                        filing_events,
                        filing_statuses,
                        mapping_status,
                        fetched_at,
                    ) = load_filing_events(
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
                failed_statuses = [
                    status for status in filing_statuses if not status.get("success", False)
                ]
                succeeded_count = len(filing_statuses) - len(failed_statuses)
                st.caption(
                    f"Searched {len(filing_statuses)} filers; {succeeded_count} succeeded, "
                    f"{len(failed_statuses)} failed."
                )
                if failed_statuses:
                    failed_filers = ", ".join(
                        sorted(
                            {
                                str(status.get("filer") or status.get("cik") or "Unknown")
                                for status in failed_statuses
                            }
                        )
                    )
                    st.warning(f"Partial SEC coverage. Failed filers: {failed_filers}.")
                if not mapping_status.get("available", False):
                    st.caption(
                        "SEC ticker mapping unavailable; tickers may be incomplete."
                    )

                snapshot_df = pd.DataFrame(derive_latest_fund_rows(filing_events))
                df = snapshot_df
                if not df.empty:
                    required_columns = [
                        "ticker",
                        "ticker_at_filing",
                        "ticker_source",
                        "etf_name",
                        "class_name",
                        "series_id",
                        "series_name",
                        "class_id",
                        "vehicle",
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
                        "filing_event_count",
                        "amendment_count",
                        "filing_form_history",
                    ]
                    for column in required_columns:
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
                    filtered_df["ticker"] = filtered_df.apply(
                        lambda row: normalize_event_ticker(row.to_dict()),
                        axis=1,
                    )
                    filtered_df["themes"] = filtered_df["etf_name"].apply(classify_primary_theme)
                    filtered_df = add_launch_readiness_columns(filtered_df)
                    if filtered_df.empty:
                        st.info("No filing snapshot rows matched the selected date range.")

                    display_df = filtered_df.copy()
                    if display_df.empty:
                        display_df["date"] = pd.Series(dtype="object")
                        display_df["earliest_auto_effective_date"] = pd.Series(
                            dtype="object"
                        )
                    else:
                        display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
                        display_df["earliest_auto_effective_date"] = display_df[
                            "earliest_auto_effective_date"
                        ].dt.strftime("%Y-%m-%d")
                    display_df["earliest_auto_effective_date"] = display_df[
                        "earliest_auto_effective_date"
                    ].fillna("")
                    filings_count = len(display_df)
                    filing_event_count = len(filing_events)
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
                        f'<div class="etf-card"><div class="etf-card-label">Funds Loaded</div><div class="etf-card-value">{filings_count}</div></div>',
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
                        f"Latest filing: {latest_date}. Snapshot contains {filings_count} fund or series rows derived from "
                        f"{filing_event_count} filing events. Readiness timing follows the checked Rule 485 "
                        "option in each filing when detected."
                    )
                    fetched_at_utc = (
                        fetched_at
                        if fetched_at.tzinfo is not None
                        else fetched_at.replace(tzinfo=timezone.utc)
                    )
                    fetched_at_et = fetched_at_utc.astimezone(
                        ZoneInfo("America/New_York")
                    )
                    st.caption(
                        f"Data as of {fetched_at_et.strftime('%I:%M %p').lstrip('0')} ET "
                        "(cached up to 30 min; use Force refresh for live data)."
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
                        <div class="etf-section-copy">Top filing themes from classified fund names.</div>
                        <div class="etf-theme-strip">{theme_cards}</div>
                        """,
                        unsafe_allow_html=True,
                    )

                    export_columns = [
                        "ticker",
                        "etf_name",
                        "class_name",
                        "vehicle",
                        "series_id",
                        "class_id",
                        "themes",
                        "filer",
                        "form",
                        "filing_stage",
                        "filing_event_count",
                        "amendment_count",
                        "filing_form_history",
                        "date",
                        "effectiveness_label",
                        "earliest_auto_effective_date",
                        "days_to_readiness",
                        "launch_readiness",
                        "link",
                    ]
                    export_df = display_df[export_columns].copy()
                    export_file_prefix = (
                        f"etf_dash_latest_snapshot_"
                        f"{st.session_state.search_start_date.isoformat()}_to_"
                        f"{st.session_state.search_end_date.isoformat()}"
                    )

                    export_cols = st.columns([1.2, 2.8])
                    export_cols[0].download_button(
                        "Download latest snapshot",
                        data=_latest_snapshot_workbook(export_df),
                        file_name=f"{export_file_prefix}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="download_latest_snapshot_xlsx",
                        use_container_width=True,
                    )
                    export_cols[1].caption(
                        "One latest row per fund or parent series. Vehicle, amendment counts, and filing-form history are included."
                    )

                    result_message = (
                        f"Loaded {filings_count} latest fund snapshot row(s) from "
                        f"{filing_event_count} filing event(s)."
                    )
                    if failed_statuses:
                        st.info(f"{result_message} Results are incomplete because some filers failed.")
                    else:
                        st.success(result_message)
                    st.caption(
                        "Latest snapshot: one row per fund or parent series, using its most recent filing in the selected period."
                    )
                    st.dataframe(
                        export_df,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.warning("No recent filings were loaded right now. The SEC may be rate-limiting some requests, so please try again shortly.")

