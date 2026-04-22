import threading
import time

import requests

from config import HEADERS

_THREAD_LOCAL = threading.local()


def get_http_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _THREAD_LOCAL.session = session
    return session


def get_response_text(url: str, max_chars: int, retries: int = 3) -> str:
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
