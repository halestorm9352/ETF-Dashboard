import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from config import HEADERS

_THREAD_LOCAL = threading.local()
_SEC_RATE_LOCK = threading.Lock()
_NEXT_SEC_REQUEST_AT = 0.0
SEC_REQUESTS_PER_SECOND = 8.0
SEC_REQUEST_INTERVAL = 1.0 / SEC_REQUESTS_PER_SECOND
RETRYABLE_STATUS_CODES = {403, 429}
MAX_RETRY_AFTER_SECONDS = 30.0


def get_http_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _THREAD_LOCAL.session = session
    return session


def _is_sec_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "sec.gov" or hostname.endswith(".sec.gov")


def _wait_for_sec_request_slot() -> None:
    global _NEXT_SEC_REQUEST_AT
    with _SEC_RATE_LOCK:
        now = time.monotonic()
        wait_seconds = max(0.0, _NEXT_SEC_REQUEST_AT - now)
        if wait_seconds:
            time.sleep(wait_seconds)
        _NEXT_SEC_REQUEST_AT = max(now, _NEXT_SEC_REQUEST_AT) + SEC_REQUEST_INTERVAL


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = str(response.headers.get("Retry-After", "") or "").strip()
    if retry_after:
        try:
            delay = max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                delay = max(
                    0.0,
                    (retry_at - datetime.now(timezone.utc)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                pass
            else:
                return min(delay, MAX_RETRY_AFTER_SECONDS)
        else:
            return min(delay, MAX_RETRY_AFTER_SECONDS)
    return 1.0 + attempt


def get_response(
    url: str,
    retries: int = 3,
    timeout: int = 20,
) -> requests.Response:
    session = get_http_session()
    last_error: requests.RequestException | None = None
    for attempt in range(retries):
        if _is_sec_url(url):
            _wait_for_sec_request_slot()
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == retries - 1:
                    response.raise_for_status()
                time.sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries - 1:
                raise
            time.sleep(1.0 + attempt)

    if last_error:
        raise last_error
    raise requests.RequestException("HTTP request failed without a response")


def get_response_text(url: str, max_chars: int, retries: int = 3) -> str:
    try:
        response = get_response(url, retries=retries)
        return response.text[:max_chars]
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in RETRYABLE_STATUS_CODES:
            raise
        return ""
    except requests.RequestException:
        return ""
