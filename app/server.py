"""HTTP API server with SQLite persistence."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.content import LESSON_MAP, LESSONS
from app.runtime import app_root


APP_ROOT = app_root()


class TeachingServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8123, db_path: Optional[Path] = None) -> None:
        self.host = host
        self.port = port
        self.db_path = Path(db_path) if db_path is not None else APP_ROOT / "teaching_app.db"
        if not self.db_path.is_absolute():
            self.db_path = APP_ROOT / self.db_path
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS lesson_progress (
                    user_id INTEGER NOT NULL,
                    lesson_id TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(user_id, lesson_id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _user_from_token(self, token: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT users.*
                FROM users
                JOIN sessions ON sessions.user_id = users.id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

    def signup(self, username: str, password: str) -> Dict[str, Any]:
        if len(username.strip()) < 3 or len(password) < 4:
            raise ValueError("Username must be at least 3 characters and password at least 4 characters.")
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username.strip(), self._hash_password(password)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username already exists.") from exc
            user_id = cursor.lastrowid
            token = secrets.token_hex(24)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id))
            conn.commit()
        return {"token": token, "user_id": user_id, "username": username.strip(), "xp": 0}

    def login(self, username: str, password: str) -> Dict[str, Any]:
        with self._connect() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ? AND password_hash = ?",
                (username.strip(), self._hash_password(password)),
            ).fetchone()
            if user is None:
                raise ValueError("Invalid username or password.")
            token = secrets.token_hex(24)
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user["id"]))
            conn.commit()
        return {"token": token, "user_id": user["id"], "username": user["username"], "xp": user["xp"]}

    def profile(self, token: str) -> Dict[str, Any]:
        user = self._user_from_token(token)
        if user is None:
            raise ValueError("Unauthorized.")
        with self._connect() as conn:
            completed = conn.execute(
                "SELECT lesson_id FROM lesson_progress WHERE user_id = ? ORDER BY completed_at DESC",
                (user["id"],),
            ).fetchall()
        return {
            "user_id": user["id"],
            "username": user["username"],
            "xp": user["xp"],
            "completed_lessons": len(completed),
            "completed_lesson_ids": [row["lesson_id"] for row in completed],
        }

    def submit_lesson(self, token: str, lesson_id: str, selected_index: int) -> Dict[str, Any]:
        user = self._user_from_token(token)
        if user is None:
            raise ValueError("Unauthorized.")
        lesson = LESSON_MAP.get(lesson_id)
        if lesson is None:
            raise ValueError("Unknown lesson.")
        is_correct = int(selected_index == lesson.quiz.answer_index)
        partial_xp = max(3, lesson.xp_reward // 4)
        xp_gain = lesson.xp_reward if is_correct else partial_xp
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT score FROM lesson_progress WHERE user_id = ? AND lesson_id = ?",
                (user["id"], lesson_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO lesson_progress (user_id, lesson_id, score) VALUES (?, ?, ?)",
                    (user["id"], lesson_id, is_correct),
                )
                conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (xp_gain, user["id"]))
            elif existing["score"] == 0 and is_correct == 1:
                bonus = lesson.xp_reward - partial_xp
                conn.execute(
                    "UPDATE lesson_progress SET score = 1, completed_at = CURRENT_TIMESTAMP WHERE user_id = ? AND lesson_id = ?",
                    (user["id"], lesson_id),
                )
                conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (bonus, user["id"]))
                xp_gain = bonus
            else:
                xp_gain = 0
            conn.commit()
            new_xp = conn.execute("SELECT xp FROM users WHERE id = ?", (user["id"],)).fetchone()["xp"]
        return {
            "correct": bool(is_correct),
            "xp_gained": xp_gain,
            "correct_answer_index": lesson.quiz.answer_index,
            "explanation": lesson.quiz.explanation,
            "new_xp": new_xp,
        }

    def leaderboard(self) -> Dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    users.username,
                    users.xp,
                    COUNT(lesson_progress.lesson_id) AS completed_lessons
                FROM users
                LEFT JOIN lesson_progress ON lesson_progress.user_id = users.id
                GROUP BY users.id
                ORDER BY users.xp DESC, completed_lessons DESC, users.username ASC
                LIMIT 25
                """
            ).fetchall()
        return {
            "leaders": [
                {
                    "rank": index + 1,
                    "username": row["username"],
                    "xp": row["xp"],
                    "completed_lessons": row["completed_lessons"],
                }
                for index, row in enumerate(rows)
            ]
        }

    def lesson_catalog(self) -> Dict[str, Any]:
        return {
            "lessons": [
                {
                    "lesson_id": lesson.lesson_id,
                    "topic_name": lesson.topic_name,
                    "stage": lesson.stage,
                    "title": lesson.title,
                    "summary": lesson.summary,
                    "explanation": lesson.explanation,
                    "code_sample": lesson.code_sample,
                    "challenge": lesson.challenge,
                    "xp_reward": lesson.xp_reward,
                    "quiz": {
                        "prompt": lesson.quiz.prompt,
                        "options": lesson.quiz.options,
                    },
                }
                for lesson in LESSONS
            ]
        }

    def start_in_background(self) -> None:
        if self._thread is not None:
            return
        server = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _send(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json_body(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                return json.loads(raw or "{}")

            def _token(self) -> str:
                header = self.headers.get("Authorization", "")
                return header.removeprefix("Bearer ").strip()

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                try:
                    if parsed.path == "/lessons":
                        self._send(server.lesson_catalog())
                    elif parsed.path == "/leaderboard":
                        self._send(server.leaderboard())
                    elif parsed.path == "/profile":
                        self._send(server.profile(self._token()))
                    elif parsed.path == "/health":
                        self._send({"status": "ok"})
                    else:
                        self._send({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    status = HTTPStatus.UNAUTHORIZED if "Unauthorized" in str(exc) else HTTPStatus.BAD_REQUEST
                    self._send({"error": str(exc)}, status)

            def do_POST(self) -> None:  # noqa: N802
                try:
                    payload = self._json_body()
                    if self.path == "/signup":
                        self._send(server.signup(payload["username"], payload["password"]), HTTPStatus.CREATED)
                    elif self.path == "/login":
                        self._send(server.login(payload["username"], payload["password"]))
                    elif self.path == "/submit-lesson":
                        self._send(
                            server.submit_lesson(
                                self._token(),
                                payload["lesson_id"],
                                int(payload["selected_index"]),
                            )
                        )
                    else:
                        self._send({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                except KeyError:
                    self._send({"error": "Missing required fields."}, HTTPStatus.BAD_REQUEST)
                except ValueError as exc:
                    status = HTTPStatus.UNAUTHORIZED if "Unauthorized" in str(exc) else HTTPStatus.BAD_REQUEST
                    self._send({"error": str(exc)}, status)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._httpd = ThreadingHTTPServer((self.host, self.port), RequestHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        self._httpd = None
        self._thread = None
