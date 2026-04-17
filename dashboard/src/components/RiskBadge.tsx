type Risk = "HIGH" | "MODERATE" | "LOW" | string;

const styles: Record<string, string> = {
  HIGH:
    "border-rose-200/80 bg-rose-500/15 text-rose-800 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]",
  MODERATE:
    "border-amber-200/80 bg-amber-400/20 text-amber-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]",
  LOW:
    "border-emerald-200/80 bg-emerald-500/15 text-emerald-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]",
};

export function RiskBadge({ level }: { level: Risk }) {
  const cls =
    styles[level] ??
    "border-slate-200/90 bg-slate-500/10 text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.6)]";
  return (
    <span
      className={`inline-flex rounded-lg border px-2.5 py-0.5 text-[0.65rem] font-bold uppercase tracking-wider backdrop-blur-sm ${cls}`}
    >
      {level}
    </span>
  );
}
