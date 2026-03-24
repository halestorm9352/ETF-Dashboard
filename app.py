import streamlit as st
import pandas as pd
from edgar_cik import fetch_filings_by_cik

st.title("ETF Dashboard")

filings = fetch_filings_by_cik()
df = pd.DataFrame(filings)

st.write(df)