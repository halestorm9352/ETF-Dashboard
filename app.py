import streamlit as st
import pandas as pd
from edgar_cik import fetch_filings

st.set_page_config(page_title="ProShares ETF Filings", layout="wide")

st.title("ProShares ETF Filings")
st.write("S-1, N-1A, 485BPOS")

data = fetch_filings()
df = pd.DataFrame(data)

if not df.empty:
    df = df.sort_values(by="date", ascending=False)

    st.dataframe(df, use_container_width=True)

    for _, row in df.iterrows():
        st.markdown(f"### {row['etf_name']}")
        st.markdown(f"**Strategy:** {row['strategy']}")
        st.markdown(f"**Form:** {row['form']} | **Date:** {row['date']}")
        st.markdown(f"[View Filing]({row['link']})")
        st.markdown("---")

else:
    st.write("Nothing here kemosabe")