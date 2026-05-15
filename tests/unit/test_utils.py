import pytest
import requests
import responses

from src.pipeline.utils import retry_with_policy, setup_logging


@pytest.fixture
def retry_policy():
    return {
        "attempts": 3,
        "per_request_timeout_s": 1,
        "max_total_duration_s": 5,
        "base_delay_ms": 10,
        "multiplier": 2.0,
        "jitter_factor": 0.0,
    }


def test_retry_success(retry_policy):
    @retry_with_policy(retry_policy)
    def success_func(**kwargs):
        return "success"

    assert success_func() == "success"


@responses.activate
def test_retry_on_5xx(retry_policy):
    url = "http://example.com"
    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, status=200, body="ok")

    @retry_with_policy(retry_policy)
    def failing_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    assert failing_func() == "ok"
    assert len(responses.calls) == 3


@responses.activate
def test_non_retryable_404(retry_policy):
    url = "http://example.com"
    responses.add(responses.GET, url, status=404)

    @retry_with_policy(retry_policy)
    def failing_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        failing_func()

    assert excinfo.value.response.status_code == 404
    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize("status_code", [400, 401, 403])
def test_non_retryable_errors(retry_policy, status_code):
    url = "http://example.com"
    responses.add(responses.GET, url, status=status_code)

    @retry_with_policy(retry_policy)
    def failing_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        failing_func()

    assert excinfo.value.response.status_code == status_code
    assert len(responses.calls) == 1


@responses.activate
def test_retry_hard_cap(retry_policy):
    # Set a very low hard cap
    retry_policy["max_total_duration_s"] = 0.1
    retry_policy["base_delay_ms"] = 200  # Delay longer than hard cap

    url = "http://example.com"
    responses.add(responses.GET, url, status=500)
    responses.add(responses.GET, url, status=500)

    @retry_with_policy(retry_policy)
    def failing_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    with pytest.raises(requests.exceptions.HTTPError):
        failing_func()

    # Should only try once because next retry would exceed hard cap
    assert len(responses.calls) == 1


@responses.activate
def test_retry_429_with_retry_after(retry_policy):
    """Test that 429 with Retry-After header is respected."""
    retry_policy["base_delay_ms"] = 10  # Ensure backoff is small
    url = "http://example.com"
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "0.01"})
    responses.add(responses.GET, url, status=200, body="ok")

    @retry_with_policy(retry_policy)
    def rate_limited_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    assert rate_limited_func() == "ok"
    assert len(responses.calls) == 2


@responses.activate
def test_retry_429_without_retry_after(retry_policy):
    """Test that 429 without Retry-After uses standard backoff."""
    retry_policy["base_delay_ms"] = 10
    url = "http://example.com"
    responses.add(responses.GET, url, status=429)
    responses.add(responses.GET, url, status=200, body="ok")

    @retry_with_policy(retry_policy)
    def rate_limited_func(**kwargs):
        resp = requests.get(url, **kwargs)
        resp.raise_for_status()
        return resp.text

    assert rate_limited_func() == "ok"
    assert len(responses.calls) == 2


def test_retry_connection_error(retry_policy):
    """Test retry on connection errors."""
    retry_policy["base_delay_ms"] = 10
    call_count = 0

    @retry_with_policy(retry_policy)
    def conn_error_func(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise requests.exceptions.ConnectionError("Connection refused")
        return "ok"

    assert conn_error_func() == "ok"
    assert call_count == 3


def test_retry_timeout_error(retry_policy):
    """Test retry on timeout errors."""
    retry_policy["base_delay_ms"] = 10
    call_count = 0

    @retry_with_policy(retry_policy)
    def timeout_func(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise requests.exceptions.Timeout("Request timed out")
        return "ok"

    assert timeout_func() == "ok"
    assert call_count == 2


def test_retry_unexpected_error(retry_policy):
    """Test that unexpected errors are not retried."""

    @retry_with_policy(retry_policy)
    def error_func(**kwargs):
        raise ValueError("unexpected")

    with pytest.raises(ValueError, match="unexpected"):
        error_func()


def test_retry_with_on_retry_callback(retry_policy):
    """Test custom on_retry callback."""
    retry_policy["base_delay_ms"] = 10
    callback_calls = []

    def on_retry(attempt, elapsed, delay, status_code, error):
        callback_calls.append((attempt, status_code))

    call_count = 0

    @retry_with_policy(retry_policy, on_retry=on_retry)
    def func_with_callback(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            resp = requests.models.Response()
            resp.status_code = 500
            raise requests.exceptions.HTTPError(response=resp)
        return "ok"

    assert func_with_callback() == "ok"
    assert len(callback_calls) == 1
    assert callback_calls[0] == (1, 500)


def test_retry_exhausts_all_attempts(retry_policy):
    """Test that all attempts are exhausted before raising."""
    retry_policy["attempts"] = 2
    retry_policy["base_delay_ms"] = 10
    call_count = 0

    @retry_with_policy(retry_policy)
    def always_fail(**kwargs):
        nonlocal call_count
        call_count += 1
        resp = requests.models.Response()
        resp.status_code = 500
        raise requests.exceptions.HTTPError(response=resp)

    with pytest.raises(requests.exceptions.HTTPError):
        always_fail()

    assert call_count == retry_policy["attempts"]


def test_setup_logging():
    """Test setup_logging doesn't crash."""
    setup_logging()
