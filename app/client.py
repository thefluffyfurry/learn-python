"""Tkinter desktop UI for the Python teaching app."""

from __future__ import annotations

import json
import sqlite3
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional
from urllib import error, request

from app.content import LESSON_MAP
from app.runtime import app_root
from app.settings import GITHUB_UPDATE_ASSET_NAME, GITHUB_UPDATE_REPO, LOCAL_API_URL
from app.updater import UpdateInfo, can_self_update, fetch_github_update, stage_update, sync_installed_version
from app.version import APP_NAME, APP_VERSION


class ApiError(RuntimeError):
    """Base API error."""


class ApiConnectionError(ApiError):
    """Raised when a server cannot be reached."""


class ApiClient:
    def __init__(self, base_url: str, fallback_url: str = LOCAL_API_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_url = fallback_url.rstrip("/")
        self.token: Optional[str] = None
        self.hosted_token: Optional[str] = None
        self.local_token: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.last_source = "local" if self.is_local_mode() else "hosted"
        self.local_db_path = app_root() / "teaching_app.db"

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
        headers = {"Content-Type": "application/json"}
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
        import hashlib

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


class ScrollFrame(tk.Frame):
    def __init__(self, master: tk.Misc, bg: str) -> None:
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))

    def reset(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self.canvas.yview_moveto(0)


class TeachingApp(tk.Tk):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.title(APP_NAME)
        self.geometry("1180x780")
        self.minsize(860, 620)
        self.configure(bg="#f4efe8")

        self.colors = {
            "shell": "#17324d",
            "shell_soft": "#284c6c",
            "shell_text": "#f7f4ef",
            "shell_muted": "#cad5df",
            "accent": "#f08a4b",
            "accent_soft": "#ffe5d6",
            "success": "#237a57",
            "success_soft": "#dff3ea",
            "warn": "#b8612c",
            "warn_soft": "#fde8da",
            "surface": "#fffdf9",
            "surface_alt": "#f7f0e7",
            "page": "#f4efe8",
            "border": "#dccfc2",
            "text": "#1d2d3d",
            "muted": "#647587",
            "code": "#101923",
        }

        self.user: Optional[Dict[str, Any]] = None
        self.leaders: List[Dict[str, Any]] = []
        self.lesson_catalog: List[Dict[str, Any]] = []
        self.topic_lookup: Dict[str, List[Dict[str, Any]]] = {}
        self.lesson_lookup: Dict[str, Dict[str, Any]] = {}
        self.completed_ids: set[str] = set()
        self.active_lesson: Optional[Dict[str, Any]] = None
        self.update_check_started = False
        self.update_prompt_open = False
        self.update_download_running = False

        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self.topic_var = tk.StringVar(value="All Topics")
        self.answer_var = tk.IntVar(value=-1)

        self._build_styles()
        self._build_shell()
        self._show_auth()
        sync_installed_version()
        self.after(1200, self._check_for_updates_async)

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=self.colors["page"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            font=("Segoe UI Semibold", 10),
            padding=(16, 9),
            background="#e8dfd3",
            foreground=self.colors["muted"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.colors["surface"])],
            foreground=[("selected", self.colors["text"])],
        )
        style.configure(
            "Board.Treeview",
            rowheight=34,
            background=self.colors["surface"],
            fieldbackground=self.colors["surface"],
            foreground=self.colors["text"],
        )
        style.configure(
            "Board.Treeview.Heading",
            background="#e7ddd1",
            foreground=self.colors["text"],
            relief="flat",
            font=("Segoe UI Semibold", 10),
        )
        style.map("Board.Treeview", background=[("selected", "#ddebf8")], foreground=[("selected", self.colors["text"])])
        style.configure("TProgressbar", troughcolor="#eadfce", background=self.colors["accent"], borderwidth=0)

    def _build_shell(self) -> None:
        self.header = tk.Frame(self, bg=self.colors["shell"], height=96)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        title = tk.Frame(self.header, bg=self.colors["shell"])
        title.pack(side="left", padx=22, pady=14)
        tk.Label(title, text="PYQUEST LEARNING STUDIO", bg=self.colors["shell"], fg="#9fb9cf", font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(title, text="PyQuest Academy", bg=self.colors["shell"], fg=self.colors["shell_text"], font=("Georgia", 26, "bold")).pack(anchor="w")
        tk.Label(
            title,
            text="Python lessons, leaderboard tracking, and a built-in offline cache that syncs back later.",
            bg=self.colors["shell"],
            fg=self.colors["shell_muted"],
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        tk.Label(title, text=f"Desktop version {APP_VERSION}", bg=self.colors["shell"], fg="#8fb0ca", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        status_wrap = tk.Frame(self.header, bg=self.colors["shell"])
        status_wrap.pack(side="right", padx=22, pady=16)
        self.status_chip = tk.Label(
            status_wrap,
            text="Offline",
            bg=self.colors["shell_soft"],
            fg=self.colors["shell_text"],
            padx=14,
            pady=8,
            font=("Segoe UI Semibold", 10),
        )
        self.status_chip.pack(anchor="e")
        self.endpoint_label = tk.Label(
            status_wrap,
            text="Endpoint: --",
            bg=self.colors["shell"],
            fg=self.colors["shell_muted"],
            font=("Consolas", 9),
            wraplength=340,
            justify="right",
        )
        self.endpoint_label.pack(anchor="e", pady=(8, 0))

        self.body = tk.Frame(self, bg=self.colors["page"])
        self.body.pack(fill="both", expand=True, padx=14, pady=14)

        self.auth_frame = tk.Frame(
            self.body,
            bg=self.colors["surface"],
            padx=34,
            pady=32,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.app_frame = tk.Frame(self.body, bg=self.colors["page"])

        self._build_auth()
        self._build_app()

    def _build_auth(self) -> None:
        mode_panel = tk.Frame(
            self.auth_frame,
            bg=self.colors["surface_alt"],
            padx=18,
            pady=16,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        )
        mode_panel.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        self.auth_mode_badge = tk.Label(
            mode_panel,
            text="SYNC MODE",
            bg=self.colors["accent_soft"],
            fg=self.colors["warn"],
            padx=10,
            pady=5,
            font=("Segoe UI Semibold", 9),
        )
        self.auth_mode_badge.pack(anchor="w")
        self.auth_mode_title = tk.Label(
            mode_panel,
            text="Hosted sync + offline cache",
            bg=self.colors["surface_alt"],
            fg=self.colors["text"],
            font=("Georgia", 18, "bold"),
        )
        self.auth_mode_title.pack(anchor="w", pady=(10, 4))
        self.auth_mode_meta = tk.Label(
            mode_panel,
            text=self.api.auth_message(),
            bg=self.colors["surface_alt"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            justify="left",
            wraplength=560,
        )
        self.auth_mode_meta.pack(anchor="w")

        tk.Label(
            self.auth_frame,
            text="Launch your Python journey",
            bg=self.colors["surface"],
            fg=self.colors["text"],
            font=("Georgia", 24, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(
            self.auth_frame,
            text="Sign in once, then keep learning even if the hosted API temporarily disappears.",
            bg=self.colors["surface"],
            fg=self.colors["muted"],
            font=("Segoe UI", 11),
            justify="left",
            wraplength=540,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 18))
        tk.Label(self.auth_frame, text="Username", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI Semibold", 10)).grid(row=3, column=0, sticky="w")
        self.username_entry = tk.Entry(
            self.auth_frame,
            font=("Segoe UI", 12),
            relief="flat",
            bg="#fffaf4",
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["shell_soft"],
        )
        self.username_entry.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 12), ipady=8)
        tk.Label(self.auth_frame, text="Password", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI Semibold", 10)).grid(row=5, column=0, sticky="w")
        self.password_entry = tk.Entry(
            self.auth_frame,
            show="*",
            font=("Segoe UI", 12),
            relief="flat",
            bg="#fffaf4",
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["shell_soft"],
        )
        self.password_entry.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(4, 18), ipady=8)
        tk.Button(
            self.auth_frame,
            text="Log In",
            command=self._login,
            bg=self.colors["shell"],
            fg="white",
            relief="flat",
            padx=14,
            pady=12,
            font=("Segoe UI Semibold", 11),
        ).grid(row=7, column=0, sticky="ew", padx=(0, 8))
        tk.Button(
            self.auth_frame,
            text="Create Account",
            command=self._signup,
            bg=self.colors["accent"],
            fg="white",
            relief="flat",
            padx=14,
            pady=12,
            font=("Segoe UI Semibold", 11),
        ).grid(row=7, column=1, sticky="ew")

    def _build_app(self) -> None:
        summary = tk.Frame(self.app_frame, bg=self.colors["shell"], padx=20, pady=18)
        summary.pack(fill="x")

        identity = tk.Frame(summary, bg=self.colors["shell"])
        identity.pack(side="left", fill="x", expand=True)
        self.user_name = tk.Label(identity, text="Not signed in", bg=self.colors["shell"], fg=self.colors["shell_text"], font=("Georgia", 24, "bold"))
        self.user_name.pack(anchor="w")
        self.user_meta = tk.Label(identity, text="", bg=self.colors["shell"], fg=self.colors["shell_muted"], font=("Segoe UI", 10), justify="left")
        self.user_meta.pack(anchor="w", pady=(2, 8))
        self.sync_meta = tk.Label(identity, text="", bg=self.colors["shell"], fg="#9fd9c0", font=("Segoe UI Semibold", 10), justify="left")
        self.sync_meta.pack(anchor="w", pady=(0, 10))
        self.progress = ttk.Progressbar(identity, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 2))

        actions = tk.Frame(summary, bg=self.colors["shell"])
        actions.pack(side="right")
        self.sync_card = tk.Frame(actions, bg=self.colors["surface_alt"], padx=14, pady=12, highlightthickness=1, highlightbackground="#415b72")
        self.sync_card.pack(fill="x", pady=(0, 10))
        self.sync_title = tk.Label(self.sync_card, text="SYNC STATUS", bg=self.colors["surface_alt"], fg=self.colors["warn"], font=("Segoe UI Semibold", 9))
        self.sync_title.pack(anchor="w")
        self.sync_detail = tk.Label(self.sync_card, text="Waiting for sign-in", bg=self.colors["surface_alt"], fg=self.colors["text"], font=("Segoe UI", 10), justify="left", wraplength=250)
        self.sync_detail.pack(anchor="w", pady=(6, 0))
        tk.Button(actions, text="Continue Learning", command=self._continue_learning, bg=self.colors["accent"], fg="white", relief="flat", padx=16, pady=10, font=("Segoe UI Semibold", 10)).pack(side="left", padx=4)
        tk.Button(actions, text="Refresh", command=self._refresh_data, bg=self.colors["shell_soft"], fg="white", relief="flat", padx=16, pady=10, font=("Segoe UI Semibold", 10)).pack(side="left", padx=4)
        tk.Button(actions, text="Log Out", command=self._logout, bg="#8d3f36", fg="white", relief="flat", padx=16, pady=10, font=("Segoe UI Semibold", 10)).pack(side="left", padx=4)

        self.notebook = ttk.Notebook(self.app_frame)
        self.notebook.pack(fill="both", expand=True, pady=(12, 0))

        self.dashboard_tab = ScrollFrame(self.notebook, self.colors["page"])
        self.learn_tab = tk.Frame(self.notebook, bg=self.colors["page"])
        self.board_tab = tk.Frame(self.notebook, bg=self.colors["page"])

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.learn_tab, text="Learn")
        self.notebook.add(self.board_tab, text="Leaderboard")

        self._build_learn_tab()
        self._build_board_tab()

    def _build_learn_tab(self) -> None:
        controls = tk.Frame(self.learn_tab, bg=self.colors["surface"], padx=12, pady=12, highlightthickness=1, highlightbackground=self.colors["border"])
        controls.pack(fill="x")
        tk.Label(controls, text="Search", bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        tk.Entry(
            controls,
            textvariable=self.search_var,
            font=("Segoe UI", 11),
            relief="flat",
            bg="#fffaf4",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
        ).grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=5)
        tk.Label(controls, text="Filter", bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI Semibold", 10)).grid(row=0, column=1, sticky="w")
        filter_box = ttk.Combobox(controls, textvariable=self.filter_var, values=["All", "Open", "Done"], state="readonly", width=10)
        filter_box.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        tk.Label(controls, text="Topic", bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI Semibold", 10)).grid(row=0, column=2, sticky="w")
        self.topic_box = ttk.Combobox(controls, textvariable=self.topic_var, state="readonly")
        self.topic_box.grid(row=1, column=2, sticky="ew", padx=(0, 10))
        tk.Button(controls, text="Open Next", command=self._continue_learning, bg=self.colors["accent"], fg="white", relief="flat", padx=14, pady=8, font=("Segoe UI Semibold", 10)).grid(row=1, column=3, sticky="e")
        controls.grid_columnconfigure(0, weight=2)
        controls.grid_columnconfigure(2, weight=2)
        self.search_var.trace_add("write", self._refresh_lesson_browser)
        filter_box.bind("<<ComboboxSelected>>", self._refresh_lesson_browser)
        self.topic_box.bind("<<ComboboxSelected>>", self._refresh_lesson_browser)

        self.topic_summary = tk.Label(
            self.learn_tab,
            text="",
            bg=self.colors["surface_alt"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            anchor="w",
            justify="left",
            padx=14,
            pady=10,
        )
        self.topic_summary.pack(fill="x", padx=12, pady=(0, 10))

        panes = ttk.PanedWindow(self.learn_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = tk.Frame(panes, bg=self.colors["surface"], padx=12, pady=12)
        right = tk.Frame(panes, bg=self.colors["surface"], padx=12, pady=12)
        panes.add(left, weight=1)
        panes.add(right, weight=3)

        tk.Label(left, text="Lesson List", bg=self.colors["surface"], fg=self.colors["text"], font=("Georgia", 18, "bold")).pack(anchor="w")
        tk.Label(left, text="Topic, stage, and completion state update live as you filter.", bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))
        self.lesson_list = tk.Listbox(
            left,
            bg="#fffaf4",
            fg=self.colors["text"],
            font=("Segoe UI", 10),
            activestyle="none",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            selectbackground="#dfeaf4",
            selectforeground=self.colors["text"],
        )
        self.lesson_list.pack(fill="both", expand=True, pady=(10, 0))
        self.lesson_list.bind("<<ListboxSelect>>", self._on_lesson_select)

        self.detail_scroll = ScrollFrame(right, self.colors["surface"])
        self.detail_scroll.pack(fill="both", expand=True)

    def _build_board_tab(self) -> None:
        tk.Label(self.board_tab, text="Leaderboard", bg=self.colors["page"], fg=self.colors["text"], font=("Georgia", 22, "bold")).pack(anchor="w", padx=12, pady=(14, 2))
        tk.Label(self.board_tab, text="Top learners ranked by XP and completed lessons.", bg=self.colors["page"], fg=self.colors["muted"], font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(0, 8))
        self.board_table = ttk.Treeview(self.board_tab, columns=("rank", "username", "xp", "done"), show="headings", style="Board.Treeview")
        for column, label, width in [("rank", "Rank", 90), ("username", "Learner", 260), ("xp", "XP", 140), ("done", "Completed Lessons", 180)]:
            self.board_table.heading(column, text=label)
            self.board_table.column(column, width=width, anchor="center")
        self.board_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _sync_state_text(self, username: Optional[str]) -> tuple[str, str, str]:
        if self.api.is_local_mode():
            return (
                "LOCAL CACHE",
                "Local-only mode is active.",
                "Progress is stored in the local database next to this project or executable.",
            )
        if self.api.using_offline_cache():
            display_name = username or "this learner"
            return (
                "OFFLINE CACHE ACTIVE",
                f"{display_name} is working from the local cache.",
                "The app will replay missing lesson completions to the hosted account when the API is reachable again.",
            )
        return (
            "HOSTED SYNC ONLINE",
            "Live hosted sync is active.",
            "Completed lessons are mirrored locally as a safety cache while the hosted account stays current.",
        )

    def _apply_chip_style(self, label: tk.Label, state_key: str) -> None:
        palette = {
            "local": (self.colors["warn_soft"], self.colors["warn"]),
            "offline-cache": (self.colors["accent_soft"], self.colors["warn"]),
            "hosted": (self.colors["success_soft"], self.colors["success"]),
        }
        bg, fg = palette[state_key]
        label.config(bg=bg, fg=fg)

    def _refresh_mode_panels(self, username: Optional[str] = None) -> None:
        endpoint = self.api.base_url if not self.api.is_local_mode() else self.api.fallback_url
        self.endpoint_label.config(text=f"Endpoint: {endpoint}")

        if self.api.is_local_mode():
            state_key = "local"
            chip_text = "Local account mode"
        elif self.api.using_offline_cache():
            state_key = "offline-cache"
            chip_text = "Offline cache active"
        else:
            state_key = "hosted"
            chip_text = "Hosted sync online"

        self.status_chip.config(text=chip_text)
        self._apply_chip_style(self.status_chip, state_key)
        self._apply_chip_style(self.auth_mode_badge, state_key)

        title, headline, detail = self._sync_state_text(username)
        self.auth_mode_badge.config(text=title)
        self.auth_mode_title.config(text=headline)
        self.auth_mode_meta.config(text=detail)
        self.sync_title.config(text=title)
        self.sync_detail.config(text=detail)

    def _show_auth(self) -> None:
        self.app_frame.pack_forget()
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
        self._refresh_mode_panels()

    def _show_app(self) -> None:
        self.auth_frame.place_forget()
        self.app_frame.pack(fill="both", expand=True)

    def _login(self) -> None:
        self._authenticate("login")

    def _signup(self) -> None:
        self._authenticate("signup")

    def _authenticate(self, action: str) -> None:
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Missing info", "Enter both username and password.")
            return
        try:
            result = self.api.signup(username, password) if action == "signup" else self.api.login(username, password)
        except RuntimeError as exc:
            messagebox.showerror("Authentication failed", str(exc))
            return
        self.user = result
        self._refresh_data()
        self._show_app()

    def _reset_signed_out_view(self) -> None:
        self.user_name.config(text="Not signed in")
        self.user_meta.config(text="")
        self.sync_meta.config(text="")
        self.progress["value"] = 0
        self.sync_title.config(text="SYNC STATUS")
        self.sync_detail.config(text="Waiting for sign-in")
        self.topic_summary.config(text="")
        self.answer_var.set(-1)
        self.lesson_list.delete(0, tk.END)
        self.board_table.delete(*self.board_table.get_children())
        self.detail_scroll.reset()

    def _logout(self) -> None:
        self.api.clear_session()
        self.user = None
        self.leaders = []
        self.lesson_catalog = []
        self.topic_lookup = {}
        self.lesson_lookup = {}
        self.completed_ids = set()
        self.active_lesson = None
        self.filter_var.set("All")
        self.topic_var.set("All Topics")
        self.search_var.set("")
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self._reset_signed_out_view()
        self._show_auth()
        self.username_entry.focus_set()

    def _check_for_updates_async(self) -> None:
        if self.update_check_started or self.update_download_running:
            return
        if not GITHUB_UPDATE_REPO.strip() or not GITHUB_UPDATE_ASSET_NAME.strip():
            return
        self.update_check_started = True
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

    def _check_for_updates_worker(self) -> None:
        try:
            update = fetch_github_update(GITHUB_UPDATE_REPO, GITHUB_UPDATE_ASSET_NAME)
        except RuntimeError:
            update = None
        self.after(0, lambda: self._handle_update_result(update))

    def _handle_update_result(self, update: Optional[UpdateInfo]) -> None:
        self.update_check_started = False
        if update is None or self.update_prompt_open:
            return

        self.update_prompt_open = True
        detail = f"A new version is available.\n\nCurrent version: {APP_VERSION}\nNew version: {update.version}"
        if update.notes:
            detail += f"\n\nWhat's new:\n{update.notes}"
        elif update.release_url:
            detail += f"\n\nRelease page:\n{update.release_url}"

        if not can_self_update():
            messagebox.showinfo("Update Available", detail)
            self.update_prompt_open = False
            return

        should_install = messagebox.askyesno("Update Available", f"{detail}\n\nDownload and restart now?")
        self.update_prompt_open = False
        if should_install:
            self._download_update_async(update)

    def _download_update_async(self, update: UpdateInfo) -> None:
        if self.update_download_running:
            return
        self.update_download_running = True
        self.status_chip.config(text="Downloading update")
        threading.Thread(target=self._download_update_worker, args=(update,), daemon=True).start()

    def _download_update_worker(self, update: UpdateInfo) -> None:
        error_text: Optional[str] = None
        try:
            stage_update(update)
        except RuntimeError as exc:
            error_text = str(exc)
        self.after(0, lambda: self._finish_update_download(error_text))

    def _finish_update_download(self, error_text: Optional[str]) -> None:
        self.update_download_running = False
        self._refresh_mode_panels(self.user["username"] if self.user else None)
        if error_text:
            messagebox.showerror("Update Failed", error_text)
            return
        messagebox.showinfo("Installing Update", "The new version is ready. The app will close and relaunch now.")
        self.after(150, self.destroy)

    def _topic_choices(self) -> List[str]:
        return ["All Topics"] + sorted(self.topic_lookup)

    def _level(self, xp: int) -> int:
        return (xp // 120) + 1

    def _recommended_lesson(self) -> Optional[Dict[str, Any]]:
        if not self.lesson_catalog:
            return None
        return next((lesson for lesson in self.lesson_catalog if lesson["lesson_id"] not in self.completed_ids), self.lesson_catalog[0])

    def _refresh_data(self) -> None:
        if self.api.token is None:
            return
        try:
            profile = self.api.profile()
            leaders = self.api.leaderboard()
            lessons = self.api.lessons()
        except RuntimeError as exc:
            messagebox.showerror("Sync error", str(exc))
            return

        previous_lesson_id = self.active_lesson["lesson_id"] if self.active_lesson else None

        self.user = profile
        self.leaders = leaders
        self.lesson_catalog = lessons
        self.completed_ids = set(profile["completed_lesson_ids"])
        self.topic_lookup = {}
        self.lesson_lookup = {}
        for lesson in lessons:
            self.topic_lookup.setdefault(lesson["topic_name"], []).append(lesson)
            self.lesson_lookup[lesson["lesson_id"]] = lesson
        for topic_lessons in self.topic_lookup.values():
            topic_lessons.sort(key=lambda item: item["stage"])

        if previous_lesson_id and previous_lesson_id in self.lesson_lookup:
            self.active_lesson = self.lesson_lookup[previous_lesson_id]
        else:
            self.active_lesson = self._recommended_lesson()

        total = len(self.lesson_catalog) or 1
        percent = int((profile["completed_lessons"] / total) * 100)
        self.user_name.config(text=profile["username"])
        self.user_meta.config(
            text=(
                f"Level {self._level(profile['xp'])}  |  XP {profile['xp']}  |  "
                f"Completed {profile['completed_lessons']} / {total}  |  Progress {percent}%"
            )
        )
        self.sync_meta.config(text=self._sync_state_text(profile["username"])[2])
        self.progress["value"] = percent

        self.topic_box["values"] = self._topic_choices()
        if self.topic_var.get() not in self.topic_box["values"]:
            self.topic_var.set("All Topics")

        self._refresh_mode_panels(profile["username"])
        self._render_dashboard()
        self._refresh_lesson_browser()
        self._render_leaderboard()

    def _selected_topic(self) -> str:
        topic = self.topic_var.get().strip()
        return topic if topic else "All Topics"

    def _filter_lessons(self) -> List[Dict[str, Any]]:
        query = self.search_var.get().strip().lower()
        mode = self.filter_var.get()
        topic = self._selected_topic()
        lessons = self.lesson_catalog if topic == "All Topics" else self.topic_lookup.get(topic, [])
        filtered = []
        for lesson in lessons:
            haystack = " ".join(
                [lesson["lesson_id"], lesson["topic_name"], lesson["title"], lesson["summary"], lesson["challenge"]]
            ).lower()
            if query and query not in haystack:
                continue
            done = lesson["lesson_id"] in self.completed_ids
            if mode == "Open" and done:
                continue
            if mode == "Done" and not done:
                continue
            filtered.append(lesson)
        return filtered

    def _refresh_lesson_browser(self, *_args: object) -> None:
        filtered = self._filter_lessons()
        self.filtered_lessons = filtered
        topic = self._selected_topic()
        if topic == "All Topics":
            done = len(self.completed_ids)
            total = len(self.lesson_catalog)
            self.topic_summary.config(text=f"Showing {len(filtered)} lessons across all topics. Completed {done} of {total}.")
        else:
            total = len(self.topic_lookup.get(topic, []))
            done = sum(1 for lesson in self.topic_lookup.get(topic, []) if lesson["lesson_id"] in self.completed_ids)
            self.topic_summary.config(text=f"{topic}: {done}/{total} lessons complete. Showing {len(filtered)} lessons with current filters.")

        self.lesson_list.delete(0, tk.END)
        for lesson in filtered:
            state = "done" if lesson["lesson_id"] in self.completed_ids else "open"
            self.lesson_list.insert(tk.END, f"{lesson['topic_name']} | Stage {lesson['stage']:02d} | {state} | {lesson['title']}")

        if self.active_lesson and any(item["lesson_id"] == self.active_lesson["lesson_id"] for item in filtered):
            index = next(i for i, item in enumerate(filtered) if item["lesson_id"] == self.active_lesson["lesson_id"])
            self.lesson_list.selection_clear(0, tk.END)
            self.lesson_list.selection_set(index)
            self.lesson_list.activate(index)
        elif filtered:
            self.active_lesson = filtered[0]
            self.lesson_list.selection_set(0)
            self.lesson_list.activate(0)
        else:
            self.active_lesson = None

        self._render_lesson_detail(self.active_lesson)

    def _render_dashboard(self) -> None:
        self.dashboard_tab.reset()
        if not self.user:
            return

        total = len(self.lesson_catalog) or 1
        percent = int((self.user["completed_lessons"] / total) * 100)
        next_lesson = self._recommended_lesson()

        hero = tk.Frame(self.dashboard_tab.inner, bg="#102a43", padx=20, pady=20)
        hero.pack(fill="x", pady=(0, 14))
        tk.Label(hero, text=f"Welcome back, {self.user['username']}", bg="#102a43", fg="#f0f4f8", font=("Georgia", 24, "bold")).pack(anchor="w")
        tk.Label(hero, text=f"Next lesson to tackle: {next_lesson['title'] if next_lesson else 'No lesson available'}", bg="#102a43", fg="#c4d4e4", font=("Segoe UI", 11)).pack(anchor="w", pady=(6, 12))
        tk.Button(hero, text="Resume Learning", command=self._continue_learning, bg="#ef8354", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 11)).pack(anchor="w")

        stats_row = tk.Frame(self.dashboard_tab.inner, bg=self.colors["page"])
        stats_row.pack(fill="x", pady=(0, 14))
        for title, value, bg in [
            ("Current Level", str(self._level(self.user["xp"])), "#e5eff7"),
            ("Total XP", str(self.user["xp"]), "#fff0e3"),
            ("Completed Lessons", str(self.user["completed_lessons"]), "#e3f3ea"),
            ("Progress", f"{percent}%", "#efe5f7"),
        ]:
            card = tk.Frame(stats_row, bg=bg, padx=16, pady=16, highlightthickness=1, highlightbackground="#d7e3f0")
            card.pack(side="left", fill="both", expand=True, padx=6)
            tk.Label(card, text=title, bg=bg, fg=self.colors["muted"], font=("Segoe UI Semibold", 10)).pack(anchor="w")
            tk.Label(card, text=value, bg=bg, fg=self.colors["text"], font=("Georgia", 22, "bold")).pack(anchor="w", pady=(8, 0))

        roadmap = tk.Frame(self.dashboard_tab.inner, bg=self.colors["surface"], padx=18, pady=18, highlightthickness=1, highlightbackground=self.colors["border"])
        roadmap.pack(fill="both", expand=True)
        tk.Label(roadmap, text="Topic Roadmap", bg=self.colors["surface"], fg=self.colors["text"], font=("Georgia", 22, "bold")).pack(anchor="w")
        tk.Label(roadmap, text="Pick a topic and jump into the Learn tab without dealing with a cramped three-column layout.", bg=self.colors["surface"], fg=self.colors["muted"], font=("Segoe UI", 10), justify="left", wraplength=800).pack(anchor="w", pady=(6, 14))
        grid = tk.Frame(roadmap, bg=self.colors["surface"])
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        for index, topic in enumerate(sorted(self.topic_lookup)):
            lessons = self.topic_lookup[topic]
            done = sum(1 for lesson in lessons if lesson["lesson_id"] in self.completed_ids)
            card = tk.Frame(grid, bg="#fffaf4", padx=14, pady=14, highlightthickness=1, highlightbackground=self.colors["border"])
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=topic, bg="#fffaf4", fg=self.colors["text"], font=("Segoe UI Semibold", 12)).pack(anchor="w")
            tk.Label(card, text=f"{done}/{len(lessons)} lessons complete", bg="#fffaf4", fg=self.colors["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 10))
            bar = ttk.Progressbar(card, orient="horizontal", mode="determinate", maximum=max(len(lessons), 1))
            bar["value"] = done
            bar.pack(fill="x", pady=(0, 10))
            tk.Button(card, text="Open Topic In Learn Tab", command=lambda value=topic: self._jump_to_topic(value), bg=self.colors["shell_soft"], fg="white", relief="flat", padx=12, pady=8, font=("Segoe UI Semibold", 9)).pack(anchor="w")

    def _jump_to_topic(self, topic: str) -> None:
        self.topic_var.set(topic)
        self.notebook.select(self.learn_tab)
        self._refresh_lesson_browser()

    def _continue_learning(self) -> None:
        lesson = self._recommended_lesson()
        if lesson is None:
            return
        self.topic_var.set(lesson["topic_name"])
        self.notebook.select(self.learn_tab)
        self.active_lesson = lesson
        self._refresh_lesson_browser()

    def _on_lesson_select(self, _event: object) -> None:
        if not self.lesson_list.curselection():
            return
        self.active_lesson = self.filtered_lessons[self.lesson_list.curselection()[0]]
        self._render_lesson_detail(self.active_lesson)

    def _render_lesson_detail(self, lesson: Optional[Dict[str, Any]]) -> None:
        self.detail_scroll.reset()
        if lesson is None:
            box = tk.Frame(self.detail_scroll.inner, bg=self.colors["surface"], padx=18, pady=18)
            box.pack(fill="both", expand=True)
            tk.Label(box, text="No lesson matches the current filters.", bg=self.colors["surface"], fg=self.colors["text"], font=("Georgia", 20, "bold")).pack(anchor="w")
            return

        status = "Completed" if lesson["lesson_id"] in self.completed_ids else "Ready to complete"

        hero = tk.Frame(self.detail_scroll.inner, bg="#102a43", padx=18, pady=18)
        hero.pack(fill="x", pady=(0, 12))
        tk.Label(hero, text=lesson["title"], bg="#102a43", fg="#f0f4f8", font=("Georgia", 22, "bold"), wraplength=760, justify="left").pack(anchor="w")
        tk.Label(hero, text=f"{lesson['topic_name']} | Stage {lesson['stage']:02d} | {lesson['xp_reward']} XP | {status}", bg="#102a43", fg="#c4d4e4", font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))

        for title, body, bg, fg in [
            ("Overview", lesson["explanation"], self.colors["surface"], "#334e68"),
            ("Challenge", lesson["challenge"], "#fff8f1", "#664d1e"),
        ]:
            card = tk.Frame(self.detail_scroll.inner, bg=bg, padx=18, pady=18, highlightthickness=1, highlightbackground=self.colors["border"])
            card.pack(fill="x", pady=(0, 12))
            tk.Label(card, text=title, bg=bg, fg=self.colors["text"], font=("Georgia", 18, "bold")).pack(anchor="w")
            tk.Label(card, text=body, bg=bg, fg=fg, font=("Segoe UI", 11), wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))

        code_card = tk.Frame(self.detail_scroll.inner, bg=self.colors["code"], padx=18, pady=18, highlightthickness=1, highlightbackground="#1f2d3d")
        code_card.pack(fill="x", pady=(0, 12))
        tk.Label(code_card, text="Code Sample", bg=self.colors["code"], fg="#f0f4f8", font=("Georgia", 18, "bold")).pack(anchor="w")
        code_box = scrolledtext.ScrolledText(code_card, height=9, wrap="none", bg="#111b26", fg="#e5eff9", insertbackground="#e5eff9", relief="flat", font=("Consolas", 10))
        code_box.pack(fill="x", pady=(10, 0))
        code_box.insert("1.0", lesson["code_sample"])
        code_box.configure(state="disabled")

        quiz = tk.Frame(self.detail_scroll.inner, bg="#f7fbff", padx=18, pady=18, highlightthickness=1, highlightbackground=self.colors["border"])
        quiz.pack(fill="x")
        tk.Label(quiz, text="Quiz Checkpoint", bg="#f7fbff", fg=self.colors["text"], font=("Georgia", 18, "bold")).pack(anchor="w")
        tk.Label(quiz, text=lesson["quiz"]["prompt"], bg="#f7fbff", fg="#334e68", font=("Segoe UI", 11), wraplength=760, justify="left").pack(anchor="w", pady=(10, 12))
        self.answer_var.set(-1)
        for index, option in enumerate(lesson["quiz"]["options"]):
            tk.Radiobutton(quiz, text=option, variable=self.answer_var, value=index, bg="#f7fbff", fg="#102a43", selectcolor="#d9e9ff", anchor="w", justify="left", wraplength=720, font=("Segoe UI", 10)).pack(fill="x", pady=4)
        self.feedback_label = tk.Label(quiz, text="", bg="#f7fbff", fg="#486581", font=("Segoe UI", 10), wraplength=760, justify="left")
        self.feedback_label.pack(anchor="w", pady=(10, 0))
        tk.Button(quiz, text="Submit Answer", command=self._submit_answer, bg=self.colors["accent"], fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(12, 0))

    def _submit_answer(self) -> None:
        if self.active_lesson is None:
            return
        selected = self.answer_var.get()
        if selected < 0:
            messagebox.showinfo("Choose an answer", "Select one quiz option before submitting.")
            return
        try:
            result = self.api.submit_lesson(self.active_lesson["lesson_id"], selected)
        except RuntimeError as exc:
            messagebox.showerror("Submission failed", str(exc))
            return
        verdict = "Correct" if result["correct"] else "Not quite"
        self.feedback_label.config(
            text=f"{verdict}. XP gained: {result['xp_gained']}. New XP total: {result['new_xp']}.\n{result['explanation']}",
            fg="#1f7a3d" if result["correct"] else "#9c4221",
        )
        lesson_id = self.active_lesson["lesson_id"]
        self._refresh_data()
        if lesson_id in self.lesson_lookup:
            self.active_lesson = self.lesson_lookup[lesson_id]
            self._refresh_lesson_browser()

    def _render_leaderboard(self) -> None:
        for row in self.board_table.get_children():
            self.board_table.delete(row)
        self.board_table.tag_configure("odd", background="#fffaf4")
        self.board_table.tag_configure("even", background="#f5eee5")
        for index, leader in enumerate(self.leaders):
            tag = "even" if index % 2 else "odd"
            self.board_table.insert("", "end", values=(leader["rank"], leader["username"], leader["xp"], leader["completed_lessons"]), tags=(tag,))


def run_client(base_url: str) -> None:
    app = TeachingApp(ApiClient(base_url))
    app.mainloop()
