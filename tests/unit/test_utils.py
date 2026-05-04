import pytest
import requests
import responses
from src.pipeline.utils import retry_with_policy

@pytest.fixture
def retry_policy():
    return {
        "attempts": 3,
        "per_request_timeout_s": 1,
        "max_total_duration_s": 5,
        "base_delay_ms": 10,
        "multiplier": 2.0,
        "jitter_factor": 0.0
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
def test_retry_hard_cap(retry_policy):
    # Set a very low hard cap
    retry_policy["max_total_duration_s"] = 0.1
    retry_policy["base_delay_ms"] = 200 # Delay longer than hard cap
    
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
