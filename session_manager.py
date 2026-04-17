"""
Session Manager
---------------
Owns the lifecycle of a monitoring session:
  - generates a unique session_id
  - starts all three capture monitors (keystroke, mouse, shell)
  - starts the WindowManager which fires feature extraction every 10s
  - stops everything cleanly on request
  - exposes the current session_id to other modules

on_window callback
~~~~~~~~~~~~~~~~~~
By default, each window updates ``BaselineEngine`` during warmup (3 windows), then
computes z-scores, calls ``GPTScorer``, prints the result, and writes an ``alerts`` row.

Pass a custom ``on_window`` to override this behavior.
"""

import time
import uuid
from typing import Callable, Optional

from baseline import BaselineEngine
from storage.database import Database
from capture.keystroke_monitor import KeystrokeMonitor
from capture.mouse_monitor import MouseMonitor
from capture.shell_monitor import ShellMonitor
from features.window import WindowManager
from features.extractor import FEATURE_KEYS
from scoring import GPTScorer


class SessionManager:
    def __init__(
        self,
        user_id: str,
        db: Database,
        enable_shell: bool = True,
        on_window: Optional[Callable[[int, dict], None]] = None,
        window_size_s: int = WindowManager.WINDOW_SIZE_S,
        warmup_windows: int = WindowManager.WARMUP_WINDOWS,
    ):
        self.user_id      = user_id
        self.db           = db
        self.enable_shell = enable_shell

        self.session_id: str          = str(uuid.uuid4())
        self._started_at: Optional[float] = None

        self._baseline   = BaselineEngine(user_id, db)
        self._gpt_scorer = GPTScorer()
        self._on_window  = on_window or self._default_scoring_on_window

        # Capture monitors
        self._ks_monitor = KeystrokeMonitor(self.session_id, self.db)
        self._ms_monitor = MouseMonitor(self.session_id, self.db)
        self._sh_monitor = ShellMonitor(self.session_id, self.db) if enable_shell else None

        # Feature extraction + windowing
        self._win_manager = WindowManager(
            session_id=self.session_id,
            db=self.db,
            on_window=self._on_window,
            window_size_s=window_size_s,
            warmup_windows=warmup_windows,
        )

    def _default_scoring_on_window(self, window_index: int, features: dict):
        if features.get("is_warmup"):
            self._baseline.feed_warmup(features)
            return

        if not self._baseline.is_ready():
            print(
                f"[Session] window {window_index}: baseline not ready; skipping score."
            )
            return

        scoring_features = {k: float(features[k]) for k in FEATURE_KEYS}
        zscores = self._baseline.compute_zscores(features)
        baseline_snapshot = self._baseline.load_baseline(self.user_id)
        shell_cmds = self.db.get_shell_commands_in_window(
            self.session_id,
            features["window_start"],
            features["window_end"],
        )

        result = self._gpt_scorer.score(
            scoring_features,
            zscores,
            shell_commands=shell_cmds,
            baseline=baseline_snapshot,
        )

        print(
            f"\n[Score] window={window_index}  risk={result['risk_level']}  "
            f"confidence={result['confidence']:.2f}"
        )
        if result.get("anomalous_features"):
            print(f"        anomalous: {result['anomalous_features']}")
        print(f"        reasoning: {result['reasoning']}\n")

        self.db.insert_alert(
            session_id=self.session_id,
            window_index=window_index,
            risk_level=result["risk_level"],
            confidence=float(result["confidence"]),
            anomalous_features=result.get("anomalous_features") or [],
            reasoning=result.get("reasoning") or "",
            timestamp=time.time(),
        )

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self):
        """Create the session record and start all monitors + window manager."""
        self._started_at = time.time()
        self.db.create_session(
            session_id=self.session_id,
            user_id=self.user_id,
            started_at=self._started_at,
        )

        self._ks_monitor.start()
        self._ms_monitor.start()
        if self._sh_monitor:
            self._sh_monitor.start()
        self._win_manager.start()

        print(f"\n[Session] Started  id={self.session_id}  user={self.user_id}")
        print(f"[Session] Window size: {self._win_manager.window_size_s}s  |  "
              f"Warmup: {self._win_manager.warmup_windows} windows")
        print("[Session] Monitoring keystrokes, mouse, and shell commands.")
        print("[Session] Press Ctrl+C to stop.\n")

    def stop(self, risk_level: str = "UNKNOWN"):
        """Stop all monitors, window manager, and close the session record."""
        self._win_manager.stop()
        self._ks_monitor.stop()
        self._ms_monitor.stop()
        if self._sh_monitor:
            self._sh_monitor.stop()

        # Use highest alert risk if caller didn't specify one
        if risk_level == "UNKNOWN":
            alerts = self.db.get_alerts_for_session(self.session_id)
            order = {"HIGH": 2, "MODERATE": 1, "LOW": 0}
            if alerts:
                risk_level = max(
                    (a["risk_level"] for a in alerts),
                    key=lambda r: order.get(r, -1),
                )

        self.db.end_session(
            session_id=self.session_id,
            ended_at=time.time(),
            risk_level=risk_level,
        )
        print(f"\n[Session] Ended  id={self.session_id}  risk={risk_level}")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def idle_seconds(self) -> float:
        """Seconds since last mouse movement."""
        return self._ms_monitor.get_idle_seconds()

    def is_in_warmup(self) -> bool:
        """True while still collecting warmup windows."""
        return self._win_manager.is_in_warmup

    def windows_completed(self) -> int:
        return self._win_manager.windows_completed

    def summary(self) -> dict:
        """Quick stats dict for the current session."""
        ks_events = self.db.get_keystroke_events(self.session_id)
        ms_events = self.db.get_mouse_events(self.session_id)
        sh_events = self.db.get_shell_events(self.session_id)
        fw        = self.db.get_feature_windows(self.session_id)
        duration  = (time.time() - self._started_at) if self._started_at else 0

        return {
            "session_id":        self.session_id,
            "user_id":           self.user_id,
            "duration_s":        round(duration, 1),
            "keystroke_events":  len(ks_events),
            "mouse_events":      len(ms_events),
            "shell_events":      len(sh_events),
            "windows_extracted": len(fw),
            "warmup_complete":   not self.is_in_warmup(),
        }
