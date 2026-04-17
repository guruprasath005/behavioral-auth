export function Spinner({ label }: { label?: string }) {
  return (
    <div
      className="glass-panel flex flex-col items-center justify-center gap-4 py-20"
      role="status"
      aria-label={label ?? "Loading"}
    >
      <div className="relative h-11 w-11">
        <div className="absolute inset-0 rounded-full border-2 border-white/80" />
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-indigo-500 border-r-violet-400" />
      </div>
      {label ? (
        <p className="text-sm font-medium text-slate-600">{label}</p>
      ) : null}
    </div>
  );
}
