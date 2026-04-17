"""
GPT-based risk scoring from behavioral features and z-scores.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from features.extractor import FEATURE_KEYS

_FALLBACK = {
    "risk_level": "MODERATE",
    "confidence": 0.5,
    "anomalous_features": [],
    "reasoning": "Parse failure or model unavailable; defaulting to MODERATE.",
}

_SYSTEM_PROMPT = (
    "You are a behavioral security analyst. You compare current typing and mouse "
    "telemetry to a per-user baseline (mean and standard deviation per feature) and "
    "z-scores. Large |z| suggests deviation from usual behavior. Shell commands may "
    "add context. Respond ONLY with a single JSON object, no markdown, with keys: "
    "risk_level (one of LOW, MODERATE, HIGH), confidence (number 0.0-1.0), "
    "anomalous_features (array of feature names that most drive the assessment), "
    "reasoning (short string explaining your decision)."
)


class GPTScorer:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=key)
        except Exception:
            return None
        return self._client

    def score(
        self,
        features: dict[str, float],
        zscores: dict[str, Any],
        shell_commands: list[str] | None = None,
        baseline: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, Any]:
        """
        Returns
        -------
        dict
            risk_level, confidence, anomalous_features, reasoning
        """
        shell_commands = shell_commands or []
        baseline = baseline or {}

        payload = {
            "baseline": baseline,
            "current_features": {k: features.get(k) for k in FEATURE_KEYS},
            "z_scores": {k: zscores.get(k) for k in FEATURE_KEYS},
            "shell_commands": shell_commands,
        }
        user_text = json.dumps(payload, indent=2)

        client = self._get_client()
        if client is None:
            out = dict(_FALLBACK)
            out["reasoning"] = "OPENAI_API_KEY not set or openai package missing."
            return out

        try:
            resp = client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = self._parse_json_response(raw)
            if parsed is None:
                return dict(_FALLBACK)
            return self._normalize_result(parsed)
        except Exception:
            return dict(_FALLBACK)

    @staticmethod
    def _parse_json_response(raw: str) -> dict | None:
        raw = raw.strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _normalize_result(data: dict) -> dict[str, Any]:
        level = str(data.get("risk_level", "MODERATE")).upper()
        if level not in ("LOW", "MODERATE", "HIGH"):
            level = "MODERATE"
        conf = data.get("confidence", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        anom = data.get("anomalous_features", [])
        if not isinstance(anom, list):
            anom = []
        anom = [str(x) for x in anom if str(x) in FEATURE_KEYS]
        reasoning = str(data.get("reasoning", "")).strip() or "No reasoning provided."
        return {
            "risk_level": level,
            "confidence": conf,
            "anomalous_features": anom,
            "reasoning": reasoning,
        }
