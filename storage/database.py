"""
Thread-safe SQLite database for behavioral auth events.

All monitors run in separate threads and call the public insert_* methods.
Internally, inserts are placed on a queue and a single writer thread
flushes them to disk — avoids SQLite multi-thread conflicts entirely.
"""

import sqlite3
import queue
import threading
import time
import json
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "behavioral_auth.db")

# Sentinel to stop the writer thread
_STOP = object()


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        self._queue: queue.Queue = queue.Queue()
        # Schema first — writer thread starts after so there's no race on WAL mode
        self._init_schema()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="db-writer"
        )
        self._writer_thread.start()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self):
        """Create all tables if they don't exist yet."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")   # better concurrent reads
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                started_at   REAL NOT NULL,
                ended_at     REAL,
                risk_level   TEXT DEFAULT 'UNKNOWN'
            );

            CREATE TABLE IF NOT EXISTS keystroke_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id     TEXT    NOT NULL,
                key_label      TEXT    NOT NULL,
                is_special     INTEGER NOT NULL,
                is_backspace   INTEGER NOT NULL,
                dwell_time_ms  REAL,
                flight_time_ms REAL,
                timestamp      REAL    NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS mouse_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT  NOT NULL,
                event_type  TEXT  NOT NULL,
                x           INTEGER,
                y           INTEGER,
                button      TEXT,
                pressed     INTEGER,
                scroll_dx   REAL,
                scroll_dy   REAL,
                speed_px_s  REAL,
                timestamp   REAL  NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS shell_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                command     TEXT NOT NULL,
                timestamp   REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS feature_windows (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id     TEXT    NOT NULL,
                window_index   INTEGER NOT NULL,
                window_start   REAL    NOT NULL,
                window_end     REAL    NOT NULL,
                is_warmup      INTEGER NOT NULL DEFAULT 1,
                features_json  TEXT    NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS baseline_profiles (
                user_id       TEXT    NOT NULL,
                feature_name  TEXT    NOT NULL,
                mean          REAL    NOT NULL,
                std           REAL    NOT NULL,
                updated_at    REAL    NOT NULL,
                PRIMARY KEY (user_id, feature_name)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id               TEXT    NOT NULL,
                window_index             INTEGER NOT NULL,
                risk_level               TEXT    NOT NULL,
                confidence               REAL    NOT NULL,
                anomalous_features_json  TEXT    NOT NULL,
                reasoning                TEXT    NOT NULL,
                timestamp                REAL    NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_ks_session  ON keystroke_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_ms_session  ON mouse_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_sh_session  ON shell_events(session_id);
            CREATE INDEX IF NOT EXISTS idx_fw_session  ON feature_windows(session_id);
            CREATE INDEX IF NOT EXISTS idx_alert_session ON alerts(session_id);
            CREATE INDEX IF NOT EXISTS idx_baseline_user ON baseline_profiles(user_id);
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Internal writer loop (runs in a dedicated thread)
    # ------------------------------------------------------------------

    def _writer_loop(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is _STOP:
                break

            sql, params = item
            try:
                conn.execute(sql, params)
                conn.commit()
            except sqlite3.Error as e:
                print(f"[DB] Write error: {e} | sql={sql[:60]}")
            finally:
                self._queue.task_done()

        conn.close()

    def _enqueue(self, sql: str, params: tuple):
        self._queue.put((sql, params))

    # ------------------------------------------------------------------
    # Public insert methods (called from monitor threads)
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, user_id: str, started_at: float):
        self._enqueue(
            "INSERT INTO sessions (session_id, user_id, started_at) VALUES (?,?,?)",
            (session_id, user_id, started_at),
        )

    def end_session(self, session_id: str, ended_at: float, risk_level: str = "UNKNOWN"):
        self._enqueue(
            "UPDATE sessions SET ended_at=?, risk_level=? WHERE session_id=?",
            (ended_at, risk_level, session_id),
        )

    def insert_keystroke_event(
        self,
        session_id: str,
        key_label: str,
        is_special: bool,
        is_backspace: bool,
        dwell_time_ms: Optional[float],
        flight_time_ms: Optional[float],
        timestamp: float,
    ):
        self._enqueue(
            """INSERT INTO keystroke_events
               (session_id, key_label, is_special, is_backspace,
                dwell_time_ms, flight_time_ms, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (
                session_id,
                key_label,
                int(is_special),
                int(is_backspace),
                dwell_time_ms,
                flight_time_ms,
                timestamp,
            ),
        )

    def insert_mouse_event(
        self,
        session_id: str,
        event_type: str,
        timestamp: float,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: Optional[str] = None,
        pressed: Optional[int] = None,
        scroll_dx: Optional[float] = None,
        scroll_dy: Optional[float] = None,
        speed_px_s: Optional[float] = None,
    ):
        self._enqueue(
            """INSERT INTO mouse_events
               (session_id, event_type, x, y, button, pressed,
                scroll_dx, scroll_dy, speed_px_s, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id,
                event_type,
                x, y,
                button,
                pressed,
                scroll_dx,
                scroll_dy,
                speed_px_s,
                timestamp,
            ),
        )

    def insert_shell_event(self, session_id: str, command: str, timestamp: float):
        self._enqueue(
            "INSERT INTO shell_events (session_id, command, timestamp) VALUES (?,?,?)",
            (session_id, command, timestamp),
        )

    def insert_feature_window(
        self,
        session_id: str,
        window_index: int,
        window_start: float,
        window_end: float,
        is_warmup: bool,
        features_json: str,
    ):
        self._enqueue(
            """INSERT INTO feature_windows
               (session_id, window_index, window_start, window_end, is_warmup, features_json)
               VALUES (?,?,?,?,?,?)""",
            (session_id, window_index, window_start, window_end, int(is_warmup), features_json),
        )

    # ------------------------------------------------------------------
    # Read helpers (used by feature extraction later)
    # ------------------------------------------------------------------

    def get_keystroke_events(self, session_id: str) -> list[dict]:
        self._queue.join()  # flush pending writes first
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM keystroke_events WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_mouse_events(self, session_id: str) -> list[dict]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM mouse_events WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_shell_events(self, session_id: str) -> list[dict]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM shell_events WHERE session_id=? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_feature_windows(self, session_id: str, warmup_only: bool = False) -> list[dict]:
        """Return all saved feature windows for a session."""
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if warmup_only:
            rows = conn.execute(
                "SELECT * FROM feature_windows WHERE session_id=? AND is_warmup=1 ORDER BY window_index",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM feature_windows WHERE session_id=? ORDER BY window_index",
                (session_id,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_sessions(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> Optional[dict]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_alerts_for_session(self, session_id: str) -> list[dict]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM alerts WHERE session_id=?
               ORDER BY timestamp ASC, id ASC""",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def replace_baseline_profile(
        self,
        user_id: str,
        feature_stats: dict[str, tuple[float, float]],
        updated_at: float,
    ):
        """Replace all baseline rows for ``user_id`` with new mean/std per feature."""
        self._enqueue(
            "DELETE FROM baseline_profiles WHERE user_id=?",
            (user_id,),
        )
        for feature_name, (mean, std) in feature_stats.items():
            self._enqueue(
                """INSERT INTO baseline_profiles
                   (user_id, feature_name, mean, std, updated_at)
                   VALUES (?,?,?,?,?)""",
                (user_id, feature_name, mean, std, updated_at),
            )

    def get_baseline_profile(self, user_id: str) -> dict[str, dict[str, float]]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT feature_name, mean, std FROM baseline_profiles WHERE user_id=?",
            (user_id,),
        ).fetchall()
        conn.close()
        return {r["feature_name"]: {"mean": r["mean"], "std": r["std"]} for r in rows}

    def insert_alert(
        self,
        session_id: str,
        window_index: int,
        risk_level: str,
        confidence: float,
        anomalous_features: list,
        reasoning: str,
        timestamp: float,
    ):
        self._enqueue(
            """INSERT INTO alerts
               (session_id, window_index, risk_level, confidence,
                anomalous_features_json, reasoning, timestamp)
               VALUES (?,?,?,?,?,?,?)""",
            (
                session_id,
                window_index,
                risk_level,
                confidence,
                json.dumps(anomalous_features),
                reasoning,
                timestamp,
            ),
        )

    def get_shell_commands_in_window(
        self, session_id: str, window_start: float, window_end: float
    ) -> list[str]:
        self._queue.join()
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """SELECT command FROM shell_events
               WHERE session_id=? AND timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp""",
            (session_id, window_start, window_end),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def close(self):
        """Flush all pending writes and stop the writer thread."""
        self._queue.join()
        self._queue.put(_STOP)
        self._writer_thread.join(timeout=5)
