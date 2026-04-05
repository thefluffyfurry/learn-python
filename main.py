"""Entry point for the Python teaching app."""

from __future__ import annotations

import traceback
import tkinter as tk
from tkinter import messagebox

from app.client import run_client
from app.server import TeachingServer
from app.settings import get_api_url, should_start_local_server


def _show_fatal_error(title: str, detail: str) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, detail)
        root.destroy()
    except tk.TclError:
        # Tk may be unavailable in some terminal-only environments.
        print(f"{title}: {detail}")


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
        run_client(api_url)
    except Exception as exc:
        traceback.print_exc()
        _show_fatal_error("PyQuest Academy", str(exc))
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    main()
