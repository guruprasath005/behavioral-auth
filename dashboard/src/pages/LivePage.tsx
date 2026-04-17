import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getAlerts,
  getBaseline,
  getLive,
  getShellEvents,
  type AlertRow,
  type BaselineResponse,
  type LiveResponse,
  type ShellEventRow,
} from "../lib/api";
import { FEATURE_KEYS } from "../lib/features";
import { formatEpochSeconds } from "../lib/format";
import { computeZ } from "../lib/zscore";
import { RiskBadge } from "../components/RiskBadge";
import { Spinner } from "../components/Spinner";
import { flagCommand } from "../lib/shellFlags";

const POLL_MS = 3000;

function shortFeature(name: string): string {
  return name.replace(/_per_min/g, "/m").replace(/_ms/g, "").slice(0, 18);
}

export function LivePage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [live, setLive] = useState<LiveResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[] | null>(null);
  const [shellEvents, setShellEvents] = useState<ShellEventRow[]>([]);
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [baselineError, setBaselineError] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const b = await getBaseline(sessionId);
        if (!cancelled) setBaseline(b);
      } catch {
        if (!cancelled) {
          setBaseline(null);
          setBaselineError(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;

    const tick = async () => {
      try {
        const [l, a, sh] = await Promise.all([
          getLive(sessionId),
          getAlerts(sessionId),
          getShellEvents(sessionId),
        ]);
        setLive(l);
        setAlerts(a.alerts);
        setShellEvents(sh.events);
        setLiveError(null);
      } catch (e) {
        setLiveError(e instanceof Error ? e.message : "Poll failed");
      } finally {
        setInitialLoad(false);
      }
    };

    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(id);
  }, [sessionId]);

  const anomalousSet = useMemo(() => {
    const list = live?.latest_alert?.anomalous_features ?? [];
    return new Set(list);
  }, [live]);

  const featureRows = useMemo(() => {
    const win = live?.latest_feature_window;
    const feats = win?.features ?? {};
    const prof = baseline?.baseline ?? {};
    return FEATURE_KEYS.map((key) => {
      const raw = feats[key];
      const value = typeof raw === "number" ? raw : NaN;
      const b = prof[key];
      const z =
        b && Number.isFinite(value)
          ? computeZ(value, b.mean, b.std)
          : null;
      const anomalous = anomalousSet.has(key);
      return { key, value, z, anomalous };
    });
  }, [live, baseline, anomalousSet]);

  const chartData = useMemo(() => {
    return featureRows.map((r) => ({
      name: shortFeature(r.key),
      zMag: r.z === null ? 0.08 : Math.min(Math.abs(r.z), 4),
      fill: r.anomalous ? "#e11d48" : "#4f46e5",
      noData: r.z === null,
    }));
  }, [featureRows]);

  const miniAlerts = useMemo(() => {
    if (!alerts?.length) return [];
    return [...alerts].slice(-5).reverse();
  }, [alerts]);

  if (!sessionId) {
    return <p className="text-slate-600">Missing session id.</p>;
  }

  if (liveError && !live) {
    return (
      <div className="glass-panel border-rose-200/80 bg-rose-500/10 p-5 text-sm font-medium text-rose-900">
        {liveError}
      </div>
    );
  }

  if (initialLoad && !live) {
    return <Spinner label="Connecting to live feed…" />;
  }

  const latest = live?.latest_alert;
  const win = live?.latest_feature_window;
  const confPct = latest
    ? Math.round(latest.confidence * 100)
    : null;
  const mode = win ? (win.is_warmup ? "WARMUP" : "LIVE") : "—";
  const idle = live?.idle_seconds;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">
          Live monitor
        </h2>
        <p className="mt-1 font-mono text-xs text-slate-500">{sessionId}</p>
        {liveError ? (
          <p className="mt-3 text-xs font-medium text-amber-800">
            Warning: {liveError}
          </p>
        ) : null}
        {baselineError ? (
          <p className="mt-3 text-xs font-medium text-amber-800">
            Baseline unavailable — z-scores hidden until baseline loads.
          </p>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="glass-panel p-7">
          <p className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
            Current score
          </p>
          {latest ? (
            <>
              <p className="mt-5 text-6xl font-bold tabular-nums tracking-tight text-slate-900">
                {confPct}%
              </p>
              <p className="mt-1 text-sm font-medium text-slate-500">
                confidence
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <RiskBadge level={latest.risk_level} />
                <span className="rounded-xl border border-white/60 bg-white/40 px-3 py-1 text-xs font-semibold text-slate-700 shadow-glass-sm backdrop-blur-sm">
                  {mode}
                </span>
              </div>
            </>
          ) : (
            <p className="mt-8 text-sm font-medium text-slate-500">
              No alert yet for this session.
            </p>
          )}
          <dl className="mt-8 space-y-3 border-t border-white/50 pt-6 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="font-medium text-slate-500">Idle</dt>
              <dd className="font-mono font-semibold text-slate-800">
                {idle === null || idle === undefined
                  ? "—"
                  : `${idle.toFixed(0)}s`}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="font-medium text-slate-500">Window</dt>
              <dd className="font-mono font-semibold text-slate-800">
                {win ? `#${win.window_index}` : "—"}
              </dd>
            </div>
          </dl>
        </div>

        <div className="glass-panel p-5">
          <p className="mb-4 px-1 text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
            Feature feed
          </p>
          <div className="max-h-[420px] space-y-1.5 overflow-y-auto pr-1">
            {featureRows.map((r) => (
              <div
                key={r.key}
                className={`flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-xs transition-colors ${
                  r.anomalous
                    ? "border border-rose-200/90 bg-rose-500/15 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]"
                    : "border border-white/40 bg-white/25"
                }`}
              >
                <span
                  className={`min-w-0 flex-1 truncate font-mono text-[0.7rem] ${
                    r.anomalous ? "font-medium text-rose-900" : "text-slate-600"
                  }`}
                  title={r.key}
                >
                  {r.key}
                </span>
                <span className="shrink-0 tabular-nums font-semibold text-slate-800">
                  {Number.isFinite(r.value) ? r.value.toFixed(3) : "—"}
                </span>
                <span
                  className={`w-[4.5rem] shrink-0 text-right font-mono text-[0.7rem] tabular-nums ${
                    r.anomalous ? "font-bold text-rose-700" : "text-slate-400"
                  }`}
                >
                  {r.anomalous && r.z !== null
                    ? `z ${r.z.toFixed(2)}`
                    : r.anomalous
                      ? "z —"
                      : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="glass-panel p-6">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
            |z-score| magnitude (capped at 4)
          </p>
          <p className="text-[0.65rem] text-slate-400">
            {win ? `window #${win.window_index} · updated ${formatEpochSeconds(win.window_end)}` : "waiting for window…"}
          </p>
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 8, right: 16, top: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#cbd5e1" />
              <XAxis type="number" domain={[0, 4]} stroke="#94a3b8" tick={{ fill: "#64748b", fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="name"
                width={100}
                tick={{ fill: "#475569", fontSize: 10 }}
                stroke="#cbd5e1"
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "rgba(255, 255, 255, 0.92)",
                  border: "1px solid rgba(255, 255, 255, 0.8)",
                  borderRadius: "12px",
                  boxShadow: "0 8px 32px rgba(15, 23, 42, 0.12)",
                  backdropFilter: "blur(12px)",
                }}
                labelStyle={{ color: "#0f172a", fontWeight: 600 }}
                formatter={(value: number, _name: string, props: { payload?: { noData?: boolean } }) =>
                  props.payload?.noData ? ["no baseline data", "|z|"] : [value.toFixed(2), "|z|"]
                }
              />
              <Bar dataKey="zMag" radius={[0, 6, 6, 0]}>
                {chartData.map((entry, i) => (
                  <Cell key={`c-${i}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <p className="mb-4 text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
          Shell commands
        </p>
        {shellEvents.length === 0 ? (
          <div className="glass-panel-subtle mb-6 px-5 py-10 text-center text-sm font-medium text-slate-500">
            No shell commands captured.{" "}
            <span className="text-slate-600">
              Run{" "}
              <code className="rounded-md border border-white/50 bg-white/40 px-1.5 py-0.5 font-mono text-xs text-slate-800">
                python3 main.py --install-hook
              </code>{" "}
              and restart your terminal to enable shell monitoring.
            </span>
          </div>
        ) : (
          <ul className="mb-6 space-y-3">
            {[...shellEvents].reverse().slice(0, 20).map((e) => {
              const flag = flagCommand(e.command);
              return (
                <li
                  key={e.id}
                  className={`glass-panel-subtle flex flex-wrap items-baseline gap-x-3 gap-y-2 px-5 py-3.5 transition-shadow ${
                    flag
                      ? "border-rose-200/90 bg-rose-500/[0.12] shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]"
                      : ""
                  }`}
                >
                  <span className="shrink-0 text-sm font-medium text-slate-600">
                    {formatEpochSeconds(e.timestamp)}
                  </span>
                  <span
                    className={`shrink-0 font-mono text-sm font-bold ${
                      flag ? "text-rose-600" : "text-emerald-600"
                    }`}
                    aria-hidden
                  >
                    $
                  </span>
                  <span
                    className={`min-w-0 flex-1 break-all font-mono text-sm leading-relaxed ${
                      flag ? "font-medium text-rose-950" : "text-slate-800"
                    }`}
                  >
                    {e.command}
                  </span>
                  {flag ? (
                    <span className="ml-auto shrink-0 rounded-lg border border-rose-200/80 bg-rose-500/20 px-2.5 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider text-rose-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] backdrop-blur-sm">
                      {flag.toUpperCase()}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div>
        <p className="mb-4 text-[0.65rem] font-bold uppercase tracking-wider text-slate-500">
          Last 5 alerts
        </p>
        <ul className="space-y-3">
          {miniAlerts.length === 0 ? (
            <li className="glass-panel-subtle px-5 py-10 text-center text-sm font-medium text-slate-500">
              No alerts yet.
            </li>
          ) : (
            miniAlerts.map((a) => (
              <li
                key={a.id}
                className="glass-panel-subtle flex flex-wrap items-center gap-3 px-5 py-3.5"
              >
                <RiskBadge level={a.risk_level} />
                <span className="text-sm font-medium text-slate-600">
                  {formatEpochSeconds(a.timestamp)}
                </span>
                <span className="text-sm text-slate-500">
                  win {a.window_index}
                </span>
                <span className="ml-auto text-sm font-bold tabular-nums text-slate-800">
                  {(a.confidence * 100).toFixed(0)}%
                </span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
