"""Unified resilient HTTP client for GasBrazil data pipelines.

Provides session pooling, exponential backoff, retry on transient errors (429, 5xx),
standard User-Agent identification, and atomic streaming file downloads.
"""
from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

DEFAULT_USER_AGENT = "GasBrazil/1.0 (+https://gasbrazil.com; open data pipeline)"
DEFAULT_TIMEOUT = 60

logger = logging.getLogger("gasbrazil.http")


def make_session(
    *,
    total_retries: int = 4,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    user_agent: str = DEFAULT_USER_AGENT,
    headers: Mapping[str, str] | None = None,
) -> requests.Session:
    """Create a configured requests.Session with connection pooling and standard retry/backoff."""
    session = requests.Session()
    retry_strategy = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "POST", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": user_agent})
    if headers:
        session.headers.update(headers)
    return session


def fetch_url(
    url: str,
    *,
    method: str = "GET",
    params: Mapping[str, Any] | None = None,
    data: Any = None,
    json_data: Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session: requests.Session | None = None,
) -> requests.Response:
    """Execute an HTTP request with retry, backoff, and standard error handling."""
    s = session or make_session()
    resp = s.request(
        method=method,
        url=url,
        params=params,
        data=data,
        json=json_data,
        headers=headers,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp


def download_file(
    url: str,
    dest: Path | str,
    *,
    chunk_size: int = 64 * 1024,
    timeout: int = 120,
    session: requests.Session | None = None,
) -> Path:
    """Stream a remote URL to a local destination file atomically."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".download.tmp")

    s = session or make_session()
    with s.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(resp.raw, f, length=chunk_size)

    os.replace(tmp_path, dest_path)
    return dest_path
