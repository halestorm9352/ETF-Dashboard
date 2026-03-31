import time

import requests
import streamlit as st

from config import HEADERS


@st.cache_resource
def get_http_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_response_text(url, max_chars, retries=3):
    session = get_http_session()
    for attempt in range(retries):
        try:
            response = session.get(url, timeout=20)
            response.raise_for_status()
            return response.text[:max_chars]
        except requests.RequestException:
            if attempt == retries - 1:
                return ""
            time.sleep(1.0 + attempt)
