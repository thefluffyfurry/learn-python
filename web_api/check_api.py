"""Small helper to verify a deployed PyQuest API is desktop-app friendly."""

from __future__ import annotations

import json
import sys
from urllib import error, request


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python web_api/check_api.py <api-base-url>")
        print("Example: python web_api/check_api.py https://your-project.supabase.co/functions/v1/pyquest-api")
        return 1

    base_url = sys.argv[1].rstrip("/")
    url = f"{base_url}/health"
    req = request.Request(url, headers={"Accept": "application/json"})

    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Request failed: HTTP {exc.code}")
        if body:
            print(f"Body: {body[:400]}")
        return 1
    except error.URLError as exc:
        print(f"Request failed: {exc}")
        return 1

    print(f"URL: {url}")
    print(f"Content-Type: {content_type}")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        snippet = body[:200].replace("\n", " ")
        print(f"Not JSON. First 200 chars: {snippet}")
        return 2

    print(f"JSON: {payload}")
    if payload.get("status") != "ok":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
