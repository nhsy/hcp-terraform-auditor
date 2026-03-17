"""Tests for TFCClient and _compute_backoff."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from hcp_tf_audit.client import TFCClient, _compute_backoff


def _make_client(**kwargs) -> TFCClient:
    defaults = dict(
        rate_limit_delay=0.0,
        max_retries=5,
        backoff_base=2.0,
        backoff_factor=1.0,
        backoff_max=60.0,
        jitter_max=0.0,
    )
    defaults.update(kwargs)
    return TFCClient("fake-token", "fake-org", **defaults)


def _mock_response(status_code: int, json_data: dict = None, headers: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_data or {"data": []}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestComputeBackoff(unittest.TestCase):
    def test_table(self):
        cases = [
            # attempt, base, factor, max_delay, jitter_max, jitter_return, expected
            (0, 2.0, 1.0, 60.0, 2.0, 0.5, 1.5),
            (1, 2.0, 1.0, 60.0, 2.0, 0.5, 2.5),
            (3, 2.0, 1.0, 60.0, 2.0, 0.5, 8.5),
            (10, 2.0, 1.0, 60.0, 2.0, 0.5, 60.5),
        ]
        for attempt, base, factor, max_delay, jitter_max, jitter_return, expected in cases:
            with self.subTest(attempt=attempt):
                with patch("hcp_tf_audit.client.random.uniform", return_value=jitter_return):
                    result = _compute_backoff(attempt, base, factor, max_delay, jitter_max)
                    self.assertAlmostEqual(result, expected)


class TestTFCClientGet(unittest.TestCase):
    def test_success_first_attempt(self):
        client = _make_client()
        ok = _mock_response(200, {"data": [{"id": "ws-1"}]})
        with patch.object(client._session, "get", return_value=ok):
            with patch("hcp_tf_audit.client.time.sleep"):
                result = client._get("/test")
        self.assertEqual(result, {"data": [{"id": "ws-1"}]})
        self.assertEqual(client.request_count, 1)

    def test_429_with_retry_after(self):
        client = _make_client()
        throttled = _mock_response(429, headers={"Retry-After": "5"})
        ok = _mock_response(200, {"data": []})
        with patch.object(client._session, "get", side_effect=[throttled, ok]):
            with patch("hcp_tf_audit.client.time.sleep") as mock_sleep:
                client._get("/test")
        # sleep calls: rate_limit_delay (0.0) x2, then Retry-After wait of 5.0
        sleep_values = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertIn(5.0, sleep_values)

    def test_429_without_retry_after_uses_backoff(self):
        client = _make_client(jitter_max=0.0)
        throttled = _mock_response(429)
        ok = _mock_response(200, {"data": []})
        with patch.object(client._session, "get", side_effect=[throttled, ok]):
            with patch("hcp_tf_audit.client.time.sleep") as mock_sleep:
                client._get("/test")
        # backoff for attempt=0, factor=1.0, base=2.0 -> 1.0, jitter=0 -> 1.0
        sleep_values = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertIn(1.0, sleep_values)

    def test_429_exhausts_retries_raises(self):
        client = _make_client(max_retries=3)
        throttled = _mock_response(429)
        with patch.object(client._session, "get", return_value=throttled):
            with patch("hcp_tf_audit.client.time.sleep"):
                with self.assertRaises(requests.HTTPError):
                    client._get("/test")

    def test_5xx_retried_then_succeeds(self):
        client = _make_client()
        err = _mock_response(503)
        ok = _mock_response(200, {"data": []})
        with patch.object(client._session, "get", side_effect=[err, ok]):
            with patch("hcp_tf_audit.client.time.sleep"):
                client._get("/test")
        self.assertEqual(client.request_count, 2)

    def test_5xx_exhausts_retries_raises(self):
        client = _make_client(max_retries=3)
        err = _mock_response(500)
        with patch.object(client._session, "get", return_value=err):
            with patch("hcp_tf_audit.client.time.sleep"):
                with self.assertRaises(requests.HTTPError):
                    client._get("/test")

    def test_4xx_not_retried(self):
        client = _make_client()
        forbidden = _mock_response(403)
        with patch.object(client._session, "get", return_value=forbidden):
            with patch("hcp_tf_audit.client.time.sleep"):
                with self.assertRaises(requests.HTTPError):
                    client._get("/test")
        self.assertEqual(client.request_count, 1)

    def test_retry_count_includes_all_attempts(self):
        client = _make_client()
        err = _mock_response(503)
        ok = _mock_response(200, {"data": []})
        with patch.object(client._session, "get", side_effect=[err, err, ok]):
            with patch("hcp_tf_audit.client.time.sleep"):
                client._get("/test")
        self.assertEqual(client.request_count, 3)
