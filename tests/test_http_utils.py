import unittest
from unittest.mock import patch

import requests

import http_utils


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}",
                response=self,
            )


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, _url, timeout):
        self.calls += 1
        return self.responses.pop(0)


class SecRateLimiterTests(unittest.TestCase):
    def test_shared_interval_limits_requests_to_eight_per_second(self):
        with patch.object(http_utils, "_NEXT_SEC_REQUEST_AT", 0.0), patch(
            "http_utils.time.monotonic",
            side_effect=[10.0, 10.0],
        ), patch("http_utils.time.sleep") as sleep:
            http_utils._wait_for_sec_request_slot()
            http_utils._wait_for_sec_request_slot()

        sleep.assert_called_once_with(http_utils.SEC_REQUEST_INTERVAL)
        self.assertEqual(http_utils.SEC_REQUEST_INTERVAL, 0.125)

    def test_retryable_response_honors_retry_after(self):
        session = FakeSession(
            [
                FakeResponse(429, headers={"Retry-After": "86400"}),
                FakeResponse(200, text="ok"),
            ]
        )
        with patch("http_utils.get_http_session", return_value=session), patch(
            "http_utils._wait_for_sec_request_slot"
        ), patch("http_utils.time.sleep") as sleep:
            text = http_utils.get_response_text(
                "https://www.sec.gov/example",
                max_chars=10,
            )

        self.assertEqual(text, "ok")
        self.assertEqual(session.calls, 2)
        sleep.assert_called_once_with(http_utils.MAX_RETRY_AFTER_SECONDS)

    def test_final_403_is_raised_instead_of_returning_empty_text(self):
        session = FakeSession([FakeResponse(403), FakeResponse(403), FakeResponse(403)])
        with patch("http_utils.get_http_session", return_value=session), patch(
            "http_utils._wait_for_sec_request_slot"
        ), patch("http_utils.time.sleep"):
            with self.assertRaises(requests.HTTPError):
                http_utils.get_response_text(
                    "https://www.sec.gov/example",
                    max_chars=10,
                )

        self.assertEqual(session.calls, 3)


if __name__ == "__main__":
    unittest.main()
