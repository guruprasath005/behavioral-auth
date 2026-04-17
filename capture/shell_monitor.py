"""
Shell Monitor
-------------
Captures terminal commands typed by the user.

How it works
~~~~~~~~~~~~
1. A one-line hook is added to ~/.zshrc (or ~/.bashrc).
   The hook appends every command to a plain log file at:
       /tmp/behavioral_auth_shell.log

2. This monitor tails that file in a background thread and
   writes each new command into the SQLite DB.

Setup (run once)
~~~~~~~~~~~~~~~~
    from capture.shell_monitor import ShellMonitor
    ShellMonitor.install_hook()          # adds hook to ~/.zshrc
    # then restart your terminal

The hook line looks like:
    preexec() { echo "$(date +%s%3N) $1" >> /tmp/behavioral_auth_shell.log; }

The timestamp prefix (epoch ms) lets us correlate shell events with
keystroke / mouse windows even if the system clock drifts slightly.
"""

import os
import time
import threading
from typing import Optional

from storage.database import Database

SHELL_LOG = "/tmp/behavioral_auth_shell.log"

ZSH_HOOK = (
    '\n# -- Behavioral Auth Hook (auto-added) --\n'
    'preexec() { echo "$(date +%s%3N) $1" >> /tmp/behavioral_auth_shell.log; }\n'
    '# -- End Behavioral Auth Hook --\n'
)

BASH_HOOK = (
    '\n# -- Behavioral Auth Hook (auto-added) --\n'
    'trap \'echo "$(date +%s%3N) $(history 1 | sed "s/^[ ]*[0-9]*[ ]*//")" '
    '>> /tmp/behavioral_auth_shell.log\' DEBUG\n'
    '# -- End Behavioral Auth Hook --\n'
)


class ShellMonitor:
    POLL_INTERVAL = 0.5  # seconds between file checks

    def __init__(self, session_id: str, db: Database, log_path: str = SHELL_LOG):
        self.session_id = session_id
        self.db = db
        self.log_path = log_path

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._file_offset: int = 0  # byte position — only read new lines

    # ------------------------------------------------------------------
    # One-time hook installation
    # ------------------------------------------------------------------

    @staticmethod
    def install_hook(shell: str = "zsh") -> str:
        """
        Append the shell hook to the user's rc file.
        Returns the path of the rc file modified.
        Safe to call multiple times — checks if hook already present.
        """
        home = os.path.expanduser("~")
        if shell == "zsh":
            rc_path = os.path.join(home, ".zshrc")
            hook = ZSH_HOOK
        else:
            rc_path = os.path.join(home, ".bashrc")
            hook = BASH_HOOK

        if os.path.exists(rc_path):
            content = open(rc_path).read()
            if "Behavioral Auth Hook" in content:
                print(f"[ShellMonitor] Hook already present in {rc_path}")
                return rc_path

        with open(rc_path, "a") as f:
            f.write(hook)

        print(f"[ShellMonitor] Hook installed in {rc_path}")
        print("[ShellMonitor] Please restart your terminal (or run: source ~/.zshrc)")
        return rc_path

    @staticmethod
    def remove_hook(shell: str = "zsh"):
        """Remove the hook from the rc file."""
        home = os.path.expanduser("~")
        rc_path = os.path.join(home, ".zshrc" if shell == "zsh" else ".bashrc")

        if not os.path.exists(rc_path):
            return

        lines = open(rc_path).readlines()
        inside_hook = False
        cleaned = []
        for line in lines:
            if "-- Behavioral Auth Hook (auto-added) --" in line:
                inside_hook = True
            if not inside_hook:
                cleaned.append(line)
            if "-- End Behavioral Auth Hook --" in line:
                inside_hook = False

        with open(rc_path, "w") as f:
            f.writelines(cleaned)

        print(f"[ShellMonitor] Hook removed from {rc_path}")

    # ------------------------------------------------------------------
    # Tail loop
    # ------------------------------------------------------------------

    def _tail_loop(self):
        """
        Poll the shell log file for new lines.
        Each line format: '<epoch_ms> <command>'
        """
        # Wait for the log file to appear (in case terminal hasn't run yet)
        waited = 0
        while not os.path.exists(self.log_path) and not self._stop_event.is_set():
            if waited == 0:
                print(f"[ShellMonitor] Waiting for {self.log_path} ...")
            time.sleep(1)
            waited += 1
            if waited > 30:
                print("[ShellMonitor] Log file never appeared. Is the hook installed?")
                return

        # Seek to end — only capture commands typed AFTER this session starts
        try:
            with open(self.log_path, "r") as f:
                f.seek(0, 2)  # seek to EOF
                self._file_offset = f.tell()
        except OSError:
            self._file_offset = 0

        print(f"[ShellMonitor] tailing {self.log_path}")

        while not self._stop_event.is_set():
            try:
                with open(self.log_path, "r") as f:
                    f.seek(self._file_offset)
                    new_data = f.read()
                    self._file_offset = f.tell()

                if new_data:
                    for raw_line in new_data.splitlines():
                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue
                        ts, command = self._parse_line(raw_line)
                        if command:
                            self.db.insert_shell_event(
                                session_id=self.session_id,
                                command=command,
                                timestamp=ts,
                            )
                            print(f"[ShellMonitor] captured: {command}")

            except OSError as e:
                print(f"[ShellMonitor] read error: {e}")

            self._stop_event.wait(self.POLL_INTERVAL)

    @staticmethod
    def _parse_line(line: str) -> tuple[float, str]:
        """
        Parse '<epoch_ms> <command>' into (timestamp_seconds, command).
        Falls back to current time if format is unexpected.
        """
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            ts = int(parts[0]) / 1000.0  # ms → seconds
            command = parts[1].strip()
        else:
            ts = time.time()
            command = line.strip()
        return ts, command

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._tail_loop, daemon=True, name="shell-monitor"
        )
        self._thread.start()
        print("[ShellMonitor] started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        print("[ShellMonitor] stopped")
