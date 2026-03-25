import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from edgar_cik import fetch_filings

st.set_page_config(page_title="ProShares ETF Filings", layout="wide")

st.title("ProShares ETF Filings")
st.write("S-1, N-1A, 485BPOS")

refresh_minutes = st.sidebar.selectbox(
    "Check for new filings every",
    options=[1, 5, 10, 30],
    index=1
)


@st.cache_data(ttl=60)
def load_filings():
    return fetch_filings()


def enable_auto_refresh(interval_minutes):
    interval_ms = interval_minutes * 60 * 1000
    components.html(
        f"""
        <script>
            setTimeout(function() {{
                window.parent.location.reload();
            }}, {interval_ms});
        </script>
        """,
        height=0,
    )


enable_auto_refresh(refresh_minutes)

st.caption(
    f"This page automatically refreshes every {refresh_minutes} minute(s) to look for new SEC filings."
)

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
        st.dataframe(df, use_container_width=True)

        for _, row in df.iterrows():
            st.markdown(f"### {row['etf_name']}")
            st.markdown(f"**Strategy:** {row['strategy']}")
            st.markdown(f"**Form:** {row['form']} | **Date:** {row['date']}")
            st.markdown(f"[View Filing]({row['link']})")
            st.markdown("---")
    else:
        st.info("No recent filings were found in the current search window.")
