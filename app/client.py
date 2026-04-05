"""Tkinter desktop UI for the Python teaching app."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional
from urllib import error, request


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

    def is_local_mode(self) -> bool:
        normalized = self.base_url.lower()
        return normalized.startswith("http://127.0.0.1") or normalized.startswith("http://localhost")

    def auth_message(self) -> str:
        if self.is_local_mode():
            return (
                "Local mode is active. Accounts are saved in the local "
                "teaching_app.db file for this project, so they do not sync "
                "to another computer unless that database file is copied too."
            )
        return f"Sign in to sync your lessons, XP, and leaderboard data with {self.base_url}."

    def _decode_json(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            trimmed = raw.lstrip().lower()
            if trimmed.startswith("<html") or "<script" in trimmed:
                raise RuntimeError(
                    "The hosted server returned an HTML page instead of API data. "
                    "Your web host is blocking desktop app requests, so online sign-in is unavailable right now."
                ) from exc
            raise RuntimeError(f"The server at {self.base_url} returned an invalid response.") from exc

    def _call(self, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=8) as response:
                raw = response.read().decode("utf-8")
                return self._decode_json(raw)
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                detail = self._decode_json(raw).get("error", raw)
            except RuntimeError as parse_error:
                detail = str(parse_error)
            raise RuntimeError(detail) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Cannot reach the teaching server at {self.base_url}.") from exc

    def signup(self, username: str, password: str) -> Dict[str, Any]:
        result = self._call("/signup", "POST", {"username": username, "password": password})
        self.token = result["token"]
        return result

    def login(self, username: str, password: str) -> Dict[str, Any]:
        result = self._call("/login", "POST", {"username": username, "password": password})
        self.token = result["token"]
        return result

    def lessons(self) -> List[Dict[str, Any]]:
        return self._call("/lessons")["lessons"]

    def profile(self) -> Dict[str, Any]:
        return self._call("/profile")

    def leaderboard(self) -> List[Dict[str, Any]]:
        return self._call("/leaderboard")["leaders"]

    def submit_lesson(self, lesson_id: str, selected_index: int) -> Dict[str, Any]:
        return self._call("/submit-lesson", "POST", {"lesson_id": lesson_id, "selected_index": selected_index})


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
        self.title("PyQuest Academy")
        self.geometry("1180x780")
        self.minsize(860, 620)
        self.configure(bg="#0b1824")

        self.user: Optional[Dict[str, Any]] = None
        self.leaders: List[Dict[str, Any]] = []
        self.lesson_catalog: List[Dict[str, Any]] = []
        self.topic_lookup: Dict[str, List[Dict[str, Any]]] = {}
        self.lesson_lookup: Dict[str, Dict[str, Any]] = {}
        self.completed_ids: set[str] = set()
        self.active_lesson: Optional[Dict[str, Any]] = None

        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self.topic_var = tk.StringVar(value="All Topics")
        self.answer_var = tk.IntVar(value=-1)

        self._build_styles()
        self._build_shell()
        self._show_auth()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background="#dce7f3", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(14, 8))
        style.configure("Board.Treeview", rowheight=30, background="#ffffff", fieldbackground="#ffffff", foreground="#102a43")
        style.map("Board.Treeview", background=[("selected", "#d9e9ff")], foreground=[("selected", "#102a43")])
        style.configure("TProgressbar", troughcolor="#d9e2ec", background="#ef8354")

    def _build_shell(self) -> None:
        self.header = tk.Frame(self, bg="#12314d", height=74)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)
        title = tk.Frame(self.header, bg="#12314d")
        title.pack(side="left", padx=18)
        tk.Label(title, text="PyQuest Academy", bg="#12314d", fg="#f0f4f8", font=("Georgia", 24, "bold")).pack(anchor="w")
        tk.Label(title, text="Python lessons, progress tracking, and leaderboard in a cleaner layout.", bg="#12314d", fg="#b8c8d8", font=("Segoe UI", 10)).pack(anchor="w")
        self.status_chip = tk.Label(self.header, text="Offline", bg="#1f4f76", fg="#f0f4f8", padx=14, pady=8, font=("Segoe UI Semibold", 10))
        self.status_chip.pack(side="right", padx=18)

        self.body = tk.Frame(self, bg="#0b1824")
        self.body.pack(fill="both", expand=True, padx=14, pady=14)

        self.auth_frame = tk.Frame(self.body, bg="#14273c", padx=28, pady=28)
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.app_frame = tk.Frame(self.body, bg="#dce7f3")

        self._build_auth()
        self._build_app()

    def _build_auth(self) -> None:
        tk.Label(self.auth_frame, text="Launch your Python journey", bg="#14273c", fg="#f0f4f8", font=("Georgia", 24, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        tk.Label(
            self.auth_frame,
            text=self.api.auth_message(),
            bg="#14273c",
            fg="#c4d4e4",
            font=("Segoe UI", 11),
            justify="left",
            wraplength=540,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))
        tk.Label(self.auth_frame, text="Username", bg="#14273c", fg="#f0f4f8", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w")
        self.username_entry = tk.Entry(self.auth_frame, font=("Segoe UI", 12), relief="flat")
        self.username_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12), ipady=6)
        tk.Label(self.auth_frame, text="Password", bg="#14273c", fg="#f0f4f8", font=("Segoe UI", 11)).grid(row=4, column=0, sticky="w")
        self.password_entry = tk.Entry(self.auth_frame, show="*", font=("Segoe UI", 12), relief="flat")
        self.password_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 18), ipady=6)
        tk.Button(self.auth_frame, text="Log In", command=self._login, bg="#3e7cb1", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 11)).grid(row=6, column=0, sticky="ew", padx=(0, 8))
        tk.Button(self.auth_frame, text="Create Account", command=self._signup, bg="#ef8354", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 11)).grid(row=6, column=1, sticky="ew")

    def _build_app(self) -> None:
        summary = tk.Frame(self.app_frame, bg="#eef4fb", padx=16, pady=12)
        summary.pack(fill="x")

        identity = tk.Frame(summary, bg="#eef4fb")
        identity.pack(side="left", fill="x", expand=True)
        self.user_name = tk.Label(identity, text="Not signed in", bg="#eef4fb", fg="#102a43", font=("Georgia", 20, "bold"))
        self.user_name.pack(anchor="w")
        self.user_meta = tk.Label(identity, text="", bg="#eef4fb", fg="#486581", font=("Segoe UI", 10), justify="left")
        self.user_meta.pack(anchor="w", pady=(2, 8))
        self.progress = ttk.Progressbar(identity, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 2))

        actions = tk.Frame(summary, bg="#eef4fb")
        actions.pack(side="right")
        tk.Button(actions, text="Continue Learning", command=self._continue_learning, bg="#ef8354", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 10)).pack(side="left", padx=4)
        tk.Button(actions, text="Refresh", command=self._refresh_data, bg="#3e7cb1", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 10)).pack(side="left", padx=4)

        self.notebook = ttk.Notebook(self.app_frame)
        self.notebook.pack(fill="both", expand=True, pady=(12, 0))

        self.dashboard_tab = ScrollFrame(self.notebook, "#dce7f3")
        self.learn_tab = tk.Frame(self.notebook, bg="#dce7f3")
        self.board_tab = tk.Frame(self.notebook, bg="#dce7f3")

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.learn_tab, text="Learn")
        self.notebook.add(self.board_tab, text="Leaderboard")

        self._build_learn_tab()
        self._build_board_tab()

    def _build_learn_tab(self) -> None:
        controls = tk.Frame(self.learn_tab, bg="#dce7f3", padx=10, pady=10)
        controls.pack(fill="x")
        tk.Label(controls, text="Search", bg="#dce7f3", fg="#334e68", font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        tk.Entry(controls, textvariable=self.search_var, font=("Segoe UI", 11), relief="flat").grid(row=1, column=0, sticky="ew", padx=(0, 10), ipady=4)
        tk.Label(controls, text="Filter", bg="#dce7f3", fg="#334e68", font=("Segoe UI Semibold", 10)).grid(row=0, column=1, sticky="w")
        filter_box = ttk.Combobox(controls, textvariable=self.filter_var, values=["All", "Open", "Done"], state="readonly", width=10)
        filter_box.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        tk.Label(controls, text="Topic", bg="#dce7f3", fg="#334e68", font=("Segoe UI Semibold", 10)).grid(row=0, column=2, sticky="w")
        self.topic_box = ttk.Combobox(controls, textvariable=self.topic_var, state="readonly")
        self.topic_box.grid(row=1, column=2, sticky="ew", padx=(0, 10))
        tk.Button(controls, text="Open Next", command=self._continue_learning, bg="#ef8354", fg="white", relief="flat", padx=14, pady=8, font=("Segoe UI Semibold", 10)).grid(row=1, column=3, sticky="e")
        controls.grid_columnconfigure(0, weight=2)
        controls.grid_columnconfigure(2, weight=2)
        self.search_var.trace_add("write", self._refresh_lesson_browser)
        filter_box.bind("<<ComboboxSelected>>", self._refresh_lesson_browser)
        self.topic_box.bind("<<ComboboxSelected>>", self._refresh_lesson_browser)

        self.topic_summary = tk.Label(self.learn_tab, text="", bg="#dce7f3", fg="#486581", font=("Segoe UI", 10), anchor="w", justify="left")
        self.topic_summary.pack(fill="x", padx=12, pady=(0, 10))

        panes = ttk.PanedWindow(self.learn_tab, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = tk.Frame(panes, bg="#ffffff", padx=10, pady=10)
        right = tk.Frame(panes, bg="#ffffff", padx=10, pady=10)
        panes.add(left, weight=1)
        panes.add(right, weight=3)

        tk.Label(left, text="Lesson List", bg="#ffffff", fg="#102a43", font=("Georgia", 18, "bold")).pack(anchor="w")
        self.lesson_list = tk.Listbox(left, bg="#f8fbff", fg="#102a43", font=("Segoe UI", 10), activestyle="none")
        self.lesson_list.pack(fill="both", expand=True, pady=(10, 0))
        self.lesson_list.bind("<<ListboxSelect>>", self._on_lesson_select)

        self.detail_scroll = ScrollFrame(right, "#ffffff")
        self.detail_scroll.pack(fill="both", expand=True)

    def _build_board_tab(self) -> None:
        tk.Label(self.board_tab, text="Top learners ranked by XP and completed lessons.", bg="#dce7f3", fg="#486581", font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(12, 8))
        self.board_table = ttk.Treeview(self.board_tab, columns=("rank", "username", "xp", "done"), show="headings", style="Board.Treeview")
        for column, label, width in [("rank", "Rank", 90), ("username", "Learner", 260), ("xp", "XP", 140), ("done", "Completed Lessons", 180)]:
            self.board_table.heading(column, text=label)
            self.board_table.column(column, width=width, anchor="center")
        self.board_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _show_auth(self) -> None:
        self.app_frame.pack_forget()
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.status_chip.config(text="Local account mode" if self.api.is_local_mode() else "Authentication required")

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
        self.status_chip.config(text=f"Connected as {profile['username']}")
        self.user_name.config(text=profile["username"])
        self.user_meta.config(
            text=(
                f"Level {self._level(profile['xp'])}  |  XP {profile['xp']}  |  "
                f"Completed {profile['completed_lessons']} / {total}  |  Progress {percent}%"
            )
        )
        self.progress["value"] = percent

        self.topic_box["values"] = self._topic_choices()
        if self.topic_var.get() not in self.topic_box["values"]:
            self.topic_var.set("All Topics")

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

        stats_row = tk.Frame(self.dashboard_tab.inner, bg="#dce7f3")
        stats_row.pack(fill="x", pady=(0, 14))
        for title, value, bg in [
            ("Current Level", str(self._level(self.user["xp"])), "#e3f2fd"),
            ("Total XP", str(self.user["xp"]), "#fff4e8"),
            ("Completed Lessons", str(self.user["completed_lessons"]), "#e9f8ef"),
            ("Progress", f"{percent}%", "#f3ebff"),
        ]:
            card = tk.Frame(stats_row, bg=bg, padx=16, pady=16, highlightthickness=1, highlightbackground="#d7e3f0")
            card.pack(side="left", fill="both", expand=True, padx=6)
            tk.Label(card, text=title, bg=bg, fg="#486581", font=("Segoe UI Semibold", 10)).pack(anchor="w")
            tk.Label(card, text=value, bg=bg, fg="#102a43", font=("Georgia", 22, "bold")).pack(anchor="w", pady=(8, 0))

        roadmap = tk.Frame(self.dashboard_tab.inner, bg="#ffffff", padx=18, pady=18, highlightthickness=1, highlightbackground="#d7e3f0")
        roadmap.pack(fill="both", expand=True)
        tk.Label(roadmap, text="Topic Roadmap", bg="#ffffff", fg="#102a43", font=("Georgia", 22, "bold")).pack(anchor="w")
        tk.Label(roadmap, text="Pick a topic and jump into the Learn tab without dealing with a cramped three-column layout.", bg="#ffffff", fg="#486581", font=("Segoe UI", 10), justify="left", wraplength=800).pack(anchor="w", pady=(6, 14))
        grid = tk.Frame(roadmap, bg="#ffffff")
        grid.pack(fill="both", expand=True)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        for index, topic in enumerate(sorted(self.topic_lookup)):
            lessons = self.topic_lookup[topic]
            done = sum(1 for lesson in lessons if lesson["lesson_id"] in self.completed_ids)
            card = tk.Frame(grid, bg="#f8fbff", padx=14, pady=14, highlightthickness=1, highlightbackground="#d7e3f0")
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=topic, bg="#f8fbff", fg="#102a43", font=("Segoe UI Semibold", 12)).pack(anchor="w")
            tk.Label(card, text=f"{done}/{len(lessons)} lessons complete", bg="#f8fbff", fg="#486581", font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 10))
            bar = ttk.Progressbar(card, orient="horizontal", mode="determinate", maximum=max(len(lessons), 1))
            bar["value"] = done
            bar.pack(fill="x", pady=(0, 10))
            tk.Button(card, text="Open Topic In Learn Tab", command=lambda value=topic: self._jump_to_topic(value), bg="#3e7cb1", fg="white", relief="flat", padx=12, pady=8, font=("Segoe UI Semibold", 9)).pack(anchor="w")

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
            box = tk.Frame(self.detail_scroll.inner, bg="#ffffff", padx=18, pady=18)
            box.pack(fill="both", expand=True)
            tk.Label(box, text="No lesson matches the current filters.", bg="#ffffff", fg="#102a43", font=("Georgia", 20, "bold")).pack(anchor="w")
            return

        status = "Completed" if lesson["lesson_id"] in self.completed_ids else "Ready to complete"

        hero = tk.Frame(self.detail_scroll.inner, bg="#102a43", padx=18, pady=18)
        hero.pack(fill="x", pady=(0, 12))
        tk.Label(hero, text=lesson["title"], bg="#102a43", fg="#f0f4f8", font=("Georgia", 22, "bold"), wraplength=760, justify="left").pack(anchor="w")
        tk.Label(hero, text=f"{lesson['topic_name']} | Stage {lesson['stage']:02d} | {lesson['xp_reward']} XP | {status}", bg="#102a43", fg="#c4d4e4", font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 0))

        for title, body, bg, fg in [
            ("Overview", lesson["explanation"], "#ffffff", "#334e68"),
            ("Challenge", lesson["challenge"], "#fff8f1", "#664d1e"),
        ]:
            card = tk.Frame(self.detail_scroll.inner, bg=bg, padx=18, pady=18, highlightthickness=1, highlightbackground="#d7e3f0")
            card.pack(fill="x", pady=(0, 12))
            tk.Label(card, text=title, bg=bg, fg="#102a43", font=("Georgia", 18, "bold")).pack(anchor="w")
            tk.Label(card, text=body, bg=bg, fg=fg, font=("Segoe UI", 11), wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))

        code_card = tk.Frame(self.detail_scroll.inner, bg="#0f1720", padx=18, pady=18, highlightthickness=1, highlightbackground="#1f2d3d")
        code_card.pack(fill="x", pady=(0, 12))
        tk.Label(code_card, text="Code Sample", bg="#0f1720", fg="#f0f4f8", font=("Georgia", 18, "bold")).pack(anchor="w")
        code_box = scrolledtext.ScrolledText(code_card, height=9, wrap="none", bg="#111b26", fg="#e5eff9", insertbackground="#e5eff9", relief="flat", font=("Consolas", 10))
        code_box.pack(fill="x", pady=(10, 0))
        code_box.insert("1.0", lesson["code_sample"])
        code_box.configure(state="disabled")

        quiz = tk.Frame(self.detail_scroll.inner, bg="#f7fbff", padx=18, pady=18, highlightthickness=1, highlightbackground="#d7e3f0")
        quiz.pack(fill="x")
        tk.Label(quiz, text="Quiz Checkpoint", bg="#f7fbff", fg="#102a43", font=("Georgia", 18, "bold")).pack(anchor="w")
        tk.Label(quiz, text=lesson["quiz"]["prompt"], bg="#f7fbff", fg="#334e68", font=("Segoe UI", 11), wraplength=760, justify="left").pack(anchor="w", pady=(10, 12))
        self.answer_var.set(-1)
        for index, option in enumerate(lesson["quiz"]["options"]):
            tk.Radiobutton(quiz, text=option, variable=self.answer_var, value=index, bg="#f7fbff", fg="#102a43", selectcolor="#d9e9ff", anchor="w", justify="left", wraplength=720, font=("Segoe UI", 10)).pack(fill="x", pady=4)
        self.feedback_label = tk.Label(quiz, text="", bg="#f7fbff", fg="#486581", font=("Segoe UI", 10), wraplength=760, justify="left")
        self.feedback_label.pack(anchor="w", pady=(10, 0))
        tk.Button(quiz, text="Submit Answer", command=self._submit_answer, bg="#ef8354", fg="white", relief="flat", padx=14, pady=10, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(12, 0))

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
        for leader in self.leaders:
            self.board_table.insert("", "end", values=(leader["rank"], leader["username"], leader["xp"], leader["completed_lessons"]))


def run_client(base_url: str) -> None:
    app = TeachingApp(ApiClient(base_url))
    app.mainloop()
