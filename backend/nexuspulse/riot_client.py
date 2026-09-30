"""Riot Games API client with multi-window rate limiting, 429 handling and exponential backoff."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from urllib.parse import quote

import httpx

from .config import settings

log = logging.getLogger(__name__)

# Match-id / platform prefix -> regional routing value (Account-v1 and Match-v5 are regional).
PLATFORM_TO_REGION = {
    "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe", "ME1": "europe",
    "NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea", "PH2": "sea", "SG2": "sea", "TH2": "sea", "TW2": "sea", "VN2": "sea",
}


class RiotApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Riot API {status}: {message}")
        self.status = status


class RateLimiter:
    """Sliding-window limiter enforcing several (max_requests, window_seconds) windows at once."""

    def __init__(self, limits: tuple[tuple[int, float], ...]):
        self._limits = limits
        self._stamps: list[deque[float]] = [deque() for _ in limits]
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def block_for(self, seconds: float) -> None:
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                wait = max(0.0, self._blocked_until - now)
                for (max_req, window), stamps in zip(self._limits, self._stamps):
                    while stamps and now - stamps[0] >= window:
                        stamps.popleft()
                    if len(stamps) >= max_req:
                        wait = max(wait, window - (now - stamps[0]) + 0.01)
                if wait <= 0:
                    for stamps in self._stamps:
                        stamps.append(now)
                    return
            time.sleep(min(wait, 5.0))


def region_for_match(match_id: str) -> str:
    prefix = match_id.split("_", 1)[0].upper()
    return PLATFORM_TO_REGION.get(prefix, "europe")


def region_for_platform(platform: str) -> str:
    return PLATFORM_TO_REGION.get(platform.upper(), "europe")


class RiotClient:
    def __init__(
        self,
        api_key: str | None = None,
        platform: str | None = None,
        limiter: RateLimiter | None = None,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.riot_api_key
        self.platform = (platform or settings.riot_platform).lower()
        self.limiter = limiter or RateLimiter(settings.rate_limits)
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=20.0, transport=transport)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, host: str, path: str, params: dict | None = None) -> dict | list:
        if not self.api_key:
            raise RiotApiError(401, "RIOT_API_KEY is not configured")
        url = f"https://{host}.api.riotgames.com{path}"
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                resp = self._http.get(url, params=params, headers={"X-Riot-Token": self.api_key})
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise RiotApiError(0, f"network error: {exc}") from exc
                self._backoff(attempt)
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                log.warning("429 from Riot, backing off %.1fs", retry_after)
                self.limiter.block_for(retry_after)
                continue
            if resp.status_code >= 500 and attempt < self.max_retries:
                self._backoff(attempt)
                continue
            raise RiotApiError(resp.status_code, resp.text[:200])
        raise RiotApiError(429, "retries exhausted")

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(60.0, (2 ** attempt) + random.uniform(0, 1)))

    # --- Account-v1 / Summoner-v4 -------------------------------------------------------
    def get_account_by_riot_id(self, game_name: str, tag_line: str) -> dict:
        region = region_for_platform(self.platform)
        return self._get(
            region,
            f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}",
        )

    def get_summoner_by_puuid(self, puuid: str) -> dict:
        return self._get(self.platform, f"/lol/summoner/v4/summoners/by-puuid/{puuid}")

    # --- League-v4 (apex seeds for high-tier training data) --------------------------------
    def get_apex_league(self, tier: str = "challenger", queue: str = "RANKED_SOLO_5x5") -> dict:
        return self._get(self.platform, f"/lol/league/v4/{tier.lower()}leagues/by-queue/{queue}")

    # --- Match-v5 ------------------------------------------------------------------------
    def get_match_ids(self, puuid: str, count: int = 20, queue: int | None = 420, start: int = 0) -> list:
        params: dict = {"start": start, "count": max(1, min(count, 100))}
        if queue is not None:
            params["queue"] = queue
        region = region_for_platform(self.platform)
        return self._get(region, f"/lol/match/v5/matches/by-puuid/{puuid}/ids", params)

    def get_match(self, match_id: str) -> dict:
        return self._get(region_for_match(match_id), f"/lol/match/v5/matches/{match_id}")

    def get_timeline(self, match_id: str) -> dict:
        return self._get(region_for_match(match_id), f"/lol/match/v5/matches/{match_id}/timeline")

    def close(self) -> None:
        self._http.close()
