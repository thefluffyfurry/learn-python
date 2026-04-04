"""Entry point for the Python teaching app."""

from __future__ import annotations

from app.client import run_client
from app.server import TeachingServer
from app.settings import get_api_url, should_start_local_server


def main() -> None:
    api_url = get_api_url()
    server: TeachingServer | None = None
    if should_start_local_server(api_url):
        server = TeachingServer()
        server.start_in_background()
    try:
        run_client(api_url)
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    main()
