"""HCP Terraform API client."""

import logging
import random
import time
from datetime import datetime

import requests

from .config import (
    BASE_URL,
    PAGE_SIZE,
    RATE_LIMIT_DELAY,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_FACTOR,
    RETRY_BACKOFF_MAX,
    RETRY_JITTER_MAX,
    RETRY_MAX_ATTEMPTS,
)

logger = logging.getLogger(__name__)


def _compute_backoff(
    attempt: int,
    base: float,
    factor: float,
    max_delay: float,
    jitter_max: float,
) -> float:
    computed = min(factor * (base**attempt), max_delay)
    return computed + random.uniform(0, jitter_max)


class TFCClient:
    def __init__(
        self,
        token: str,
        org: str,
        *,
        rate_limit_delay: float = RATE_LIMIT_DELAY,
        max_retries: int = RETRY_MAX_ATTEMPTS,
        backoff_base: float = RETRY_BACKOFF_BASE,
        backoff_factor: float = RETRY_BACKOFF_FACTOR,
        backoff_max: float = RETRY_BACKOFF_MAX,
        jitter_max: float = RETRY_JITTER_MAX,
    ) -> None:
        self.org = org
        self._rate_limit_delay = rate_limit_delay
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_factor = backoff_factor
        self._backoff_max = backoff_max
        self._jitter_max = jitter_max
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.api+json",
            }
        )
        self._req_count = 0

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{BASE_URL}{path}"
        attempt = 0
        resp = None
        while attempt < self._max_retries:
            self._req_count += 1
            time.sleep(self._rate_limit_delay)
            resp = self._session.get(url, params=params)

            if resp.status_code == 429:
                wait = float(
                    resp.headers.get("Retry-After")
                    or _compute_backoff(
                        attempt,
                        self._backoff_base,
                        self._backoff_factor,
                        self._backoff_max,
                        self._jitter_max,
                    )
                )
                logger.warning(
                    "rate-limited (429); waiting %.1fs (attempt %d/%d)",
                    wait,
                    attempt + 1,
                    self._max_retries,
                )
                time.sleep(wait)
                attempt += 1
                continue

            if resp.status_code >= 500:
                wait = _compute_backoff(
                    attempt,
                    self._backoff_base,
                    self._backoff_factor,
                    self._backoff_max,
                    self._jitter_max,
                )
                logger.warning(
                    "server error %d; retrying in %.1fs (attempt %d/%d)",
                    resp.status_code,
                    wait,
                    attempt + 1,
                    self._max_retries,
                )
                time.sleep(wait)
                attempt += 1
                continue

            resp.raise_for_status()
            return resp.json()

        resp.raise_for_status()

    def _paginate(self, path: str, params: dict = None, max_pages: int = 50) -> list:
        params = params or {}
        params["page[size]"] = PAGE_SIZE
        params["page[number]"] = 1
        all_data = []
        pages = 0
        while pages < max_pages:
            result = self._get(path, params)
            all_data.extend(result.get("data", []))
            meta = result.get("meta", {}).get("pagination", {})
            pages += 1
            if meta.get("next-page"):
                params["page[number]"] = meta["next-page"]
            else:
                break
        return all_data

    def list_workspaces(self) -> list:
        return self._paginate(f"/organizations/{self.org}/workspaces")

    def list_projects(self) -> list:
        return self._paginate(f"/organizations/{self.org}/projects")

    def list_workspace_resources(self, ws_id: str) -> list:
        """Fetch all managed resources for a workspace (the RUM source)."""
        return self._paginate(f"/workspaces/{ws_id}/resources")

    def get_workspace_resource_count(self, ws_id: str) -> int:
        """Quick count without fetching all resources."""
        try:
            result = self._get(f"/workspaces/{ws_id}/resources", {"page[size]": 1})
            return result.get("meta", {}).get("pagination", {}).get("total-count", 0)
        except Exception:
            return 0

    def list_workspace_runs(self, ws_id: str, since: datetime) -> list:
        """Fetch runs for a workspace, stopping at the cutoff date."""
        params = {"page[size]": PAGE_SIZE, "page[number]": 1}
        all_runs = []
        while True:
            result = self._get(f"/workspaces/{ws_id}/runs", params)
            data = result.get("data", [])
            if not data:
                break
            stop = False
            for run in data:
                created = run["attributes"].get("created-at", "")
                if created:
                    try:
                        run_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        if run_dt < since:
                            stop = True
                            break
                    except ValueError:
                        pass
                all_runs.append(run)
            meta = result.get("meta", {}).get("pagination", {})
            if stop or not meta.get("next-page"):
                break
            params["page[number]"] = meta["next-page"]
        return all_runs

    def list_state_versions(self, ws_id: str, limit: int = 10) -> list:
        """Fetch recent state versions to track RUM growth over time."""
        return self._paginate(
            f"/workspaces/{ws_id}/state-versions",
            params={"page[size]": min(limit, PAGE_SIZE)},
            max_pages=1,
        )

    @property
    def request_count(self) -> int:
        return self._req_count
