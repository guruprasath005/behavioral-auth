import { Fragment, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getAlerts,
  getWindows,
  type AlertRow,
  type FeatureWindowRow,
} from "../lib/api";
import { formatEpochSeconds } from "../lib/format";
import { RiskBadge } from "../components/RiskBadge";
import { Spinner } from "../components/Spinner";

type Filter = "ALL" | "HIGH" | "MODERATE" | "LOW";

export function AlertsPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [alerts, setAlerts] = useState<AlertRow[] | null>(null);
  const [windows, setWindows] = useState<FeatureWindowRow[] | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const [a, w] = await Promise.all([
          getAlerts(sessionId),
          getWindows(sessionId),
        ]);
        if (!cancelled) {
          setAlerts(a.alerts);
          setWindows(w.windows);
        }
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load data");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const counts = useMemo(() => {
    if (!alerts) return { HIGH: 0, MODERATE: 0, LOW: 0 };
    return alerts.reduce(
      (acc, x) => {
        if (x.risk_level === "HIGH") acc.HIGH += 1;
        else if (x.risk_level === "MODERATE") acc.MODERATE += 1;
        else if (x.risk_level === "LOW") acc.LOW += 1;
        return acc;
      },
      { HIGH: 0, MODERATE: 0, LOW: 0 },
    );
  }, [alerts]);

  const filtered = useMemo(() => {
    if (!alerts) return [];
    if (filter === "ALL") return alerts;
    return alerts.filter((a) => a.risk_level === filter);
  }, [alerts, filter]);

  if (!sessionId) {
    return <p className="text-slate-600">Missing session id.</p>;
  }

  if (error) {
    return (
      <div className="glass-panel border-rose-200/80 bg-rose-500/10 p-5 text-sm font-medium text-rose-900">
        {error}
      </div>
    );
  }

  if (alerts === null || windows === null) {
    return <Spinner label="Loading alerts…" />;
  }

  const filterBtn = (f: Filter) => (
    <button
      key={f}
      type="button"
      onClick={() => setFilter(f)}
      className={`rounded-xl border px-4 py-2 text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
        filter === f
          ? "border-indigo-300/80 bg-indigo-500/25 text-indigo-900 shadow-glass-sm"
          : "border-white/50 bg-white/30 text-slate-600 hover:border-white/60 hover:bg-white/45 hover:text-slate-800"
      } `}
    >
      {f}
    </button>
  );

  return (
    <div>
      <h2 className="mb-1 text-2xl font-semibold tracking-tight text-slate-900">
        Alerts &amp; audit
      </h2>
      <p className="mb-8 font-mono text-xs text-slate-500">{sessionId}</p>

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="HIGH" value={counts.HIGH} accent="text-rose-600" />
        <StatCard
          label="MODERATE"
          value={counts.MODERATE}
          accent="text-amber-700"
        />
        <StatCard label="LOW" value={counts.LOW} accent="text-emerald-700" />
        <StatCard
          label="Total windows"
          value={windows.length}
          accent="text-slate-800"
        />
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {filterBtn("ALL")}
        {filterBtn("HIGH")}
        {filterBtn("MODERATE")}
        {filterBtn("LOW")}
      </div>

      <div className="glass-panel overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-white/50 bg-white/30 text-[0.65rem] font-semibold uppercase tracking-wider text-slate-500 backdrop-blur-md">
            <tr>
              <th className="w-10 px-3 py-4" />
              <th className="px-4 py-4 font-semibold">Time</th>
              <th className="px-4 py-4 font-semibold">Window</th>
              <th className="px-4 py-4 font-semibold">Risk</th>
              <th className="px-4 py-4 font-semibold">Confidence</th>
              <th className="px-4 py-4 font-semibold">Anomalies</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/40 bg-white/20">
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-14 text-center text-sm text-slate-500"
                >
                  No alerts for this filter.
                </td>
              </tr>
            ) : (
              filtered.map((a) => (
                <Fragment key={a.id}>
                  <tr
                    className="cursor-pointer transition-colors hover:bg-white/40"
                    onClick={() =>
                      setExpanded(expanded === a.id ? null : a.id)
                    }
                  >
                    <td className="px-3 py-3.5 text-center text-xs text-slate-400">
                      {expanded === a.id ? "▼" : "▶"}
                    </td>
                    <td className="px-4 py-3.5 text-slate-600">
                      {formatEpochSeconds(a.timestamp)}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-slate-800">
                      {a.window_index}
                    </td>
                    <td className="px-4 py-3.5">
                      <RiskBadge level={a.risk_level} />
                    </td>
                    <td className="px-4 py-3.5 font-medium tabular-nums text-slate-800">
                      {(a.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap gap-1.5">
                        {a.anomalous_features.slice(0, 4).map((f) => (
                          <span
                            key={f}
                            className="rounded-lg border border-white/50 bg-white/40 px-2 py-0.5 text-[0.65rem] font-medium text-slate-600 backdrop-blur-sm"
                          >
                            {f}
                          </span>
                        ))}
                        {a.anomalous_features.length > 4 ? (
                          <span className="text-xs font-medium text-slate-400">
                            +{a.anomalous_features.length - 4}
                          </span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                  {expanded === a.id ? (
                    <tr className="bg-white/35 backdrop-blur-sm">
                      <td colSpan={6} className="px-5 py-5 text-slate-700">
                        <p className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
                          Reasoning
                        </p>
                        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                          {a.reasoning}
                        </p>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <div className="glass-panel-subtle p-5">
      <p className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className={`mt-2 text-3xl font-semibold tabular-nums tracking-tight ${accent}`}>
        {value}
      </p>
    </div>
  );
}
