const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export type SessionRow = {
  session_id: string;
  user_id: string;
  started_at: number;
  ended_at: number | null;
  risk_level: string;
};

export type AlertRow = {
  id: number;
  session_id: string;
  window_index: number;
  risk_level: string;
  confidence: number;
  anomalous_features: string[];
  reasoning: string;
  timestamp: number;
};

export type BaselineResponse = {
  baseline: Record<string, { mean: number; std: number }>;
  radar_data: { feature: string; value: number }[];
};

export type FeatureWindowRow = {
  id: number;
  session_id: string;
  window_index: number;
  window_start: number;
  window_end: number;
  is_warmup: boolean;
  features: Record<string, number>;
};

export type LiveResponse = {
  latest_alert: AlertRow | null;
  latest_feature_window: FeatureWindowRow | null;
  idle_seconds: number | null;
};

export function getSessions() {
  return fetchJson<{ sessions: SessionRow[] }>("/sessions");
}

export function getAlerts(sessionId: string) {
  return fetchJson<{ alerts: AlertRow[] }>(`/sessions/${sessionId}/alerts`);
}

export function getBaseline(sessionId: string) {
  return fetchJson<BaselineResponse>(`/sessions/${sessionId}/baseline`);
}

export function getWindows(sessionId: string) {
  return fetchJson<{ windows: FeatureWindowRow[] }>(
    `/sessions/${sessionId}/windows`,
  );
}

export type ShellEventRow = {
  id: number;
  session_id: string;
  command: string;
  timestamp: number;
};

export function getLive(sessionId: string) {
  return fetchJson<LiveResponse>(`/sessions/${sessionId}/live`);
}

export function getShellEvents(sessionId: string) {
  return fetchJson<{ events: ShellEventRow[] }>(`/sessions/${sessionId}/shell`);
}
