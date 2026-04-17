"""
BaselineEngine — per-session warmup statistics for the 13 behavioral features.
"""

from __future__ import annotations

import statistics
import time
from typing import Any, Optional

from features.extractor import FEATURE_KEYS
from storage.database import Database


class BaselineEngine:
    def __init__(self, user_id: str, db: Database):
        self.user_id = user_id
        self.db = db
        self._warmup_rows: list[dict[str, float]] = []
        self._cached: Optional[dict[str, dict[str, float]]] = None
        self._session_baseline_ready = False

    def feed_warmup(self, features: dict) -> None:
        """Accumulate scoring features from warmup windows; persist after 3."""
        if not features.get("is_warmup"):
            return
        row = {k: float(features[k]) for k in FEATURE_KEYS}
        self._warmup_rows.append(row)
        if len(self._warmup_rows) >= 3:
            self._compute_and_save(self._warmup_rows[:3])
            self._warmup_rows.clear()

    def _compute_and_save(self, rows: list[dict[str, float]]) -> None:
        stats: dict[str, tuple[float, float]] = {}
        for key in FEATURE_KEYS:
            vals = [r[key] for r in rows]
            mean = statistics.mean(vals)
            std = statistics.stdev(vals) if len(vals) > 1 else 0.0
            stats[key] = (mean, std)
        self.db.replace_baseline_profile(self.user_id, stats, updated_at=time.time())
        self._cached = {k: {"mean": stats[k][0], "std": stats[k][1]} for k in FEATURE_KEYS}
        self._session_baseline_ready = True

    def is_ready(self) -> bool:
        """True once this session has finished 3 warmup windows and baseline is stored."""
        return self._session_baseline_ready

    def load_baseline(self, user_id: str) -> dict[str, dict[str, float]]:
        """Return ``{feature: {mean, std}}`` from cache or database."""
        if self._cached is not None:
            return {k: dict(self._cached[k]) for k in self._cached}
        loaded = self.db.get_baseline_profile(user_id)
        if len(loaded) == len(FEATURE_KEYS):
            self._cached = loaded
        return loaded

    def compute_zscores(self, features_dict: dict) -> dict[str, Optional[float]]:
        """
        z = (current - mean) / std. Values with std == 0 map to ``None``.
        """
        baseline = self.load_baseline(self.user_id)
        if len(baseline) != len(FEATURE_KEYS):
            return {}
        out: dict[str, Optional[float]] = {}
        for key in FEATURE_KEYS:
            b = baseline[key]
            mean, std = b["mean"], b["std"]
            if std == 0:
                out[key] = None
            else:
                cur = float(features_dict[key])
                out[key] = (cur - mean) / std
        return out
