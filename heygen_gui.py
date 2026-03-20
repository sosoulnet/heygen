#!/usr/bin/env python3
"""
HeyGen Video Creator — GUI Launcher

A tkinter GUI that collects credentials, settings, and text file folder,
then launches the Selenium browser automation to create HeyGen videos.

Usage:
    python heygen_gui.py
"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class HeyGenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("HeyGen Video Creator")
        self.root.resizable(True, True)
        self.root.minsize(600, 520)

        self.running = False
        self.driver = None

        self._build_ui()
        self._load_saved_settings()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Main container with padding
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        # ── Credentials ──────────────────────────────────────────
        cred_frame = ttk.LabelFrame(main, text="HeyGen Credentials", padding=10)
        cred_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(cred_frame, text="Email:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.email_var = tk.StringVar()
        ttk.Entry(cred_frame, textvariable=self.email_var, width=40).grid(
            row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=2
        )

        ttk.Label(cred_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.password_var = tk.StringVar()
        ttk.Entry(cred_frame, textvariable=self.password_var, width=40, show="*").grid(
            row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=2
        )

        self.show_pass_var = tk.BooleanVar(value=False)
        self.pass_entry = cred_frame.grid_slaves(row=1, column=1)[0]
        ttk.Checkbutton(
            cred_frame, text="Show", variable=self.show_pass_var,
            command=self._toggle_password
        ).grid(row=1, column=2, padx=(4, 0), pady=2)

        ttk.Label(
            cred_frame, text="Leave blank to log in manually in the browser.",
            foreground="gray"
        ).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(2, 0))

        cred_frame.columnconfigure(1, weight=1)

        # ── Text Files Folder ────────────────────────────────────
        folder_frame = ttk.LabelFrame(main, text="Text Files Folder", padding=10)
        folder_frame.pack(fill=tk.X, pady=(0, 10))

        self.folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_var, width=50).grid(
            row=0, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(folder_frame, text="Browse...", command=self._browse_folder).grid(
            row=0, column=1, padx=(8, 0), pady=2
        )

        self.file_count_label = ttk.Label(folder_frame, text="No folder selected.", foreground="gray")
        self.file_count_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(2, 0))

        self.folder_var.trace_add("write", self._on_folder_change)
        folder_frame.columnconfigure(0, weight=1)

        # ── Download Folder ───────────────────────────────────────
        dl_frame = ttk.LabelFrame(main, text="Download Folder", padding=10)
        dl_frame.pack(fill=tk.X, pady=(0, 10))

        self.download_folder_var = tk.StringVar()
        ttk.Entry(dl_frame, textvariable=self.download_folder_var, width=50).grid(
            row=0, column=0, sticky=tk.EW, pady=2
        )
        ttk.Button(dl_frame, text="Browse...", command=self._browse_download_folder).grid(
            row=0, column=1, padx=(8, 0), pady=2
        )

        ttk.Label(
            dl_frame, text="Leave blank to save in a 'downloads' subfolder of the text files folder.",
            foreground="gray"
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(2, 0))

        dl_frame.columnconfigure(0, weight=1)

        # ── Settings ─────────────────────────────────────────────
        settings_frame = ttk.LabelFrame(main, text="Video Settings", padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Orientation
        ttk.Label(settings_frame, text="Orientation:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.orientation_var = tk.StringVar(value="portrait")
        orient_frame = ttk.Frame(settings_frame)
        orient_frame.grid(row=0, column=1, sticky=tk.W, padx=(8, 0), pady=2)
        ttk.Radiobutton(orient_frame, text="Portrait (9:16)", variable=self.orientation_var, value="portrait").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(orient_frame, text="Landscape (16:9)", variable=self.orientation_var, value="landscape").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(orient_frame, text="Square (1:1)", variable=self.orientation_var, value="square").pack(side=tk.LEFT)

        # Avatar
        ttk.Label(settings_frame, text="Avatar:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.avatar_var = tk.StringVar(value="none")
        avatar_frame = ttk.Frame(settings_frame)
        avatar_frame.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=2)
        ttk.Radiobutton(avatar_frame, text="No Avatar", variable=self.avatar_var, value="none").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(avatar_frame, text="Default Avatar", variable=self.avatar_var, value="default").pack(side=tk.LEFT)

        # Headless
        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings_frame, text="Run browser in background (headless)",
            variable=self.headless_var
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        settings_frame.columnconfigure(1, weight=1)

        # ── Action Buttons ───────────────────────────────────────
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(btn_frame, text="Start Creating Videos", command=self._start)
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Progress bar
        self.progress = ttk.Progressbar(btn_frame, mode="determinate", length=200)
        self.progress.pack(side=tk.RIGHT)

        self.progress_label = ttk.Label(btn_frame, text="")
        self.progress_label.pack(side=tk.RIGHT, padx=(0, 8))

        # ── Log Output ───────────────────────────────────────────
        log_frame = ttk.LabelFrame(main, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state=tk.DISABLED,
            font=("Consolas", 9), wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _toggle_password(self):
        self.pass_entry.configure(show="" if self.show_pass_var.get() else "*")

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder with .txt files")
        if folder:
            self.folder_var.set(folder)

    def _browse_download_folder(self):
        folder = filedialog.askdirectory(title="Select download folder for videos")
        if folder:
            self.download_folder_var.set(folder)

    def _on_folder_change(self, *_args):
        folder = self.folder_var.get().strip()
        if folder and Path(folder).is_dir():
            count = len(list(Path(folder).glob("*.txt")))
            self.file_count_label.config(
                text=f"Found {count} .txt file(s).",
                foreground="green" if count > 0 else "red"
            )
        else:
            self.file_count_label.config(text="No folder selected.", foreground="gray")

    @property
    def _settings_path(self):
        return Path(__file__).parent / "heygen_settings.json"

    def _load_saved_settings(self):
        """Load settings from JSON file, falling back to env vars."""
        try:
            data = json.loads(self._settings_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        self.email_var.set(data.get("email", os.environ.get("HEYGEN_EMAIL", "")))
        self.password_var.set(data.get("password", os.environ.get("HEYGEN_PASSWORD", "")))
        self.folder_var.set(data.get("folder", ""))
        self.download_folder_var.set(data.get("download_folder", ""))
        self.orientation_var.set(data.get("orientation", "portrait"))
        self.avatar_var.set(data.get("avatar", "none"))
        self.headless_var.set(data.get("headless", False))

    def _save_settings(self):
        """Persist current GUI settings to a JSON file."""
        data = {
            "email": self.email_var.get().strip(),
            "password": self.password_var.get().strip(),
            "folder": self.folder_var.get().strip(),
            "download_folder": self.download_folder_var.get().strip(),
            "orientation": self.orientation_var.get(),
            "avatar": self.avatar_var.get(),
            "headless": self.headless_var.get(),
        }
        try:
            self._settings_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass  # non-critical

    def _log(self, msg):
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def _on_close(self):
        """Save settings and close the window."""
        self._save_settings()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.root.destroy()

    def _set_progress(self, current, total):
        def _update():
            self.progress["maximum"] = total
            self.progress["value"] = current
            self.progress_label.config(text=f"{current}/{total}")
        self.root.after(0, _update)

    def _set_running(self, running):
        def _update():
            self.running = running
            self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
            self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.root.after(0, _update)

    def _start(self):
        self._save_settings()
        folder = self.folder_var.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror("Error", "Please select a valid folder containing .txt files.")
            return

        txt_files = sorted(Path(folder).glob("*.txt"))
        if not txt_files:
            messagebox.showerror("Error", f"No .txt files found in:\n{folder}")
            return

        self._set_running(True)
        self._log("=" * 50)
        self._log("Starting HeyGen Video Creator...")
        self._log(f"Folder: {folder}")
        self._log(f"Files: {len(txt_files)}")
        self._log(f"Orientation: {self.orientation_var.get()}")
        self._log(f"Avatar: {self.avatar_var.get()}")
        self._log(f"Headless: {self.headless_var.get()}")
        self._log("=" * 50)

        # Run in a background thread to keep the GUI responsive
        thread = threading.Thread(
            target=self._run_automation,
            args=(folder, txt_files),
            daemon=True,
        )
        thread.start()

    def _stop(self):
        self._log("Stopping... (will finish current operation)")
        self.running = False
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _run_automation(self, folder, txt_files):
        """Run the Selenium automation in a background thread."""
        import heygen_video_creator as hvc

        folder = Path(folder).resolve()
        dl_folder = self.download_folder_var.get().strip()
        if dl_folder and Path(dl_folder).is_dir():
            downloads_dir = Path(dl_folder).resolve()
        else:
            downloads_dir = folder / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        headless = self.headless_var.get()
        orientation = self.orientation_var.get()
        use_avatar = self.avatar_var.get() != "none"

        # Monkey-patch print so output goes to our log
        original_print = hvc.__builtins__["print"] if isinstance(hvc.__builtins__, dict) else print
        def gui_print(*args, **kwargs):
            msg = " ".join(str(a) for a in args)
            self._log(msg)
        import builtins
        old_print = builtins.print
        builtins.print = gui_print

        # Also patch input() so it doesn't block
        def gui_input(prompt=""):
            self._log(f"[ACTION NEEDED] {prompt}")
            messagebox.showinfo("Action Required", prompt)
            return ""
        old_input = builtins.input
        builtins.input = gui_input

        try:
            self._log("Launching browser...")
            driver = hvc.create_driver(headless=headless, download_dir=downloads_dir)
            self.driver = driver

            self._log("Logging in to HeyGen...")
            email = self.email_var.get().strip() or None
            password = self.password_var.get().strip() or None
            hvc.login(driver, email=email, password=password)

            results = {"success": 0, "failed": 0}
            total = len(txt_files)

            for i, txt_file in enumerate(txt_files, 1):
                if not self.running:
                    self._log("Stopped by user.")
                    break

                self._set_progress(i - 1, total)
                self._log(f"\n{'='*50}")
                self._log(f"File {i}/{total}: {txt_file.name}")
                self._log(f"{'='*50}")

                text = txt_file.read_text(encoding="utf-8").strip()
                if not text:
                    self._log(f"  Skipping empty file.")
                    results["failed"] += 1
                    continue

                title = txt_file.stem

                try:
                    hvc.create_video_from_text(driver, text, title, downloads_dir)
                    results["success"] += 1
                except Exception as e:
                    self._log(f"  Error: {e}")
                    results["failed"] += 1
                    try:
                        ss = downloads_dir / f"error_{title}.png"
                        driver.save_screenshot(str(ss))
                        self._log(f"  Screenshot saved: {ss}")
                    except Exception:
                        pass

                self._set_progress(i, total)

            self._log(f"\n{'='*50}")
            self._log(f"Done! Success: {results['success']}, Failed: {results['failed']}")
            self._log(f"Videos saved to: {downloads_dir}")

            self.root.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Done!\n\nSuccess: {results['success']}\nFailed: {results['failed']}\n\nVideos saved to:\n{downloads_dir}"
            ))

        except Exception as e:
            self._log(f"Fatal error: {e}")
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            builtins.print = old_print
            builtins.input = old_input
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
            self._set_running(False)


def main():
    root = tk.Tk()
    app = HeyGenGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
