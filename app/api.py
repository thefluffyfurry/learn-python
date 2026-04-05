"""Shared API client for desktop and console frontends."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional
from urllib import error, request

from app.content import LESSON_MAP
from app.identity import get_client_identity
from app.runtime import app_root
from app.settings import LOCAL_API_URL
from app.version import APP_VERSION


class ApiError(RuntimeError):
    """Base API error."""


class ApiConnectionError(ApiError):
    """Raised when a server cannot be reached."""


class ApiClient:
    def __init__(self, base_url: str, fallback_url: str = LOCAL_API_URL, client_type: str = "desktop") -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.client_type = client_type.strip() or "desktop"
        self.token: Optional[str] = None
        self.hosted_token: Optional[str] = None
        self.local_token: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.last_source = "local" if self.is_local_mode() else "hosted"
        self.local_db_path = app_root() / "teaching_app.db"
        self.client_identity = get_client_identity(self.client_type)

    @staticmethod
    def _is_local_url(url: str) -> bool:
        normalized = url.lower()
        return normalized.startswith("http://127.0.0.1") or normalized.startswith("http://localhost")

    def is_local_mode(self) -> bool:
        return self._is_local_url(self.base_url)

    def using_offline_cache(self) -> bool:
        return not self.is_local_mode() and self.last_source == "local"

    def auth_message(self) -> str:
        if self.is_local_mode():
            return (
                "Local mode is active. Accounts are saved in the local "
                "teaching_app.db file for this project, so they do not sync "
                "to another computer unless that database file is copied too."
            )
        return (
            f"Hosted sync is active with {self.base_url}. If the hosted API goes down, "
            "the app keeps working against the local cache and syncs your lesson progress "
            "the next time the hosted API is reachable."
        )

    def _decode_json(self, raw: str, url: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            trimmed = raw.lstrip().lower()
            if trimmed.startswith("<html") or "<script" in trimmed:
                raise ApiConnectionError(
                    "The hosted server returned an HTML page instead of API data. "
                    "Your web host is blocking desktop app requests, so online sign-in is unavailable right now."
                ) from exc
            raise ApiError(f"The server at {url} returned an invalid response.") from exc

    def _call_url(
        self,
        url: str,
        path: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = None
        headers = {
            "Content-Type": "application/json",
            "X-PyQuest-App-Version": APP_VERSION,
            "X-PyQuest-Client-Type": self.client_type,
            "X-PyQuest-Session-Name": self.client_identity["session_name"],
            "X-PyQuest-Install-Id": self.client_identity["install_id"],
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(f"{url}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=8) as response:
                raw = response.read().decode("utf-8")
                return self._decode_json(raw, url)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                detail = self._decode_json(raw, url).get("error", raw)
            except ApiError as parse_error:
                detail = str(parse_error)
            raise ApiError(str(detail)) from exc
        except error.URLError as exc:
            raise ApiConnectionError(f"Cannot reach the teaching server at {url}.") from exc

    def _call_hosted(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._call_url(self.base_url, path, method, payload, token=self.hosted_token)

    def _call_local(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._call_url(self.fallback_url, path, method, payload, token=self.local_token)

    def _remember_credentials(self, username: str, password: str) -> None:
        self.username = username.strip()
        self.password = password

    def _update_local_password(self, username: str, password: str) -> bool:
        password_hash = self._hash_password(password)
        with sqlite3.connect(self.local_db_path) as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (password_hash, username.strip()),
            )
            conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _ensure_local_session(self, username: str, password: str, prefer_signup: bool = False) -> Dict[str, Any]:
        username = username.strip()
        payload = {"username": username, "password": password}

        if prefer_signup:
            try:
                result = self._call_local("/signup", "POST", payload)
                self.local_token = result["token"]
                return result
            except ApiConnectionError:
                raise
            except ApiError:
                pass

        try:
            result = self._call_local("/login", "POST", payload)
            self.local_token = result["token"]
            return result
        except ApiConnectionError:
            raise
        except ApiError as exc:
            if "Invalid username or password." in str(exc) and self._update_local_password(username, password):
                result = self._call_local("/login", "POST", payload)
                self.local_token = result["token"]
                return result

        result = self._call_local("/signup", "POST", payload)
        self.local_token = result["token"]
        return result

    def _restore_hosted_session(self) -> bool:
        if self.is_local_mode():
            return False
        if self.hosted_token:
            return True
        if not self.username or self.password is None:
            return False

        payload = {"username": self.username, "password": self.password}
        try:
            result = self._call_url(self.base_url, "/login", "POST", payload)
        except ApiConnectionError:
            return False
        except ApiError:
            try:
                result = self._call_url(self.base_url, "/signup", "POST", payload)
            except ApiConnectionError:
                return False
            except ApiError:
                return False

        self.hosted_token = result["token"]
        return True

    def _call_hosted_authenticated(
        self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not self._restore_hosted_session():
            raise ApiConnectionError(f"Cannot reach the teaching server at {self.base_url}.")
        try:
            return self._call_hosted(path, method, payload)
        except ApiError as exc:
            if "Unauthorized." not in str(exc) or not self.username or self.password is None:
                raise
        self.hosted_token = None
        if not self._restore_hosted_session():
            raise ApiConnectionError(f"Cannot reach the teaching server at {self.base_url}.")
        return self._call_hosted(path, method, payload)

    def _call_local_authenticated(
        self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self.local_token is None:
            if not self.username or self.password is None:
                raise ApiError("Sign in again to continue.")
            self._ensure_local_session(self.username, self.password)
        return self._call_local(path, method, payload)

    def _local_lesson_scores(self) -> Dict[str, int]:
        if self.local_token is None:
            return {}
        with sqlite3.connect(self.local_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT lesson_progress.lesson_id, lesson_progress.score
                FROM lesson_progress
                JOIN sessions ON sessions.user_id = lesson_progress.user_id
                WHERE sessions.token = ?
                """,
                (self.local_token,),
            ).fetchall()
        return {row["lesson_id"]: int(row["score"]) for row in rows}

    def _sync_local_to_hosted(self) -> None:
        if self.is_local_mode():
            return
        if not self.username or self.password is None:
            return
        if not self._restore_hosted_session():
            return

        try:
            self._ensure_local_session(self.username, self.password)
            local_profile = self._call_local_authenticated("/profile")
            hosted_profile = self._call_hosted_authenticated("/profile")
        except (ApiError, ApiConnectionError):
            return

        hosted_ids = set(hosted_profile["completed_lesson_ids"])
        pending_ids = [lesson_id for lesson_id in local_profile["completed_lesson_ids"] if lesson_id not in hosted_ids]
        if not pending_ids:
            return

        score_map = self._local_lesson_scores()
        for lesson_id in pending_ids:
            lesson = LESSON_MAP.get(lesson_id)
            if lesson is None:
                continue
            if score_map.get(lesson_id, 0) == 1:
                selected_index = lesson.quiz.answer_index
            else:
                selected_index = 0 if lesson.quiz.answer_index != 0 else 1
            try:
                self._call_hosted_authenticated(
                    "/submit-lesson",
                    "POST",
                    {"lesson_id": lesson_id, "selected_index": selected_index},
                )
            except (ApiError, ApiConnectionError):
                return

    def _mirror_submission_locally(self, lesson_id: str, selected_index: int) -> None:
        if self.is_local_mode():
            return
        if not self.username or self.password is None:
            return
        try:
            self._ensure_local_session(self.username, self.password)
            self._call_local_authenticated(
                "/submit-lesson",
                "POST",
                {"lesson_id": lesson_id, "selected_index": selected_index},
            )
        except (ApiError, ApiConnectionError):
            return

    def signup(self, username: str, password: str) -> Dict[str, Any]:
        self._remember_credentials(username, password)
        if self.is_local_mode():
            result = self._ensure_local_session(username, password, prefer_signup=True)
            self.token = self.local_token
            self.last_source = "local"
            return result
        try:
            result = self._call_url(self.base_url, "/signup", "POST", {"username": username, "password": password})
            self.hosted_token = result["token"]
            self.token = self.hosted_token
            self.last_source = "hosted"
            self._ensure_local_session(username, password, prefer_signup=True)
            return result
        except ApiConnectionError:
            result = self._ensure_local_session(username, password, prefer_signup=True)
            self.token = self.local_token
            self.last_source = "local"
        return result

    def login(self, username: str, password: str) -> Dict[str, Any]:
        self._remember_credentials(username, password)
        if self.is_local_mode():
            result = self._ensure_local_session(username, password)
            self.token = self.local_token
            self.last_source = "local"
            return result
        try:
            result = self._call_url(self.base_url, "/login", "POST", {"username": username, "password": password})
            self.hosted_token = result["token"]
            self.token = self.hosted_token
            self.last_source = "hosted"
            self._ensure_local_session(username, password)
            self._sync_local_to_hosted()
            return result
        except ApiConnectionError:
            result = self._ensure_local_session(username, password)
            self.token = self.local_token
            self.last_source = "local"
        return result

    def lessons(self) -> List[Dict[str, Any]]:
        if self.is_local_mode():
            self.last_source = "local"
            return self._call_local("/lessons")["lessons"]
        self._sync_local_to_hosted()
        try:
            lessons = self._call_hosted("/lessons")["lessons"]
            self.last_source = "hosted"
            self.token = self.hosted_token
            return lessons
        except ApiConnectionError:
            self.last_source = "local"
            self.token = self.local_token
            return self._call_local("/lessons")["lessons"]

    def profile(self) -> Dict[str, Any]:
        if self.is_local_mode():
            self.last_source = "local"
            self.token = self.local_token
            return self._call_local_authenticated("/profile")
        self._sync_local_to_hosted()
        try:
            profile = self._call_hosted_authenticated("/profile")
            self.last_source = "hosted"
            self.token = self.hosted_token
            return profile
        except ApiConnectionError:
            profile = self._call_local_authenticated("/profile")
            self.last_source = "local"
            self.token = self.local_token
            return profile

    def leaderboard(self) -> List[Dict[str, Any]]:
        if self.is_local_mode():
            self.last_source = "local"
            return self._call_local("/leaderboard")["leaders"]
        try:
            leaders = self._call_hosted("/leaderboard")["leaders"]
            self.last_source = "hosted"
            return leaders
        except ApiConnectionError:
            self.last_source = "local"
            return self._call_local("/leaderboard")["leaders"]

    def submit_lesson(self, lesson_id: str, selected_index: int) -> Dict[str, Any]:
        payload = {"lesson_id": lesson_id, "selected_index": selected_index}
        if self.is_local_mode():
            self.last_source = "local"
            self.token = self.local_token
            return self._call_local_authenticated("/submit-lesson", "POST", payload)

        self._sync_local_to_hosted()
        try:
            result = self._call_hosted_authenticated("/submit-lesson", "POST", payload)
            self.last_source = "hosted"
            self.token = self.hosted_token
            self._mirror_submission_locally(lesson_id, selected_index)
            return result
        except ApiConnectionError:
            result = self._call_local_authenticated("/submit-lesson", "POST", payload)
            self.last_source = "local"
            self.token = self.local_token
            return result

    def clear_session(self) -> None:
        self.token = None
        self.hosted_token = None
        self.local_token = None
        self.username = None
        self.password = None
        self.last_source = "local" if self.is_local_mode() else "hosted"
