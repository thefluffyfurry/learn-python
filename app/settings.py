"""Runtime configuration for local and hosted API modes."""

from __future__ import annotations

import os


LOCAL_API_URL = "http://127.0.0.1:8123"
HOSTED_API_URL = "http://pyquest-academy.free.nf/api"


def get_api_url() -> str:
    return os.environ.get("PYQUEST_API_URL", LOCAL_API_URL).rstrip("/")


def should_start_local_server(api_url: str) -> bool:
    normalized = api_url.lower()
    return normalized.startswith("http://127.0.0.1") or normalized.startswith("http://localhost")
