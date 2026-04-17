"""
Feature Extractor
-----------------
Takes raw keystroke + mouse events for a time window and computes
the 13 behavioural features used by the GPT-4o mini scoring engine.

Keystroke features (7)
~~~~~~~~~~~~~~~~~~~~~~
  typing_speed_wpm          — chars typed ÷ 5 ÷ minutes in window
  keystroke_interval_avg_ms — mean flight time  (key-up → next key-down)
  keystroke_interval_std_ms — std  flight time  (typing rhythm variance)
  backspace_rate            — backspace count ÷ total keystrokes
  error_rate                — backspace count ÷ words typed
  pause_frequency           — fraction of intervals > PAUSE_THRESHOLD
  burst_typing_ratio        — fraction of intervals < BURST_THRESHOLD

Mouse features (6)
~~~~~~~~~~~~~~~~~~
  mouse_speed_avg           — mean   instantaneous speed (px / s)
  mouse_speed_std           — std    instantaneous speed
  click_rate_per_min        — left/right clicks per minute
  double_click_rate         — double-clicks ÷ total click events
  scroll_events_per_min     — scroll events per minute
  mouse_idle_ratio          — fraction of window where mouse was still
"""

import statistics
from typing import Optional

# ------------------------------------------------------------------
# Tuning constants
# ------------------------------------------------------------------
PAUSE_THRESHOLD_MS  = 1_000.0   # flight > 1 s  → user paused
BURST_THRESHOLD_MS  = 100.0     # flight < 100 ms → rapid burst
IDLE_THRESHOLD_S    = 2.0       # no mouse move for 2 s → idle
MIN_KEYSTROKES      = 5         # minimum to mark window as reliable


class FeatureExtractor:
    """Stateless extractor — call .extract() with event lists each window."""

    def extract(
        self,
        keystroke_events: list[dict],
        mouse_events: list[dict],
        window_duration_s: float,
    ) -> dict:
        """
        Compute all 13 features.

        Parameters
        ----------
        keystroke_events  : rows from the keystroke_events table for this window
        mouse_events      : rows from the mouse_events table for this window
        window_duration_s : length of the time window in seconds

        Returns
        -------
        dict with all 13 feature keys + metadata keys:
            keystroke_count, mouse_event_count, window_duration_s, sufficient_data
        """
        features: dict = {}
        features.update(self._keystroke_features(keystroke_events, window_duration_s))
        features.update(self._mouse_features(mouse_events, window_duration_s))

        # Metadata (not fed to GPT, used for logging / baseline decisions)
        features["keystroke_count"]   = len(keystroke_events)
        features["mouse_event_count"] = len(mouse_events)
        features["window_duration_s"] = round(window_duration_s, 2)
        features["sufficient_data"]   = len(keystroke_events) >= MIN_KEYSTROKES

        return features

    # ------------------------------------------------------------------
    # Keystroke features
    # ------------------------------------------------------------------

    def _keystroke_features(self, events: list[dict], duration_s: float) -> dict:
        if not events:
            return self._zero_keystroke_features()

        total         = len(events)
        backspace_count = sum(1 for e in events if e["is_backspace"])
        special_count   = sum(1 for e in events if e["is_special"])
        char_count      = max(total - special_count, 0)

        # Flight times — gap between key-up and next key-down
        flight_times = [
            e["flight_time_ms"]
            for e in events
            if e.get("flight_time_ms") is not None and e["flight_time_ms"] > 0
        ]

        # 1. typing_speed_wpm
        if duration_s > 0 and char_count > 0:
            typing_speed_wpm = (char_count / 5.0) / (duration_s / 60.0)
        else:
            typing_speed_wpm = 0.0

        # 2. keystroke_interval_avg_ms  (mean flight time)
        ks_avg = statistics.mean(flight_times) if flight_times else 0.0

        # 3. keystroke_interval_std_ms  (std flight time)
        ks_std = statistics.stdev(flight_times) if len(flight_times) > 1 else 0.0

        # 4. backspace_rate
        backspace_rate = backspace_count / total if total > 0 else 0.0

        # 5. error_rate  (backspaces per word)
        words_typed = char_count / 5.0 if char_count > 0 else 1.0
        error_rate  = backspace_count / words_typed

        # 6. pause_frequency  (fraction of intervals that are long pauses)
        if flight_times:
            pauses          = [f for f in flight_times if f > PAUSE_THRESHOLD_MS]
            pause_frequency = len(pauses) / len(flight_times)
        else:
            pause_frequency = 0.0

        # 7. burst_typing_ratio  (fraction of intervals that are rapid bursts)
        if flight_times:
            bursts             = [f for f in flight_times if f < BURST_THRESHOLD_MS]
            burst_typing_ratio = len(bursts) / len(flight_times)
        else:
            burst_typing_ratio = 0.0

        return {
            "typing_speed_wpm":           round(typing_speed_wpm,    3),
            "keystroke_interval_avg_ms":  round(ks_avg,               3),
            "keystroke_interval_std_ms":  round(ks_std,               3),
            "backspace_rate":             round(backspace_rate,        4),
            "error_rate":                 round(error_rate,            4),
            "pause_frequency":            round(pause_frequency,       4),
            "burst_typing_ratio":         round(burst_typing_ratio,    4),
        }

    # ------------------------------------------------------------------
    # Mouse features
    # ------------------------------------------------------------------

    def _mouse_features(self, events: list[dict], duration_s: float) -> dict:
        if not events:
            return self._zero_mouse_features()

        duration_min = max(duration_s / 60.0, 1e-6)

        move_events   = [e for e in events if e["event_type"] == "move"]
        click_events  = [
            e for e in events
            if e["event_type"] == "click" and e.get("pressed") == 1
        ]
        dbl_events    = [e for e in events if e["event_type"] == "double_click"]
        scroll_events = [e for e in events if e["event_type"] == "scroll"]

        # Speeds from move events (px/s)
        speeds = [
            e["speed_px_s"]
            for e in move_events
            if e.get("speed_px_s") is not None
        ]

        # 8. mouse_speed_avg
        mouse_speed_avg = statistics.mean(speeds) if speeds else 0.0

        # 9. mouse_speed_std
        mouse_speed_std = statistics.stdev(speeds) if len(speeds) > 1 else 0.0

        # 10. click_rate_per_min
        click_rate_per_min = len(click_events) / duration_min

        # 11. double_click_rate
        total_clicks     = len(click_events) + len(dbl_events)
        double_click_rate = len(dbl_events) / total_clicks if total_clicks > 0 else 0.0

        # 12. scroll_events_per_min
        scroll_events_per_min = len(scroll_events) / duration_min

        # 13. mouse_idle_ratio
        mouse_idle_ratio = self._idle_ratio(move_events, duration_s)

        return {
            "mouse_speed_avg":        round(mouse_speed_avg,       3),
            "mouse_speed_std":        round(mouse_speed_std,       3),
            "click_rate_per_min":     round(click_rate_per_min,    3),
            "double_click_rate":      round(double_click_rate,     4),
            "scroll_events_per_min":  round(scroll_events_per_min, 3),
            "mouse_idle_ratio":       round(mouse_idle_ratio,      4),
        }

    @staticmethod
    def _idle_ratio(move_events: list[dict], duration_s: float) -> float:
        """
        Fraction of the window where the mouse was not moving.

        Strategy: sort move events by timestamp; any gap between
        consecutive moves that exceeds IDLE_THRESHOLD_S is idle time.
        """
        if not move_events or duration_s <= 0:
            return 1.0  # no movement at all → fully idle

        timestamps = sorted(e["timestamp"] for e in move_events)
        idle_total = 0.0

        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            if gap > IDLE_THRESHOLD_S:
                idle_total += gap

        return round(min(idle_total / duration_s, 1.0), 4)

    # ------------------------------------------------------------------
    # Zero-value fallbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _zero_keystroke_features() -> dict:
        return {
            "typing_speed_wpm":           0.0,
            "keystroke_interval_avg_ms":  0.0,
            "keystroke_interval_std_ms":  0.0,
            "backspace_rate":             0.0,
            "error_rate":                 0.0,
            "pause_frequency":            0.0,
            "burst_typing_ratio":         0.0,
        }

    @staticmethod
    def _zero_mouse_features() -> dict:
        return {
            "mouse_speed_avg":        0.0,
            "mouse_speed_std":        0.0,
            "click_rate_per_min":     0.0,
            "double_click_rate":      0.0,
            "scroll_events_per_min":  0.0,
            "mouse_idle_ratio":       1.0,   # idle by default
        }


# ------------------------------------------------------------------
# Feature names (for GPT prompt building and Z-score labelling)
# ------------------------------------------------------------------

FEATURE_KEYS = [
    "typing_speed_wpm",
    "keystroke_interval_avg_ms",
    "keystroke_interval_std_ms",
    "backspace_rate",
    "error_rate",
    "pause_frequency",
    "burst_typing_ratio",
    "mouse_speed_avg",
    "mouse_speed_std",
    "click_rate_per_min",
    "double_click_rate",
    "scroll_events_per_min",
    "mouse_idle_ratio",
]
