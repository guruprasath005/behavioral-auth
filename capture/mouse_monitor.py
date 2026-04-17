"""
Mouse Monitor
-------------
Captures mouse movement, clicks, and scroll events and computes:

  - speed_px_s     : instantaneous mouse speed (pixels per second)
  - button         : which button was clicked
  - pressed        : click down (1) or up (0)
  - scroll_dx/dy   : scroll delta per event
  - idle tracking  : time since last any mouse activity
"""

import time
import math
import threading
from typing import Optional
from pynput import mouse

from storage.database import Database


class MouseMonitor:
    # Throttle move events — record one every MOVE_INTERVAL seconds
    # to avoid flooding the DB with thousands of tiny movements
    MOVE_INTERVAL = 0.05  # 50 ms  →  max 20 move events/sec

    def __init__(self, session_id: str, db: Database):
        self.session_id = session_id
        self.db = db

        self._last_move_time: Optional[float] = None
        self._last_move_pos: Optional[tuple[int, int]] = None
        self._last_activity_time: float = time.time()

        # Track consecutive clicks for double-click detection
        self._last_click_time: Optional[float] = None
        self._last_click_button: Optional[str] = None
        self.DOUBLE_CLICK_THRESHOLD = 0.35  # seconds

        self._lock = threading.Lock()
        self._listener: Optional[mouse.Listener] = None

    # ------------------------------------------------------------------
    # pynput callbacks
    # ------------------------------------------------------------------

    def _on_move(self, x: int, y: int):
        now = time.time()

        with self._lock:
            # Throttle — skip if last move was too recent
            if self._last_move_time and (now - self._last_move_time) < self.MOVE_INTERVAL:
                return

            speed: Optional[float] = None
            if self._last_move_time and self._last_move_pos:
                dt = now - self._last_move_time
                if dt > 0:
                    dx = x - self._last_move_pos[0]
                    dy = y - self._last_move_pos[1]
                    dist = math.sqrt(dx * dx + dy * dy)
                    speed = dist / dt  # px/s

            self._last_move_time = now
            self._last_move_pos = (x, y)
            self._last_activity_time = now

        self.db.insert_mouse_event(
            session_id=self.session_id,
            event_type="move",
            x=x,
            y=y,
            speed_px_s=speed,
            timestamp=now,
        )

    def _on_click(self, x: int, y: int, button, pressed: bool):
        now = time.time()
        btn_label = str(button).replace("Button.", "")  # 'left', 'right', 'middle'

        with self._lock:
            self._last_activity_time = now

            # Double-click detection (only on press, not release)
            is_double = False
            if pressed:
                if (
                    self._last_click_time is not None
                    and self._last_click_button == btn_label
                    and (now - self._last_click_time) <= self.DOUBLE_CLICK_THRESHOLD
                ):
                    is_double = True
                self._last_click_time = now
                self._last_click_button = btn_label

        event_type = "double_click" if is_double else "click"

        self.db.insert_mouse_event(
            session_id=self.session_id,
            event_type=event_type,
            x=x,
            y=y,
            button=btn_label,
            pressed=int(pressed),
            timestamp=now,
        )

    def _on_scroll(self, x: int, y: int, dx: float, dy: float):
        now = time.time()
        with self._lock:
            self._last_activity_time = now

        self.db.insert_mouse_event(
            session_id=self.session_id,
            event_type="scroll",
            x=x,
            y=y,
            scroll_dx=dx,
            scroll_dy=dy,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_idle_seconds(self) -> float:
        """Seconds since the last mouse activity."""
        with self._lock:
            return time.time() - self._last_activity_time

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._listener.start()
        print("[MouseMonitor] started")

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
        print("[MouseMonitor] stopped")
