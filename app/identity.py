"""Stable client identity metadata for hosted telemetry."""

from __future__ import annotations

import json
import re
import secrets
import socket
from pathlib import Path
from typing import Any, Dict

from app.runtime import app_root


IDENTITY_PATH = app_root() / "client_identity.json"


def _safe_host_label() -> str:
    host = socket.gethostname().strip() or "device"
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", host).strip("-_.")
    return normalized or "device"


def _default_session_name(client_type: str) -> str:
    return f"{client_type}-{_safe_host_label()}"


def _load_identity_blob(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get_client_identity(client_type: str) -> Dict[str, str]:
    path = IDENTITY_PATH
    blob = _load_identity_blob(path)
    raw_entry = blob.get(client_type)
    entry = raw_entry if isinstance(raw_entry, dict) else {}

    install_id = str(entry.get("install_id") or "").strip()
    session_name = str(entry.get("session_name") or "").strip()
    changed = False

    if not install_id:
        install_id = secrets.token_hex(12)
        changed = True
    if not session_name:
        session_name = _default_session_name(client_type)
        changed = True

    if changed:
        blob[client_type] = {
            "install_id": install_id,
            "session_name": session_name,
        }
        try:
            path.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        except OSError:
            pass

    return {
        "install_id": install_id,
        "session_name": session_name,
    }
