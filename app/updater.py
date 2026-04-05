"""Simple Windows self-update support for the packaged desktop app."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from app.version import APP_VERSION


@dataclass(slots=True)
class UpdateInfo:
    version: str
    download_url: str
    notes: str = ""


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            parts.append(0)
            continue
        parts.append(int(digits))
    return tuple(parts)


def can_self_update() -> bool:
    return os.name == "nt" and getattr(sys, "frozen", False)


def fetch_update(manifest_url: str) -> UpdateInfo | None:
    manifest_url = manifest_url.strip()
    if not manifest_url:
        return None

    req = request.Request(
        manifest_url,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "PyQuestAcademyUpdater"},
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            payload = response.read().decode("utf-8")
    except error.URLError as exc:
        raise RuntimeError(f"Cannot reach the update server at {manifest_url}.") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The update manifest is not valid JSON.") from exc

    version = str(data.get("version", "")).strip()
    download_url = str(data.get("download_url", "")).strip()
    notes = str(data.get("notes", "")).strip()
    if not version or not download_url:
        raise RuntimeError("The update manifest must include version and download_url.")

    if _version_key(version) <= _version_key(APP_VERSION):
        return None
    return UpdateInfo(version=version, download_url=download_url, notes=notes)


def stage_update(update: UpdateInfo) -> None:
    if not can_self_update():
        raise RuntimeError("Self-update only works from the packaged Windows app.")

    current_exe = Path(sys.executable).resolve()
    pending_exe = current_exe.with_name(f"{current_exe.stem}-{update.version}.pending.exe")
    updater_script = current_exe.with_name("apply_update.bat")

    req = request.Request(update.download_url, headers={"User-Agent": "PyQuestAcademyUpdater"})
    try:
        with request.urlopen(req, timeout=30) as response, pending_exe.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                handle.write(chunk)
    except error.URLError as exc:
        if pending_exe.exists():
            pending_exe.unlink(missing_ok=True)
        raise RuntimeError(f"Cannot download the new version from {update.download_url}.") from exc

    if not pending_exe.exists() or pending_exe.stat().st_size == 0:
        pending_exe.unlink(missing_ok=True)
        raise RuntimeError("The downloaded update file was empty.")

    updater_script.write_text(
        "\n".join(
            [
                "@echo off",
                "setlocal",
                f'set "CURRENT_EXE={current_exe}"',
                f'set "PENDING_EXE={pending_exe}"',
                ":retry",
                'copy /Y "%PENDING_EXE%" "%CURRENT_EXE%" >nul',
                "if errorlevel 1 (",
                "  timeout /t 1 /nobreak >nul",
                "  goto retry",
                ")",
                'del /Q "%PENDING_EXE%" >nul 2>nul',
                'start "" "%CURRENT_EXE%"',
                'del "%~f0"',
            ]
        ),
        encoding="utf-8",
    )

    subprocess.Popen(
        ["cmd.exe", "/c", str(updater_script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
