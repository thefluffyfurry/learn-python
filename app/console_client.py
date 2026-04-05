"""Console frontend for the Python teaching app."""

from __future__ import annotations

import textwrap
from typing import Any, Dict, List, Optional

from app.api import ApiClient, ApiConnectionError, ApiError
from app.version import APP_NAME, APP_VERSION


class ConsoleTeachingApp:
    def __init__(self, api: ApiClient) -> None:
        self.api = api
        self.lessons: List[Dict[str, Any]] = []

    def run(self) -> None:
        self._print_banner()
        self._refresh_lessons(show_message=False)
        while True:
            try:
                if self.api.username:
                    if not self._signed_in_menu():
                        return
                else:
                    if not self._guest_menu():
                        return
            except KeyboardInterrupt:
                print("\nExiting PyQuest Academy.")
                return
            except EOFError:
                print("\nInput closed. Exiting PyQuest Academy.")
                return

    def _print_banner(self) -> None:
        print(f"{APP_NAME} Console v{APP_VERSION}")
        print("=" * (len(APP_NAME) + len(APP_VERSION) + 12))
        print(self.api.auth_message())
        print()

    def _status_label(self) -> str:
        if self.api.is_local_mode():
            return "Local mode"
        if self.api.using_offline_cache():
            return "Offline cache"
        return "Hosted sync"

    def _guest_menu(self) -> bool:
        self._print_status()
        print("1. Sign up")
        print("2. Log in")
        print("3. Browse lessons")
        print("4. Leaderboard")
        print("5. Refresh lessons")
        print("6. Exit")
        choice = input("Choose an option: ").strip().lower()
        print()

        if choice == "1":
            self._authenticate(signup=True)
            return True
        if choice == "2":
            self._authenticate(signup=False)
            return True
        if choice == "3":
            self._browse_topics()
            return True
        if choice == "4":
            self._show_leaderboard()
            return True
        if choice == "5":
            self._refresh_lessons()
            return True
        if choice in {"6", "q", "quit", "exit"}:
            return False

        print("Enter one of the menu numbers.\n")
        return True

    def _signed_in_menu(self) -> bool:
        self._print_status()
        print(f"Signed in as: {self.api.username}")
        print("1. Profile")
        print("2. Continue next lesson")
        print("3. Browse lessons")
        print("4. Leaderboard")
        print("5. Refresh lessons")
        print("6. Log out")
        print("7. Exit")
        choice = input("Choose an option: ").strip().lower()
        print()

        if choice == "1":
            self._show_profile()
            return True
        if choice == "2":
            self._continue_next_lesson()
            return True
        if choice == "3":
            self._browse_topics()
            return True
        if choice == "4":
            self._show_leaderboard()
            return True
        if choice == "5":
            self._refresh_lessons()
            return True
        if choice == "6":
            self.api.clear_session()
            print("You have been logged out.\n")
            return True
        if choice in {"7", "q", "quit", "exit"}:
            return False

        print("Enter one of the menu numbers.\n")
        return True

    def _print_status(self) -> None:
        source = self._status_label()
        target = self.api.base_url if not self.api.is_local_mode() else self.api.fallback_url
        print(f"Status: {source} ({target})")
        print("-" * 72)

    def _authenticate(self, signup: bool) -> None:
        action = "Sign up" if signup else "Log in"
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        if not username or not password:
            print("Enter both username and password.\n")
            return

        try:
            result = self.api.signup(username, password) if signup else self.api.login(username, password)
        except ApiError as exc:
            print(f"{action} failed: {exc}\n")
            return

        print(
            f"{action} complete. Welcome {result['username']}."
            f" XP: {result['xp']} | Source: {self._status_label()}\n"
        )

    def _refresh_lessons(self, show_message: bool = True) -> bool:
        try:
            self.lessons = self.api.lessons()
        except ApiError as exc:
            print(f"Could not load lessons: {exc}\n")
            return False

        if show_message:
            print(f"Loaded {len(self.lessons)} lessons from {self._status_label().lower()}.\n")
        return True

    def _profile_or_none(self) -> Optional[Dict[str, Any]]:
        if not self.api.username:
            return None
        try:
            return self.api.profile()
        except ApiError as exc:
            print(f"Could not load profile: {exc}\n")
            return None

    def _show_profile(self) -> None:
        profile = self._profile_or_none()
        if profile is None:
            return

        print(f"Username: {profile['username']}")
        print(f"XP: {profile['xp']}")
        print(f"Completed lessons: {profile['completed_lessons']}")
        recent_ids = profile["completed_lesson_ids"][:10]
        if recent_ids:
            print("Recent lessons: " + ", ".join(recent_ids))
        print()

    def _show_leaderboard(self) -> None:
        try:
            leaders = self.api.leaderboard()
        except ApiError as exc:
            print(f"Could not load leaderboard: {exc}\n")
            return

        if not leaders:
            print("Leaderboard is empty.\n")
            return

        print("Leaderboard")
        print("-" * 72)
        for leader in leaders[:10]:
            print(
                f"{leader['rank']:>2}. {leader['username']:<18} "
                f"XP {leader['xp']:<5} Lessons {leader['completed_lessons']}"
            )
        print()

    def _browse_topics(self) -> None:
        if not self.lessons and not self._refresh_lessons(show_message=False):
            return

        topics = self._topic_groups(self.lessons)
        profile = self._profile_or_none()
        completed_ids = set(profile["completed_lesson_ids"]) if profile else set()

        while True:
            print("Topics")
            print("-" * 72)
            for index, topic_name in enumerate(topics, start=1):
                topic_lessons = topics[topic_name]
                done_count = sum(1 for lesson in topic_lessons if lesson["lesson_id"] in completed_ids)
                print(f"{index:>2}. {topic_name:<24} {done_count:>2}/{len(topic_lessons)} complete")
            print(" B. Back")
            choice = input("Pick a topic: ").strip().lower()
            print()

            if choice in {"b", "back", "q"}:
                return
            if not choice.isdigit():
                print("Enter a topic number.\n")
                continue

            topic_index = int(choice) - 1
            if topic_index < 0 or topic_index >= len(topics):
                print("That topic number is out of range.\n")
                continue

            topic_name = list(topics.keys())[topic_index]
            self._browse_topic_lessons(topic_name, topics[topic_name], completed_ids)
            profile = self._profile_or_none()
            completed_ids = set(profile["completed_lesson_ids"]) if profile else set()

    def _browse_topic_lessons(
        self, topic_name: str, topic_lessons: List[Dict[str, Any]], completed_ids: set[str]
    ) -> None:
        while True:
            print(topic_name)
            print("-" * 72)
            for lesson in topic_lessons:
                marker = "x" if lesson["lesson_id"] in completed_ids else " "
                print(
                    f"[{marker}] {lesson['stage']:>2}. {lesson['title']} "
                    f"(+{lesson['xp_reward']} XP)"
                )
            print(" B. Back")
            choice = input("Pick a stage number: ").strip().lower()
            print()

            if choice in {"b", "back", "q"}:
                return
            if not choice.isdigit():
                print("Enter a stage number.\n")
                continue

            stage_number = int(choice)
            lesson = next((item for item in topic_lessons if int(item["stage"]) == stage_number), None)
            if lesson is None:
                print("That stage number is not in this topic.\n")
                continue

            self._show_lesson(lesson)
            if self.api.username:
                profile = self._profile_or_none()
                completed_ids.clear()
                if profile:
                    completed_ids.update(profile["completed_lesson_ids"])

    def _show_lesson(self, lesson: Dict[str, Any]) -> None:
        self._print_wrapped(f"{lesson['title']} ({lesson['lesson_id']})")
        print("-" * 72)
        self._print_wrapped(lesson["summary"])
        print()
        self._print_wrapped(lesson["explanation"])
        print()
        print("Code sample:")
        print(lesson["code_sample"])
        print()
        print("Challenge:")
        self._print_wrapped(lesson["challenge"])
        print()
        print(f"Quiz XP reward: {lesson['xp_reward']}")
        print(f"Quiz: {lesson['quiz']['prompt']}")
        for index, option in enumerate(lesson["quiz"]["options"], start=1):
            self._print_wrapped(f"{index}. {option}")
        print()

        if not self.api.username:
            print("Log in or sign up to submit answers and save progress.\n")
            return

        take_quiz = input("Submit an answer now? [y/N]: ").strip().lower()
        if take_quiz not in {"y", "yes"}:
            print()
            return

        answer = input("Choose 1-4: ").strip()
        if answer not in {"1", "2", "3", "4"}:
            print("Answer cancelled.\n")
            return

        try:
            result = self.api.submit_lesson(lesson["lesson_id"], int(answer) - 1)
        except ApiError as exc:
            print(f"Submission failed: {exc}\n")
            return

        verdict = "Correct" if result["correct"] else "Not quite"
        print(f"{verdict}. XP gained: {result['xp_gained']}. New XP total: {result['new_xp']}.")
        self._print_wrapped(result["explanation"])
        print()

    def _continue_next_lesson(self) -> None:
        if not self.lessons and not self._refresh_lessons(show_message=False):
            return

        profile = self._profile_or_none()
        if profile is None:
            return

        completed_ids = set(profile["completed_lesson_ids"])
        next_lesson = next((lesson for lesson in self.lessons if lesson["lesson_id"] not in completed_ids), None)
        if next_lesson is None:
            print("You have completed every lesson currently available.\n")
            return

        self._show_lesson(next_lesson)

    @staticmethod
    def _topic_groups(lessons: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for lesson in lessons:
            grouped.setdefault(str(lesson["topic_name"]), []).append(lesson)
        return grouped

    @staticmethod
    def _print_wrapped(text: str) -> None:
        print(textwrap.fill(text, width=88))


def run_console_client(base_url: str) -> None:
    ConsoleTeachingApp(ApiClient(base_url, client_type="console")).run()
