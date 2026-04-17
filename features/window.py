"""
Window Manager
--------------
Fires every WINDOW_SIZE_S seconds and hands a fresh feature dict
to the registered callback.

Timeline
~~~~~~~~
  window 0  (warmup) → extract features, save to DB, callback with is_warmup=True
  window 1  (warmup) → same
  window 2  (warmup) → same
  window 3+ (live)   → extract features, callback with is_warmup=False
                        → Phase 5 (GPT scoring) plugs in here via callback

The callback signature:
    on_window(window_index: int, features: dict) -> None

    features dict contains all 13 feature values plus:
        window_index    int
        window_start    float  (epoch seconds)
        window_end      float  (epoch seconds)
        is_warmup       bool
        sufficient_data bool   (False if < 5 keystrokes in window)
"""

import json
import time
import threading
from typing import Callable, Optional

from storage.database import Database
from features.extractor import FeatureExtractor


class WindowManager:
    WINDOW_SIZE_S  = 10   # seconds per window
    WARMUP_WINDOWS = 3    # collect silently before scoring starts

    def __init__(
        self,
        session_id: str,
        db: Database,
        on_window: Callable[[int, dict], None],
        window_size_s: int = WINDOW_SIZE_S,
        warmup_windows: int = WARMUP_WINDOWS,
    ):
        self.session_id    = session_id
        self.db            = db
        self.on_window     = on_window
        self.window_size_s = window_size_s
        self.warmup_windows = warmup_windows

        self._extractor    = FeatureExtractor()
        self._window_index = 0
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Core tick — runs every WINDOW_SIZE_S seconds
    # ------------------------------------------------------------------

    def _tick(self):
        now          = time.time()
        window_start = now - self.window_size_s
        is_warmup    = self._window_index < self.warmup_windows

        # Pull only events that fall inside this window
        all_ks = self.db.get_keystroke_events(self.session_id)
        all_ms = self.db.get_mouse_events(self.session_id)

        ks_window = [e for e in all_ks if e["timestamp"] >= window_start]
        ms_window = [e for e in all_ms if e["timestamp"] >= window_start]

        # Extract features
        features = self._extractor.extract(
            keystroke_events=ks_window,
            mouse_events=ms_window,
            window_duration_s=self.window_size_s,
        )

        # Attach window metadata
        features["window_index"] = self._window_index
        features["window_start"] = round(window_start, 3)
        features["window_end"]   = round(now, 3)
        features["is_warmup"]    = is_warmup

        # Persist to DB (features_json stores the 13 scoring features only)
        scoring_features = {
            k: features[k]
            for k in [
                "typing_speed_wpm", "keystroke_interval_avg_ms",
                "keystroke_interval_std_ms", "backspace_rate", "error_rate",
                "pause_frequency", "burst_typing_ratio", "mouse_speed_avg",
                "mouse_speed_std", "click_rate_per_min", "double_click_rate",
                "scroll_events_per_min", "mouse_idle_ratio",
            ]
        }
        self.db.insert_feature_window(
            session_id=self.session_id,
            window_index=self._window_index,
            window_start=window_start,
            window_end=now,
            is_warmup=is_warmup,
            features_json=json.dumps(scoring_features),
        )

        # Log to console
        status = "WARMUP" if is_warmup else "LIVE  "
        print(
            f"[Window {self._window_index:>3}] {status} | "
            f"ks={features['keystroke_count']:>4}  "
            f"ms={features['mouse_event_count']:>4}  "
            f"wpm={features['typing_speed_wpm']:>6.1f}  "
            f"speed={features['mouse_speed_avg']:>7.1f}px/s  "
            f"data={'OK' if features['sufficient_data'] else '--'}"
        )

        current_index = self._window_index
        self._window_index += 1

        # Fire the callback (Phase 5 GPT scoring plugs in here)
        try:
            self.on_window(current_index, features)
        except Exception as e:
            print(f"[WindowManager] callback error: {e}")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _loop(self):
        while not self._stop_event.is_set():
            # Wait for the window to elapse, then tick
            self._stop_event.wait(self.window_size_s)
            if not self._stop_event.is_set():
                try:
                    self._tick()
                except Exception as e:
                    print(f"[WindowManager] tick error: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="window-mgr"
        )
        self._thread.start()
        print(
            f"[WindowManager] started — "
            f"{self.window_size_s}s windows, "
            f"{self.warmup_windows} warmup windows before scoring"
        )

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.window_size_s + 2)
            self._thread = None
        print("[WindowManager] stopped")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_in_warmup(self) -> bool:
        return self._window_index < self.warmup_windows

    @property
    def windows_completed(self) -> int:
        return self._window_index
