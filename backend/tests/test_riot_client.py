import time

import httpx
import pytest

from nexuspulse.riot_client import RateLimiter, RiotApiError, RiotClient, region_for_match


def test_rate_limiter_enforces_window():
    limiter = RateLimiter(((3, 0.5),))
    start = time.monotonic()
    for _ in range(4):
        limiter.acquire()
    assert time.monotonic() - start >= 0.45  # 4th request had to wait for the window


def test_region_routing():
    assert region_for_match("EUW1_123") == "europe"
    assert region_for_match("NA1_123") == "americas"
    assert region_for_match("KR_123") == "asia"


def _client(handler):
    return RiotClient(api_key="test", platform="euw1", limiter=RateLimiter(((100, 1.0),)),
                      max_retries=3, transport=httpx.MockTransport(handler))


def test_retries_after_429_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        assert request.headers["X-Riot-Token"] == "test"
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(200, json={"metadata": {"matchId": "EUW1_1"}})

    assert _client(handler).get_match("EUW1_1")["metadata"]["matchId"] == "EUW1_1"
    assert calls["n"] == 2


def test_404_raises_without_retry():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, text="not found")

    with pytest.raises(RiotApiError) as err:
        _client(handler).get_match("EUW1_1")
    assert err.value.status == 404 and calls["n"] == 1


def test_missing_key_is_refused():
    with pytest.raises(RiotApiError):
        RiotClient(api_key="").get_match("EUW1_1")
