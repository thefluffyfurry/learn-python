"""Print hosted admin activity for PyQuest Academy."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable
from urllib import error, parse, request

from app.settings import get_api_url


def fetch_activity(base_url: str, admin_key: str, limit: int = 25) -> Dict[str, Any]:
    query = parse.urlencode({"limit": limit})
    url = f"{base_url.rstrip('/')}/admin/activity?{query}"
    req = request.Request(
        url,
        headers={
            "X-Admin-Key": admin_key,
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{exc.code} {body}") from exc


def print_rows(title: str, rows: Iterable[Dict[str, Any]], fields: list[str]) -> None:
    print(title)
    print("-" * len(title))
    row_list = list(rows)
    if not row_list:
        print("No rows.\n")
        return

    for row in row_list:
        parts = []
        for field in fields:
            value = row.get(field, "")
            parts.append(f"{field}={value}")
        print(" | ".join(parts))
    print()


def main() -> None:
    admin_key = os.environ.get("PYQUEST_ADMIN_KEY", "").strip()
    if not admin_key:
        raise RuntimeError("Set PYQUEST_ADMIN_KEY before running this script.")

    payload = fetch_activity(get_api_url(), admin_key)
    print_rows(
        "Active Clients",
        payload.get("active_clients", []),
        ["session_name", "username", "client_type", "app_version", "ip_address", "ip_country", "last_event", "last_seen_at"],
    )
    print_rows(
        "Recent Logins",
        payload.get("recent_logins", []),
        ["created_at", "event_type", "username", "session_name", "client_type", "app_version", "ip_address", "ip_country"],
    )
    print_rows(
        "Recent Activity",
        payload.get("recent_activity", []),
        ["created_at", "event_type", "username", "request_path", "session_name", "app_version", "ip_address"],
    )


if __name__ == "__main__":
    main()
