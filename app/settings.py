"""Runtime configuration for local and hosted API modes."""

from __future__ import annotations

import os


LOCAL_API_URL = "http://127.0.0.1:8123"
HOSTED_API_URL = "https://keyquuyuamfuvotaruod.supabase.co/functions/v1/pyquest-api"
GITHUB_UPDATE_REPO = "thefluffyfurry/learn-python"
GITHUB_UPDATE_ASSET_NAME = "PyQuestAcademy.exe"
GITHUB_UPDATE_ZIP_ASSET_NAME = "PyQuestAcademy.zip"


def get_api_url() -> str:
    env_url = os.environ.get("PYQUEST_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    hosted_url = HOSTED_API_URL.strip().rstrip("/")
    if hosted_url:
        return hosted_url

    return LOCAL_API_URL


def should_start_local_server(api_url: str) -> bool:
    normalized = api_url.lower()
    return normalized.startswith("http://127.0.0.1") or normalized.startswith("http://localhost")
