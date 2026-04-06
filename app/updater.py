"""Windows self-update support backed by the hosted API and local SQLite state."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from app.runtime import app_root
from app.version import APP_VERSION


@dataclass(slots=True)
class UpdateInfo:
    version: str
    download_url: str
    notes: str = ""
    asset_name: str = ""
    wipe_local_state: bool = False
    force_update: bool = False


APP_META_DB = app_root() / "teaching_app.db"


def _normalize_version(version: str) -> str:
    return version.strip().lstrip("vV")


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in _normalize_version(version).replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            parts.append(0)
            continue
        parts.append(int(digits))
    return tuple(parts)


def _connect_state_db() -> sqlite3.Connection:
    conn = sqlite3.connect(APP_META_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_state_table() -> None:
    with _connect_state_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def sync_installed_version() -> str:
    _ensure_state_table()
    current_version = _normalize_version(APP_VERSION)
    with _connect_state_db() as conn:
        conn.execute(
            """
            INSERT INTO app_meta (key, value, updated_at)
            VALUES ('installed_version', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (current_version,),
        )
        conn.commit()
    return current_version


def can_self_update() -> bool:
    return os.name == "nt" and getattr(sys, "frozen", False)


def fetch_server_update(base_url: str, path: str = "/app-update") -> UpdateInfo | None:
    base_url = base_url.strip().rstrip("/")
    path = path.strip() or "/app-update"
    if not path.startswith("/"):
        path = f"/{path}"
    if not base_url:
        return None

    current_version = sync_installed_version()
    api_url = f"{base_url}{path}"
    req = request.Request(
        api_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PyQuestAcademyUpdater",
        },
    )
    try:
        with request.urlopen(req, timeout=8) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Server update check failed with HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cannot reach the update server at {api_url}.") from exc

    try:
        import json

        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The update server returned invalid JSON.") from exc

    version = _normalize_version(str(data.get("version") or ""))
    if not version:
        return None

    download_url = str(data.get("download_url") or "").strip()
    if not download_url:
        return None

    notes = str(data.get("notes", "")).strip()
    asset_name = str(data.get("asset_name", "")).strip() or Path(download_url).name
    wipe_local_state = bool(data.get("wipe_local_state", False))
    force_update = bool(data.get("force_update", False))

    if not force_update and _version_key(version) <= _version_key(current_version):
        return None
    return UpdateInfo(
        version=version,
        download_url=download_url,
        notes=notes,
        asset_name=asset_name,
        wipe_local_state=wipe_local_state,
        force_update=force_update,
    )


def stage_update(update: UpdateInfo) -> None:
    if not can_self_update():
        raise RuntimeError("Self-update only works from the packaged Windows app.")

    current_exe = Path(sys.executable).resolve()
    pending_exe = current_exe.with_name(f"{current_exe.stem}-{update.version}.pending.exe")
    pending_archive = current_exe.with_name(f"{current_exe.stem}-{update.version}.pending.zip")
    updater_script = current_exe.with_name("apply_update.bat")
    state_db = APP_META_DB.resolve()

    req = request.Request(update.download_url, headers={"User-Agent": "PyQuestAcademyUpdater"})
    try:
        target_path = pending_archive if update.asset_name.lower().endswith(".zip") else pending_exe
        with request.urlopen(req, timeout=30) as response, target_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                handle.write(chunk)
    except error.URLError as exc:
        if pending_exe.exists():
            pending_exe.unlink(missing_ok=True)
        if pending_archive.exists():
            pending_archive.unlink(missing_ok=True)
        raise RuntimeError(f"Cannot download the new version from {update.download_url}.") from exc

    if update.asset_name.lower().endswith(".zip"):
        if not pending_archive.exists() or pending_archive.stat().st_size == 0:
            pending_archive.unlink(missing_ok=True)
            raise RuntimeError("The downloaded update file was empty.")
        try:
            with zipfile.ZipFile(pending_archive) as archive:
                exe_member = next(
                    (name for name in archive.namelist() if Path(name).name.lower() == current_exe.name.lower()),
                    None,
                )
                if exe_member is None:
                    exe_member = next(
                        (name for name in archive.namelist() if Path(name).suffix.lower() == ".exe"),
                        None,
                    )
                if exe_member is None:
                    raise RuntimeError("The update zip does not contain a Windows executable.")
                with archive.open(exe_member) as source, pending_exe.open("wb") as target:
                    target.write(source.read())
        except zipfile.BadZipFile as exc:
            pending_archive.unlink(missing_ok=True)
            raise RuntimeError("The downloaded update zip is not valid.") from exc
        finally:
            pending_archive.unlink(missing_ok=True)

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
                *([f'del /Q "{state_db}" >nul 2>nul'] if update.wipe_local_state else []),
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
