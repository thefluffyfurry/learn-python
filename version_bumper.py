"""Desktop tool for updating release version numbers in one place."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


VERSION_PATTERN = re.compile(r'APP_VERSION\s*=\s*"([^"]+)"')
VALID_VERSION = re.compile(r"^\d+(?:\.\d+)*$")


def find_project_root() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    candidates.append(Path.cwd().resolve())
    candidates.append(Path(__file__).resolve().parent)

    seen: set[Path] = set()
    for base in candidates:
        current = base
        while current not in seen:
            seen.add(current)
            if (current / "app" / "version.py").exists() and (current / "update_manifest.json").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise FileNotFoundError("Could not find project root with app/version.py and update_manifest.json.")


def read_current_version(version_file: Path) -> str:
    match = VERSION_PATTERN.search(version_file.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("Could not read APP_VERSION from app/version.py.")
    return match.group(1)


def update_version_file(version_file: Path, new_version: str) -> None:
    content = version_file.read_text(encoding="utf-8")
    updated, count = VERSION_PATTERN.subn(f'APP_VERSION = "{new_version}"', content, count=1)
    if count != 1:
        raise RuntimeError("Could not update APP_VERSION in app/version.py.")
    version_file.write_text(updated, encoding="utf-8")


def update_manifest(manifest_file: Path, new_version: str) -> None:
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    payload["version"] = new_version
    manifest_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_main_exe(root_dir: Path) -> Path:
    python_exe = root_dir / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        raise RuntimeError("Missing virtual environment Python at .venv\\Scripts\\python.exe")

    dist_dir = root_dir / "dist_release"
    work_dir = root_dir / "build_release"
    spec_dir = root_dir
    command = [
        str(python_exe),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        "PyQuestAcademy",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "main.py",
    ]
    result = subprocess.run(
        command,
        cwd=root_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "PyInstaller failed."
        raise RuntimeError(detail)
    exe_path = dist_dir / "PyQuestAcademy.exe"
    if not exe_path.exists():
        raise RuntimeError("Build finished but dist_release\\PyQuestAcademy.exe was not created.")
    return exe_path


class VersionBumperApp(tk.Tk):
    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self.root_dir = root_dir
        self.version_file = root_dir / "app" / "version.py"
        self.manifest_file = root_dir / "update_manifest.json"
        self.example_manifest_file = root_dir / "update_manifest.example.json"
        self.current_version = read_current_version(self.version_file)
        self.is_busy = False

        self.title("PyQuest Version Bumper")
        self.geometry("600x360")
        self.minsize(560, 320)
        self.configure(bg="#f4efe8")

        self.version_var = tk.StringVar(value=self.current_version)
        self.current_version_var = tk.StringVar(value=f"Current version: {self.current_version}")
        self.status_var = tk.StringVar(value=f"Project: {self.root_dir}")

        shell = tk.Frame(self, bg="#17324d", padx=22, pady=18)
        shell.pack(fill="x")
        tk.Label(shell, text="RELEASE TOOL", bg="#17324d", fg="#9fb9cf", font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(shell, text="PyQuest Version Bumper", bg="#17324d", fg="#f7f4ef", font=("Georgia", 24, "bold")).pack(anchor="w")
        tk.Label(
            shell,
            text="Enter one version number and update release files, or update and build the app in one step.",
            bg="#17324d",
            fg="#cad5df",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self, bg="#fffdf9", padx=24, pady=22, highlightthickness=1, highlightbackground="#dccfc2")
        card.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(card, textvariable=self.current_version_var, bg="#fffdf9", fg="#1d2d3d", font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(card, text="New version", bg="#fffdf9", fg="#647587", font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(18, 6))
        entry = tk.Entry(
            card,
            textvariable=self.version_var,
            font=("Segoe UI", 14),
            relief="flat",
            bg="#fffaf4",
            fg="#1d2d3d",
            insertbackground="#1d2d3d",
            highlightthickness=1,
            highlightbackground="#dccfc2",
            highlightcolor="#284c6c",
        )
        entry.pack(fill="x", ipady=8)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        files = [
            "app/version.py",
            "update_manifest.json",
            "update_manifest.example.json",
        ]
        tk.Label(
            card,
            text="Files updated:",
            bg="#fffdf9",
            fg="#647587",
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(18, 6))
        for item in files:
            tk.Label(card, text=item, bg="#fffdf9", fg="#1d2d3d", font=("Consolas", 10)).pack(anchor="w")

        actions = tk.Frame(card, bg="#fffdf9")
        actions.pack(fill="x", pady=(20, 0))
        self.update_button = tk.Button(
            actions,
            text="Update Versions",
            command=self.apply_update,
            bg="#f08a4b",
            fg="white",
            relief="flat",
            padx=18,
            pady=10,
            font=("Segoe UI Semibold", 10),
        )
        self.update_button.pack(side="left")
        self.release_button = tk.Button(
            actions,
            text="Update + Build EXE",
            command=self.apply_update_and_build,
            bg="#237a57",
            fg="white",
            relief="flat",
            padx=18,
            pady=10,
            font=("Segoe UI Semibold", 10),
        )
        self.release_button.pack(side="left", padx=(8, 0))
        tk.Button(
            actions,
            text="Close",
            command=self.destroy,
            bg="#284c6c",
            fg="white",
            relief="flat",
            padx=18,
            pady=10,
            font=("Segoe UI Semibold", 10),
        ).pack(side="left", padx=(8, 0))

        tk.Label(self, textvariable=self.status_var, bg="#f4efe8", fg="#647587", font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=18, pady=(0, 12))

    def apply_update(self) -> None:
        if self.is_busy:
            return
        new_version = self.version_var.get().strip()
        if not VALID_VERSION.fullmatch(new_version):
            messagebox.showerror("Invalid version", "Use numbers separated by dots, like 1.3.1")
            return

        try:
            update_version_file(self.version_file, new_version)
            update_manifest(self.manifest_file, new_version)
            if self.example_manifest_file.exists():
                update_manifest(self.example_manifest_file, new_version)
        except Exception as exc:
            messagebox.showerror("Update failed", str(exc))
            return

        self.current_version = new_version
        self.current_version_var.set(f"Current version: {new_version}")
        self.status_var.set(f"Updated release files to version {new_version}")
        messagebox.showinfo("Versions updated", f"Updated all release files to {new_version}.")

    def apply_update_and_build(self) -> None:
        if self.is_busy:
            return
        new_version = self.version_var.get().strip()
        if not VALID_VERSION.fullmatch(new_version):
            messagebox.showerror("Invalid version", "Use numbers separated by dots, like 1.3.1")
            return
        self.is_busy = True
        self.update_button.config(state="disabled")
        self.release_button.config(state="disabled")
        self.status_var.set(f"Updating release files and building version {new_version}...")
        threading.Thread(target=self._apply_update_and_build_worker, args=(new_version,), daemon=True).start()

    def _apply_update_and_build_worker(self, new_version: str) -> None:
        error_text: str | None = None
        exe_path: Path | None = None
        try:
            update_version_file(self.version_file, new_version)
            update_manifest(self.manifest_file, new_version)
            if self.example_manifest_file.exists():
                update_manifest(self.example_manifest_file, new_version)
            exe_path = build_main_exe(self.root_dir)
        except Exception as exc:
            error_text = str(exc)
        self.after(0, lambda: self._finish_update_and_build(new_version, exe_path, error_text))

    def _finish_update_and_build(self, new_version: str, exe_path: Path | None, error_text: str | None) -> None:
        self.is_busy = False
        self.update_button.config(state="normal")
        self.release_button.config(state="normal")
        if error_text:
            self.status_var.set("Update/build failed.")
            messagebox.showerror("Build failed", error_text)
            return
        self.current_version = new_version
        self.current_version_var.set(f"Current version: {new_version}")
        self.status_var.set(f"Built {exe_path}")
        messagebox.showinfo(
            "Release ready",
            f"Updated release files to {new_version}.\n\nBuilt:\n{exe_path}",
        )


def main() -> None:
    root_dir = find_project_root()
    app = VersionBumperApp(root_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
