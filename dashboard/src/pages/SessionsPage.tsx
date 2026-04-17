import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSessions, type SessionRow } from "../lib/api";
import { formatEpochSeconds, formatSessionDuration, truncateId } from "../lib/format";
import { RiskBadge } from "../components/RiskBadge";
import { Spinner } from "../components/Spinner";

export function SessionsPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getSessions();
        if (!cancelled) setSessions(data.sessions);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load sessions");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="glass-panel border-rose-200/80 bg-rose-500/10 p-5 text-sm font-medium text-rose-900">
        {error}
      </div>
    );
  }

  if (sessions === null) {
    return <Spinner label="Loading sessions…" />;
  }

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold tracking-tight text-slate-900">
        Sessions
      </h2>
      <p className="mb-8 text-sm text-slate-600">
        Select a row to open alerts and audit trail.
      </p>
      <div className="glass-panel overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/50 bg-white/30 text-[0.65rem] font-semibold uppercase tracking-wider text-slate-500 backdrop-blur-md">
            <tr>
              <th className="px-5 py-4 font-semibold">Session</th>
              <th className="px-5 py-4 font-semibold">User</th>
              <th className="px-5 py-4 font-semibold">Started</th>
              <th className="px-5 py-4 font-semibold">Duration</th>
              <th className="px-5 py-4 font-semibold">Risk</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/40 bg-white/20">
            {sessions.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-5 py-14 text-center text-sm text-slate-500"
                >
                  No sessions in database.
                </td>
              </tr>
            ) : (
              sessions.map((s) => (
                <tr
                  key={s.session_id}
                  className="cursor-pointer transition-colors hover:bg-white/45"
                  onClick={() =>
                    navigate(`/sessions/${s.session_id}/alerts`)
                  }
                >
                  <td className="px-5 py-3.5 font-mono text-sm font-medium text-indigo-700">
                    {truncateId(s.session_id)}
                  </td>
                  <td className="px-5 py-3.5 font-medium text-slate-800">
                    {s.user_id}
                  </td>
                  <td className="px-5 py-3.5 text-slate-600">
                    {formatEpochSeconds(s.started_at)}
                  </td>
                  <td className="px-5 py-3.5 tabular-nums text-slate-600">
                    {formatSessionDuration(s.started_at, s.ended_at)}
                  </td>
                  <td className="px-5 py-3.5">
                    <RiskBadge level={s.risk_level} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
