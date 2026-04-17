"""
Keystroke Monitor
-----------------
Captures every key press/release and computes:

  - dwell_time_ms  : how long the key was held down
  - flight_time_ms : gap between the previous key-up and this key-down
                     (measures typing rhythm)
  - is_backspace   : whether the key was a correction
  - is_special     : shift, ctrl, fn keys etc.

The actual character is stored only as a sanitised label so no passwords
or private text are ever reconstructed from the log.
"""

import time
import threading
from typing import Optional
from pynput import keyboard

from storage.database import Database


class KeystrokeMonitor:
    def __init__(self, session_id: str, db: Database):
        self.session_id = session_id
        self.db = db

        # key_label -> timestamp of key-down
        self._down_times: dict[str, float] = {}

        # timestamp of the most recent key-up (for flight time)
        self._last_key_up: Optional[float] = None

        self._lock = threading.Lock()
        self._listener: Optional[keyboard.Listener] = None

    # ------------------------------------------------------------------
    # pynput callbacks
    # ------------------------------------------------------------------

    def _on_press(self, key):
        now = time.time()
        label = self._label(key)
        with self._lock:
            # Only record down-time if not already held (key repeat guard)
            if label not in self._down_times:
                self._down_times[label] = now

    def _on_release(self, key):
        now = time.time()
        label = self._label(key)

        with self._lock:
            down_time = self._down_times.pop(label, None)

            # dwell = key held duration
            dwell_ms: Optional[float] = None
            if down_time is not None:
                dwell_ms = (now - down_time) * 1000

            # flight = gap between previous key-up and THIS key-down
            flight_ms: Optional[float] = None
            if self._last_key_up is not None and down_time is not None:
                gap = (down_time - self._last_key_up) * 1000
                # Negative flight time means keys overlapped (e.g. shift held)
                # Keep it — it's a valid behavioural signal
                flight_ms = gap

            self._last_key_up = now

        is_backspace = label in ("backspace", "Key.backspace")
        is_special = label.startswith("Key.")

        self.db.insert_keystroke_event(
            session_id=self.session_id,
            key_label=label,
            is_special=is_special,
            is_backspace=is_backspace,
            dwell_time_ms=dwell_ms,
            flight_time_ms=flight_ms,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _label(key) -> str:
        """
        Return a safe string label for the key.

        Regular printable characters are stored as-is (single char).
        Special keys (shift, ctrl, fn …) are stored as 'Key.<name>'.
        This is enough information to compute timing features without
        reconstructing typed text.
        """
        try:
            char = key.char
            if char and char.isprintable():
                # Normalise letters to lowercase so 'A' and 'a' share
                # the same timing bucket — we don't care about case.
                return char.lower()
            return "Key.nonprintable"
        except AttributeError:
            return f"Key.{key.name}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Start listening in a background thread."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        print("[KeystrokeMonitor] started")

    def stop(self):
        """Stop the listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        print("[KeystrokeMonitor] stopped")
