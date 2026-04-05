"""Console entry point for PyQuest Academy."""

from __future__ import annotations

import traceback

from app.console_client import run_console_client
from app.server import TeachingServer
from app.settings import get_api_url, should_start_local_server
from app.version import APP_NAME


def _start_local_server(api_url: str) -> TeachingServer | None:
    try:
        server = TeachingServer()
        server.start_in_background()
        return server
    except OSError as exc:
        if should_start_local_server(api_url):
            raise RuntimeError(
                "The local teaching server could not start. "
                "Make sure no other app is already using http://127.0.0.1:8123."
            ) from exc
        return None


def main() -> None:
    api_url = get_api_url()
    server: TeachingServer | None = None
    try:
        server = _start_local_server(api_url)
        run_console_client(api_url)
    except KeyboardInterrupt:
        print(f"\n{APP_NAME}: closing.")
    except Exception as exc:
        traceback.print_exc()
        print(f"{APP_NAME}: {exc}")
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    main()
