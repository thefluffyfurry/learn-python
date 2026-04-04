"""Tkinter desktop UI for the Python teaching app."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional
from urllib import error, request


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: Optional[str] = None

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
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            message = exc.read().decode("utf-8")
            try:
                detail = json.loads(message).get("error", message)
            except json.JSONDecodeError:
                detail = message or str(exc)
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


class TeachingApp(tk.Tk):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.title("PyQuest Academy")
        self.geometry("1360x820")
        self.minsize(1200, 760)
        self.configure(bg="#0d1b2a")

        self.user: Optional[Dict[str, Any]] = None
        self.leaders: List[Dict[str, Any]] = []
        self.lesson_catalog: List[Dict[str, Any]] = []
        self.topic_lookup: Dict[str, List[Dict[str, Any]]] = {}
        self.lesson_lookup: Dict[str, Dict[str, Any]] = {}
        self.filtered_topic_names: List[str] = []
        self.filtered_lessons: List[Dict[str, Any]] = []
        self.active_topic_name: Optional[str] = None
        self.active_lesson: Optional[Dict[str, Any]] = None
        self.answer_var = tk.IntVar(value=-1)
        self.search_var = tk.StringVar()

        self._build_styles()
        self._build_layout()
        self._show_auth()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#bcccdc", background="#ef8354")

    def _build_layout(self) -> None:
        self.header = tk.Frame(self, bg="#102a43", height=72)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.title_label = tk.Label(
            self.header,
            text="PyQuest Academy",
            fg="#f0f4f8",
            bg="#102a43",
            font=("Georgia", 24, "bold"),
        )
        self.title_label.pack(side="left", padx=18)

        self.status_label = tk.Label(
            self.header,
            text="Offline",
            fg="#9fb3c8",
            bg="#102a43",
            font=("Segoe UI", 11),
        )
        self.status_label.pack(side="right", padx=18)

        self.body = tk.Frame(self, bg="#0d1b2a")
        self.body.pack(fill="both", expand=True, padx=16, pady=16)

        self.auth_frame = tk.Frame(self.body, bg="#1b263b", padx=28, pady=28)
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.main_frame = tk.Frame(self.body, bg="#0d1b2a")

        self.nav_panel = tk.Frame(self.main_frame, width=330, bg="#1b263b", padx=14, pady=14)
        self.nav_panel.pack(side="left", fill="y")
        self.nav_panel.pack_propagate(False)

        self.lesson_panel = tk.Frame(self.main_frame, width=360, bg="#243b53", padx=14, pady=14)
        self.lesson_panel.pack(side="left", fill="y")
        self.lesson_panel.pack_propagate(False)

        self.content = tk.Frame(self.main_frame, bg="#f8fafc", padx=18, pady=18)
        self.content.pack(side="left", fill="both", expand=True)

        self._build_auth_widgets()
        self._build_navigation()
        self._build_content()

    def _build_auth_widgets(self) -> None:
        tk.Label(
            self.auth_frame,
            text="Learn Python. Earn XP. Climb the leaderboard.",
            bg="#1b263b",
            fg="#f0f4f8",
            font=("Georgia", 20, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        tk.Label(
            self.auth_frame,
            text=f"Create an account or log in to sync progress with {self.api.base_url}.",
            bg="#1b263b",
            fg="#bcccdc",
            font=("Segoe UI", 11),
            justify="left",
            wraplength=540,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))

        tk.Label(self.auth_frame, text="Username", bg="#1b263b", fg="#f0f4f8", font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w")
        self.username_entry = tk.Entry(self.auth_frame, font=("Segoe UI", 11), width=28)
        self.username_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        tk.Label(self.auth_frame, text="Password", bg="#1b263b", fg="#f0f4f8", font=("Segoe UI", 11)).grid(row=4, column=0, sticky="w")
        self.password_entry = tk.Entry(self.auth_frame, show="*", font=("Segoe UI", 11), width=28)
        self.password_entry.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 18))

        tk.Button(
            self.auth_frame,
            text="Log In",
            command=self._login,
            bg="#3e7cb1",
            fg="white",
            activebackground="#2b6a99",
            relief="flat",
            padx=14,
            pady=10,
            font=("Segoe UI Semibold", 11),
        ).grid(row=6, column=0, sticky="ew", padx=(0, 8))

        tk.Button(
            self.auth_frame,
            text="Sign Up",
            command=self._signup,
            bg="#ef8354",
            fg="white",
            activebackground="#db6d3f",
            relief="flat",
            padx=14,
            pady=10,
            font=("Segoe UI Semibold", 11),
        ).grid(row=6, column=1, sticky="ew")

    def _build_navigation(self) -> None:
        self.user_card = tk.Label(
            self.nav_panel,
            text="Sign in to start",
            justify="left",
            anchor="w",
            bg="#1b263b",
            fg="#f0f4f8",
            font=("Segoe UI", 12),
        )
        self.user_card.pack(fill="x", pady=(0, 12))

        self.progress_bar = ttk.Progressbar(self.nav_panel, orient="horizontal", mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 14))

        button_row = tk.Frame(self.nav_panel, bg="#1b263b")
        button_row.pack(fill="x", pady=(0, 14))
        for label, command in [
            ("Dashboard", self._show_dashboard),
            ("Leaderboard", self._show_leaderboard),
            ("Refresh", self._refresh_data),
        ]:
            tk.Button(
                button_row,
                text=label,
                command=command,
                bg="#486581",
                fg="white",
                relief="flat",
                padx=10,
                pady=8,
                font=("Segoe UI Semibold", 9),
            ).pack(side="left", expand=True, fill="x", padx=3)

        tk.Label(
            self.nav_panel,
            text="Find Lessons",
            bg="#1b263b",
            fg="#d9e2ec",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")

        search_entry = tk.Entry(
            self.nav_panel,
            textvariable=self.search_var,
            font=("Segoe UI", 11),
            relief="flat",
        )
        search_entry.pack(fill="x", pady=(6, 12))
        self.search_var.trace_add("write", self._on_search_change)

        tk.Label(
            self.nav_panel,
            text="Topics",
            bg="#1b263b",
            fg="#d9e2ec",
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", pady=(4, 8))

        self.topic_list = tk.Listbox(
            self.nav_panel,
            bg="#f0f4f8",
            fg="#102a43",
            font=("Segoe UI", 10),
            activestyle="none",
            height=16,
            relief="flat",
        )
        self.topic_list.pack(fill="both", expand=True)
        self.topic_list.bind("<<ListboxSelect>>", self._on_topic_select)

        tk.Label(
            self.lesson_panel,
            text="Lesson Path",
            bg="#243b53",
            fg="#f0f4f8",
            font=("Georgia", 18, "bold"),
        ).pack(anchor="w")

        self.topic_meta_label = tk.Label(
            self.lesson_panel,
            text="Pick a topic to see its lesson path.",
            bg="#243b53",
            fg="#bcccdc",
            justify="left",
            wraplength=310,
            font=("Segoe UI", 10),
        )
        self.topic_meta_label.pack(fill="x", pady=(4, 12))

        self.lesson_list = tk.Listbox(
            self.lesson_panel,
            bg="#f8fafc",
            fg="#102a43",
            font=("Consolas", 10),
            activestyle="none",
            relief="flat",
        )
        self.lesson_list.pack(fill="both", expand=True)
        self.lesson_list.bind("<<ListboxSelect>>", self._on_lesson_select)

    def _build_content(self) -> None:
        self.hero_label = tk.Label(
            self.content,
            text="Dashboard",
            bg="#f8fafc",
            fg="#102a43",
            anchor="w",
            justify="left",
            font=("Georgia", 26, "bold"),
        )
        self.hero_label.pack(fill="x", pady=(0, 8))

        self.sub_label = tk.Label(
            self.content,
            text="",
            bg="#f8fafc",
            fg="#486581",
            anchor="w",
            justify="left",
            font=("Segoe UI", 11),
        )
        self.sub_label.pack(fill="x", pady=(0, 12))

        self.dashboard_text = tk.Text(
            self.content,
            wrap="word",
            bg="#ffffff",
            fg="#102a43",
            relief="flat",
            font=("Segoe UI", 11),
            padx=18,
            pady=18,
        )
        self.dashboard_text.pack(fill="both", expand=True)

    def _show_auth(self) -> None:
        self.main_frame.pack_forget()
        self.auth_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.status_label.config(text="Authentication required")

    def _show_main(self) -> None:
        self.auth_frame.place_forget()
        self.main_frame.pack(fill="both", expand=True)

    def _signup(self) -> None:
        self._authenticate("signup")

    def _login(self) -> None:
        self._authenticate("login")

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
        self._show_main()
        self._show_dashboard()

    def _group_lessons(self) -> None:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for lesson in self.lesson_catalog:
            grouped.setdefault(lesson["topic_name"], []).append(lesson)
        for lessons in grouped.values():
            lessons.sort(key=lambda item: item["stage"])
        self.topic_lookup = dict(sorted(grouped.items()))
        self.lesson_lookup = {lesson["lesson_id"]: lesson for lesson in self.lesson_catalog}

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
        self.user = profile
        self.leaders = leaders
        self.lesson_catalog = lessons
        self._group_lessons()
        self.status_label.config(text=f"Connected as {profile['username']}")
        total_lessons = len(self.lesson_catalog) or 1
        percent = int((profile["completed_lessons"] / total_lessons) * 100)
        self.progress_bar["value"] = percent
        self.user_card.config(
            text=(
                f"{profile['username']}\n"
                f"XP: {profile['xp']}\n"
                f"Completed: {profile['completed_lessons']} / {total_lessons}\n"
                f"Progress: {percent}%"
            )
        )
        self._populate_topics()

    def _populate_topics(self) -> None:
        query = self.search_var.get().strip().lower()
        self.topic_list.delete(0, tk.END)
        self.filtered_topic_names = []
        completed_ids = set(self.user["completed_lesson_ids"]) if self.user else set()
        for topic_name, lessons in self.topic_lookup.items():
            if query and not any(
                query in topic_name.lower() or query in lesson["title"].lower() or query in lesson["lesson_id"].lower()
                for lesson in lessons
            ):
                continue
            done_count = sum(1 for lesson in lessons if lesson["lesson_id"] in completed_ids)
            self.filtered_topic_names.append(topic_name)
            self.topic_list.insert(tk.END, f"{topic_name}  ({done_count}/{len(lessons)})")

        if not self.filtered_topic_names:
            self.active_topic_name = None
            self.lesson_list.delete(0, tk.END)
            self.topic_meta_label.config(text="No topics match this search.")
            return

        if self.active_topic_name not in self.filtered_topic_names:
            self.active_topic_name = self.filtered_topic_names[0]

        topic_index = self.filtered_topic_names.index(self.active_topic_name)
        self.topic_list.selection_clear(0, tk.END)
        self.topic_list.selection_set(topic_index)
        self.topic_list.activate(topic_index)
        self._populate_lessons_for_topic(self.active_topic_name)

    def _populate_lessons_for_topic(self, topic_name: str) -> None:
        query = self.search_var.get().strip().lower()
        completed_ids = set(self.user["completed_lesson_ids"]) if self.user else set()
        lessons = self.topic_lookup.get(topic_name, [])
        self.filtered_lessons = [
            lesson
            for lesson in lessons
            if not query
            or query in lesson["title"].lower()
            or query in lesson["lesson_id"].lower()
            or query in lesson["summary"].lower()
        ]
        self.lesson_list.delete(0, tk.END)
        for lesson in self.filtered_lessons:
            status = "done" if lesson["lesson_id"] in completed_ids else "open"
            self.lesson_list.insert(
                tk.END,
                f"Stage {lesson['stage']:02d} | {status:<4} | {lesson['xp_reward']:>2} XP | {lesson['title']}",
            )

        total = len(lessons)
        shown = len(self.filtered_lessons)
        completed = sum(1 for lesson in lessons if lesson["lesson_id"] in completed_ids)
        self.topic_meta_label.config(
            text=(
                f"{topic_name}\n"
                f"{completed}/{total} lessons completed"
                + (f"\nShowing {shown} matching lessons" if query else "")
            )
        )

        next_lesson = next((lesson for lesson in lessons if lesson["lesson_id"] not in completed_ids), lessons[0] if lessons else None)
        selected_lesson = None
        if self.active_lesson and self.active_lesson.get("topic_name") == topic_name:
            selected_lesson = next(
                (lesson for lesson in self.filtered_lessons if lesson["lesson_id"] == self.active_lesson["lesson_id"]),
                None,
            )
        if selected_lesson is None:
            selected_lesson = next_lesson if next_lesson in self.filtered_lessons else (self.filtered_lessons[0] if self.filtered_lessons else None)

        if selected_lesson is not None:
            self.active_lesson = selected_lesson
            selection_index = self.filtered_lessons.index(selected_lesson)
            self.lesson_list.selection_clear(0, tk.END)
            self.lesson_list.selection_set(selection_index)
            self.lesson_list.activate(selection_index)
            self._show_lesson(selected_lesson)

    def _on_search_change(self, *_args: str) -> None:
        if not self.topic_lookup:
            return
        self._populate_topics()

    def _show_dashboard(self) -> None:
        self.hero_label.config(text="Dashboard")
        total = len(self.lesson_catalog)
        completed = self.user["completed_lessons"] if self.user else 0
        remaining = max(total - completed, 0)
        completed_ids = set(self.user["completed_lesson_ids"]) if self.user else set()
        topic_lines = []
        for topic_name, lessons in list(self.topic_lookup.items())[:6]:
            done = sum(1 for lesson in lessons if lesson["lesson_id"] in completed_ids)
            topic_lines.append(f"- {topic_name}: {done}/{len(lessons)} complete")
        self.sub_label.config(text="Browse by topic, search by keyword, and continue from the next open lesson.")
        self.dashboard_text.delete("1.0", tk.END)
        self.dashboard_text.insert(
            tk.END,
            (
                "PyQuest Academy now uses a guided lesson path instead of one long lesson list.\n\n"
                f"Total lessons: {total}\n"
                f"Completed lessons: {completed}\n"
                f"Remaining lessons: {remaining}\n"
                f"Current XP: {self.user['xp'] if self.user else 0}\n\n"
                "How to use the new system:\n"
                "- Pick a topic in the left column.\n"
                "- Use search to narrow topics and lessons.\n"
                "- The middle column shows the lesson path for that topic.\n"
                "- The app auto-selects the next unfinished lesson when possible.\n\n"
                "Topic progress:\n"
                + "\n".join(topic_lines)
            ),
        )

    def _show_leaderboard(self) -> None:
        self.hero_label.config(text="Leaderboard")
        self.sub_label.config(text="Top learners ranked by XP and completed lessons.")
        self.dashboard_text.delete("1.0", tk.END)
        lines = []
        for leader in self.leaders:
            lines.append(
                f"#{leader['rank']:02d}  {leader['username']:<18}  XP {leader['xp']:<5}  Lessons {leader['completed_lessons']}"
            )
        self.dashboard_text.insert(tk.END, "\n".join(lines) if lines else "No leaderboard data yet.")

    def _on_topic_select(self, _event: object) -> None:
        if not self.topic_list.curselection():
            return
        self.active_topic_name = self.filtered_topic_names[self.topic_list.curselection()[0]]
        self._populate_lessons_for_topic(self.active_topic_name)

    def _on_lesson_select(self, _event: object) -> None:
        if not self.lesson_list.curselection():
            return
        lesson = self.filtered_lessons[self.lesson_list.curselection()[0]]
        self.active_lesson = lesson
        self._show_lesson(lesson)

    def _show_lesson(self, lesson: Dict[str, Any]) -> None:
        self.active_lesson = lesson
        self.answer_var.set(-1)
        self.hero_label.config(text=lesson["title"])
        self.sub_label.config(text=f"{lesson['topic_name']} | Stage {lesson['stage']} | Reward {lesson['xp_reward']} XP")
        self.dashboard_text.delete("1.0", tk.END)
        self.dashboard_text.insert(
            tk.END,
            (
                f"{lesson['summary']}\n\n"
                f"{lesson['explanation']}\n\n"
                "Code sample:\n"
                f"{lesson['code_sample']}\n\n"
                "Challenge:\n"
                f"{lesson['challenge']}\n\n"
                "Quiz:\n"
                f"{lesson['quiz']['prompt']}\n\n"
            ),
        )
        for index, option in enumerate(lesson["quiz"]["options"]):
            radio = tk.Radiobutton(
                self.dashboard_text,
                text=option,
                variable=self.answer_var,
                value=index,
                bg="#ffffff",
                fg="#102a43",
                selectcolor="#d9e2ec",
                font=("Segoe UI", 10),
                anchor="w",
                justify="left",
            )
            self.dashboard_text.window_create(tk.END, window=radio)
            self.dashboard_text.insert(tk.END, "\n")
        submit = tk.Button(
            self.dashboard_text,
            text="Submit Answer",
            command=self._submit_answer,
            bg="#3e7cb1",
            fg="white",
            relief="flat",
            padx=12,
            pady=8,
            font=("Segoe UI Semibold", 10),
        )
        self.dashboard_text.insert(tk.END, "\n")
        self.dashboard_text.window_create(tk.END, window=submit)

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
        messagebox.showinfo(
            "Lesson result",
            f"{verdict}\nXP gained: {result['xp_gained']}\nNew XP total: {result['new_xp']}\n\n{result['explanation']}",
        )
        current_topic = self.active_lesson["topic_name"]
        current_lesson_id = self.active_lesson["lesson_id"]
        self._refresh_data()
        self.active_topic_name = current_topic
        self.active_lesson = self.lesson_lookup.get(current_lesson_id, self.active_lesson)
        self._populate_topics()


def run_client(base_url: str) -> None:
    app = TeachingApp(ApiClient(base_url))
    app.mainloop()
